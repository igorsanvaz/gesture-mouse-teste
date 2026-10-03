"""Gestos de navegação além do clique esquerdo: rolagem, clique direito, duplo e meio.

Como em `clicks`, nada aqui chama o sistema: as classes recebem os pontos da mão e
devolvem o que deve acontecer, para poderem ser testadas sem câmera nem mouse.
"""

from __future__ import annotations

import math
from enum import Enum

from .clicks import INDEX_TIP, MIDDLE_MCP, THUMB_TIP, WRIST, ClickEvent, PinchClicker, _dist

# Índices dos pontos do MediaPipe Hands: (articulação do meio, ponta) de cada dedo
FINGER_JOINTS = {
    "index": (6, 8),
    "middle": (10, 12),
    "ring": (14, 16),
    "pinky": (18, 20),
}
MIDDLE_TIP = 12
RING_TIP = 16


def _hand_size(landmarks) -> float:
    return _dist(landmarks[WRIST], landmarks[MIDDLE_MCP])


def fingers_extended(landmarks, ratio: float = 1.15) -> dict[str, bool]:
    """Dedo esticado = ponta bem mais longe do punho que a articulação do meio.

    Comparar distâncias até o punho (e não coordenadas y) funciona com a mão inclinada.
    """
    wrist = landmarks[WRIST]
    return {name: _dist(wrist, landmarks[tip]) > ratio * _dist(wrist, landmarks[pip])
            for name, (pip, tip) in FINGER_JOINTS.items()}


def finger_pinch_ratios(landmarks) -> dict[str, float]:
    """Distância do polegar a cada ponta de dedo, normalizada pelo tamanho da mão."""
    size = _hand_size(landmarks)
    if size < 1e-6:
        return {"index": math.inf, "middle": math.inf, "ring": math.inf}
    thumb = landmarks[THUMB_TIP]
    return {
        "index": _dist(thumb, landmarks[INDEX_TIP]) / size,
        "middle": _dist(thumb, landmarks[MIDDLE_TIP]) / size,
        "ring": _dist(thumb, landmarks[RING_TIP]) / size,
    }


# ----------------------------------------------------------------------------
class Posture(Enum):
    POINT = "point"     # qualquer pose comum: move o cursor
    SCROLL = "scroll"   # indicador + médio esticados, anelar + mínimo dobrados


def classify_posture(landmarks) -> Posture:
    f = fingers_extended(landmarks)
    if f["index"] and f["middle"] and not f["ring"] and not f["pinky"]:
        return Posture.SCROLL
    return Posture.POINT


class PostureDetector:
    """Só troca de pose depois que a nova pose se mantém por `hold_s` segundos.

    Evita entrar e sair da rolagem a cada quadro quando um dedo fica no limiar.
    """

    def __init__(self, hold_s: float = 0.25):
        self.hold_s = hold_s
        self.reset()

    def reset(self) -> None:
        self.posture = Posture.POINT
        self._candidate = Posture.POINT
        self._since = 0.0

    def update(self, observed: Posture, t: float) -> Posture:
        if observed == self.posture:
            self._candidate = observed
        elif observed != self._candidate:
            self._candidate, self._since = observed, t
        elif t - self._since >= self.hold_s:
            self.posture = observed
        return self.posture


# ----------------------------------------------------------------------------
class ScrollController:
    """Rolagem tipo joystick: o ponto onde o gesto começou é o centro.

    Mover a mão para cima/baixo além da zona morta rola a página, mais rápido quanto
    mais longe do centro. Parada no centro, a página fica parada — não exige movimentos
    repetitivos, o que ajuda quem tem pouca amplitude ou tremor.
    Distâncias em tamanhos de mão; velocidade em "dentes" da roda por segundo.
    """

    def __init__(self, dead_zone: float = 0.12, full_range: float = 0.5,
                 max_speed: float = 12.0):
        self.dead_zone = dead_zone
        self.full_range = full_range
        self.max_speed = max_speed
        self.reset()

    def reset(self) -> None:
        self.anchor_y: float | None = None
        self._last_t: float | None = None
        self.offset = 0.0   # deslocamento atual (para desenhar)

    def update(self, y: float, hand_size: float, t: float) -> float:
        """Recebe o y normalizado da mão; devolve quantos dentes rolar neste quadro
        (positivo = para cima, como a roda do mouse)."""
        if self.anchor_y is None or hand_size < 1e-6:
            self.anchor_y, self._last_t, self.offset = y, t, 0.0
            return 0.0
        dt = max(t - self._last_t, 0.0)
        self._last_t = t
        # y da imagem cresce para baixo: mão acima do centro = offset positivo = rola para cima
        self.offset = (self.anchor_y - y) / hand_size
        excess = abs(self.offset) - self.dead_zone
        if excess <= 0:
            return 0.0
        level = min(excess / (self.full_range - self.dead_zone), 1.0)
        return math.copysign(level * self.max_speed * dt, self.offset)


# ----------------------------------------------------------------------------
class ExtraPinches:
    """Pinças do polegar com o médio (clique direito) e com o anelar (clique duplo).

    Só conta a pinça do dedo mais perto do polegar: ao tocar o médio, o indicador
    costuma chegar perto também, e isso não pode virar outro clique.
    """

    ACTIONS = {"middle": "right", "ring": "double"}

    def __init__(self, on: float = 0.25, off: float = 0.35):
        self.pinches = {finger: PinchClicker(on, off, freeze=on) for finger in self.ACTIONS}

    def reset(self) -> None:
        for p in self.pinches.values():
            p.reset()

    @property
    def pressed(self) -> bool:
        return any(p.pressed for p in self.pinches.values())

    def update(self, ratios: dict[str, float], t: float) -> str | None:
        """Devolve "right", "double" ou None."""
        closest = min(ratios, key=ratios.get)
        action = None
        for finger, pinch in self.pinches.items():
            # fora do dedo mais próximo, a pinça é vista como aberta (exceto se já fechada)
            ratio = ratios[finger] if (finger == closest or pinch.pressed) else math.inf
            if pinch.update(ratio, t) == ClickEvent.DOWN:
                action = self.ACTIONS[finger]
        return action

    def blocks_left(self, ratios: dict[str, float]) -> bool:
        """True quando a pinça esquerda deve ser ignorada (outro dedo está mais perto)."""
        return self.pressed or min(ratios, key=ratios.get) != "index"


# ----------------------------------------------------------------------------
DWELL_ACTIONS = ("left", "double", "right", "middle", "drag")
DWELL_ACTION_LABELS = {"left": "esquerdo", "double": "duplo", "right": "direito",
                       "middle": "meio", "drag": "arrastar"}


class DwellActionSelector:
    """Tipo do próximo clique por permanência.

    Duplo, direito e meio valem para um clique e voltam ao esquerdo (como as
    ferramentas de clique por permanência costumam fazer). Arrastar usa duas
    permanências: a primeira segura o botão, a segunda solta.
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.action = "left"
        self.dragging = False

    def cycle(self) -> str:
        if not self.dragging:
            i = DWELL_ACTIONS.index(self.action)
            self.action = DWELL_ACTIONS[(i + 1) % len(DWELL_ACTIONS)]
        return self.action

    def on_dwell(self) -> str:
        """Chamado a cada clique por permanência; devolve o que fazer:
        "left", "double", "right", "middle", "press" ou "release"."""
        action = self.action
        if action == "drag":
            if self.dragging:
                self.dragging = False
                self.action = "left"
                return "release"
            self.dragging = True
            return "press"
        self.action = "left"
        return action
