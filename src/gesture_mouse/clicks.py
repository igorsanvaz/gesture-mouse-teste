"""Detecção de clique: por pinça (polegar + indicador) e por permanência (dwell).

Os detectores não clicam sozinhos: retornam eventos que o app repassa ao sistema.
Assim eles podem ser testados sem mouse real.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class ClickEvent(Enum):
    NONE = "none"
    DOWN = "down"     # botão pressionado (pinça fechou)
    UP = "up"         # botão solto (pinça abriu)
    CLICK = "click"   # clique completo (permanência)


# Índices dos pontos do MediaPipe Hands
WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_TIP = 8
MIDDLE_MCP = 9


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def pinch_ratio(landmarks) -> float:
    """Distância polegar–indicador dividida pelo tamanho da mão (punho → base do médio).

    Normalizar pelo tamanho da mão torna o limiar independente da distância da câmera.
    `landmarks` é uma sequência de pontos (x, y) normalizados.
    """
    hand_size = _dist(landmarks[WRIST], landmarks[MIDDLE_MCP])
    if hand_size < 1e-6:
        return float("inf")
    return _dist(landmarks[THUMB_TIP], landmarks[INDEX_TIP]) / hand_size


# ----------------------------------------------------------------------------
class PinchClicker:
    """Pinça com histerese: fecha abaixo de `on`, só reabre acima de `off`.

    A histerese evita cliques repetidos quando a distância oscila perto do limiar,
    o que é comum com tremor. `freeze` indica quando o cursor deve parar de se mover
    porque o usuário está prestes a clicar.
    """

    def __init__(self, on: float = 0.25, off: float = 0.35, freeze: float = 0.45,
                 min_hold_s: float = 0.05, freeze_after_press_s: float = 0.3):
        if not on < off:
            raise ValueError("pinch_on deve ser menor que pinch_off")
        self.on = on
        self.off = off
        self.freeze = freeze
        self.min_hold_s = min_hold_s  # tempo mínimo fechada para contar (anti-ruído)
        # após fechar a pinça, o cursor fica parado por um instante (clique preciso);
        # se a pinça continuar fechada, o movimento volta e permite arrastar
        self.freeze_after_press_s = freeze_after_press_s
        self.reset()

    def reset(self) -> None:
        self.pressed = False
        self._closing_since: float | None = None
        self._pressed_at: float | None = None
        self.last_ratio = float("inf")

    def should_freeze(self, t: float) -> bool:
        if self.pressed:
            return self._pressed_at is not None and t - self._pressed_at < self.freeze_after_press_s
        return self.last_ratio < self.freeze

    def update(self, ratio: float, t: float) -> ClickEvent:
        self.last_ratio = ratio
        if not self.pressed:
            if ratio < self.on:
                if self._closing_since is None:
                    self._closing_since = t
                if t - self._closing_since >= self.min_hold_s:
                    self.pressed = True
                    self._pressed_at = t
                    self._closing_since = None
                    return ClickEvent.DOWN
            else:
                self._closing_since = None
        else:
            if ratio > self.off:
                self.pressed = False
                return ClickEvent.UP
        return ClickEvent.NONE


# ----------------------------------------------------------------------------
@dataclass
class DwellState:
    progress: float = 0.0           # 0–1, para desenhar o indicador
    anchor: tuple[float, float] | None = None
    armed: bool = True


class DwellClicker:
    """Clique por permanência.

    O clique acontece quando o cursor fica dentro de um círculo de raio `radius` (px)
    por `dwell_time` segundos. Depois de clicar, o detector só volta a armar quando o
    cursor se afasta `rearm_distance` px do ponto clicado — isso impede cliques em
    sequência quando o usuário simplesmente deixa a mão parada.
    """

    def __init__(self, dwell_time: float = 1.0, radius: float = 30.0,
                 rearm_distance: float = 60.0):
        self.dwell_time = dwell_time
        self.radius = radius
        self.rearm_distance = rearm_distance
        self.reset()

    def reset(self) -> None:
        self.state = DwellState()
        self._start_t: float | None = None
        self._last_click_pos: tuple[float, float] | None = None

    def update(self, x: float, y: float, t: float) -> ClickEvent:
        s = self.state
        pos = (x, y)

        if not s.armed:
            if self._last_click_pos is None or _dist(pos, self._last_click_pos) >= self.rearm_distance:
                s.armed = True
                s.anchor = pos
                self._start_t = t
            s.progress = 0.0
            return ClickEvent.NONE

        if s.anchor is None or _dist(pos, s.anchor) > self.radius:
            # saiu do círculo: recomeça a contagem a partir daqui
            s.anchor = pos
            self._start_t = t
            s.progress = 0.0
            return ClickEvent.NONE

        elapsed = t - (self._start_t if self._start_t is not None else t)
        s.progress = min(elapsed / self.dwell_time, 1.0)
        if elapsed >= self.dwell_time:
            s.armed = False
            s.progress = 0.0
            self._last_click_pos = s.anchor
            s.anchor = None
            return ClickEvent.CLICK
        return ClickEvent.NONE
