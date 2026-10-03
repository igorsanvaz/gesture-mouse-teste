"""Mapeamento da posição da mão (imagem) para a posição do cursor (tela).

A mão raramente percorre a imagem inteira, principalmente em pessoas com amplitude
de movimento reduzida. Por isso, uma região menor da imagem (a "caixa de controle",
definida na calibração) é esticada para cobrir a tela toda.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ControlBox:
    """Região da imagem, em coordenadas normalizadas (0–1), que cobre a tela toda."""

    x_min: float = 0.25
    x_max: float = 0.75
    y_min: float = 0.25
    y_max: float = 0.75

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not (0.0 <= self.x_min < self.x_max <= 1.0):
            raise ValueError(f"Limites x inválidos: {self.x_min}, {self.x_max}")
        if not (0.0 <= self.y_min < self.y_max <= 1.0):
            raise ValueError(f"Limites y inválidos: {self.y_min}, {self.y_max}")

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @classmethod
    def from_points(cls, xs, ys, margin: float = 0.03, min_size: float = 0.08) -> "ControlBox":
        """Cria a caixa a partir dos pontos percorridos na calibração.

        `margin` (fração da imagem) é retirada de cada lado da área percorrida, para que
        o usuário alcance as bordas da tela sem precisar ir ao limite do próprio
        movimento. `min_size` evita caixas minúsculas, que deixariam o cursor sensível
        demais.
        """
        if len(xs) == 0 or len(ys) == 0:
            raise ValueError("Calibração sem pontos")
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        # garante tamanho mínimo, crescendo a partir do centro
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        half_w = max((x1 - x0) / 2, min_size / 2)
        half_h = max((y1 - y0) / 2, min_size / 2)
        # margem deixa a área um pouco MENOR que a percorrida: o usuário alcança
        # as bordas da tela sem precisar ir ao limite do próprio movimento
        half_w = max(half_w - margin, min_size / 2)
        half_h = max(half_h - margin, min_size / 2)
        return cls(
            x_min=max(0.0, cx - half_w),
            x_max=min(1.0, cx + half_w),
            y_min=max(0.0, cy - half_h),
            y_max=min(1.0, cy + half_h),
        )


def image_to_screen(
    nx: float, ny: float, box: ControlBox, screen_w: int, screen_h: int, edge_px: int = 1
) -> tuple[float, float]:
    """Converte um ponto normalizado da imagem em coordenadas de tela (px).

    O resultado é limitado a [edge_px, tamanho - 1 - edge_px] para nunca encostar nos
    cantos exatos da tela (alguns sistemas tratam o canto como gesto especial).
    """
    u = (nx - box.x_min) / box.width
    v = (ny - box.y_min) / box.height
    u = min(max(u, 0.0), 1.0)
    v = min(max(v, 0.0), 1.0)
    sx = edge_px + u * (screen_w - 1 - 2 * edge_px)
    sy = edge_px + v * (screen_h - 1 - 2 * edge_px)
    return sx, sy
