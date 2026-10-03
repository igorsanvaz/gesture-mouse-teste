"""Filtros de suavização da posição do cursor.

Todos os filtros trabalham em 2D (x, y) e recebem o instante da amostra em segundos,
pois a taxa de quadros da webcam varia. A interface comum é:

    filtro.filter(x, y, t) -> (x_filtrado, y_filtrado)
    filtro.reset()

Filtros implementados (comparados no TCC):
    - NoFilter: sem suavização (referência)
    - MovingAverageFilter: média das últimas N amostras
    - KalmanFilter2D: Kalman com modelo de velocidade constante (Kalman, 1960)
    - OneEuroFilter2D: passa-baixas de corte adaptativo (Casiez, Roussel e Vogel, 2012)
"""

from __future__ import annotations

import math
from collections import deque
from typing import Protocol


class PointFilter(Protocol):
    name: str

    def filter(self, x: float, y: float, t: float) -> tuple[float, float]: ...

    def reset(self) -> None: ...


# ----------------------------------------------------------------------------
class NoFilter:
    name = "none"

    def filter(self, x: float, y: float, t: float) -> tuple[float, float]:
        return x, y

    def reset(self) -> None:
        pass


# ----------------------------------------------------------------------------
class MovingAverageFilter:
    name = "moving_average"

    def __init__(self, window: int = 5):
        if window < 1:
            raise ValueError("window deve ser >= 1")
        self.window = window
        self._xs: deque[float] = deque(maxlen=window)
        self._ys: deque[float] = deque(maxlen=window)

    def filter(self, x: float, y: float, t: float) -> tuple[float, float]:
        self._xs.append(x)
        self._ys.append(y)
        return sum(self._xs) / len(self._xs), sum(self._ys) / len(self._ys)

    def reset(self) -> None:
        self._xs.clear()
        self._ys.clear()


# ----------------------------------------------------------------------------
class _Kalman1D:
    """Kalman de velocidade constante para um eixo. Estado: [posição, velocidade]."""

    def __init__(self, process_noise: float, measurement_noise: float):
        self.q = process_noise
        self.r = measurement_noise
        self.reset()

    def reset(self) -> None:
        self.initialized = False
        self.x = 0.0      # posição
        self.v = 0.0      # velocidade
        # covariância P (2x2)
        self.p00, self.p01, self.p10, self.p11 = 1.0, 0.0, 0.0, 1.0

    def update(self, z: float, dt: float) -> float:
        if not self.initialized:
            self.x, self.v = z, 0.0
            self.initialized = True
            return z
        # --- predição: x' = F x,  P' = F P F^T + Q  (F = [[1, dt], [0, 1]])
        x_pred = self.x + self.v * dt
        v_pred = self.v
        p00 = self.p00 + dt * (self.p10 + self.p01) + dt * dt * self.p11
        p01 = self.p01 + dt * self.p11
        p10 = self.p10 + dt * self.p11
        p11 = self.p11
        # ruído de processo para aceleração aleatória (modelo de aceleração branca)
        q = self.q
        p00 += q * dt ** 4 / 4
        p01 += q * dt ** 3 / 2
        p10 += q * dt ** 3 / 2
        p11 += q * dt ** 2
        # --- correção (medimos só a posição, H = [1, 0])
        s = p00 + self.r
        k0 = p00 / s
        k1 = p10 / s
        y = z - x_pred
        self.x = x_pred + k0 * y
        self.v = v_pred + k1 * y
        self.p00 = (1 - k0) * p00
        self.p01 = (1 - k0) * p01
        self.p10 = p10 - k1 * p00
        self.p11 = p11 - k1 * p01
        return self.x


class KalmanFilter2D:
    name = "kalman"

    def __init__(self, process_noise: float = 1.0e6, measurement_noise: float = 100.0):
        self._kx = _Kalman1D(process_noise, measurement_noise)
        self._ky = _Kalman1D(process_noise, measurement_noise)
        self._last_t: float | None = None

    def filter(self, x: float, y: float, t: float) -> tuple[float, float]:
        dt = 1 / 30 if self._last_t is None else max(t - self._last_t, 1e-3)
        self._last_t = t
        return self._kx.update(x, dt), self._ky.update(y, dt)

    def reset(self) -> None:
        self._kx.reset()
        self._ky.reset()
        self._last_t = None


# ----------------------------------------------------------------------------
def _smoothing_factor(cutoff: float, dt: float) -> float:
    """alpha = 1 / (1 + 1 / (2*pi*fc*Te)) — Equação (2) do plano de trabalho."""
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class _OneEuro1D:
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self.x_prev: float | None = None
        self.dx_prev = 0.0

    def update(self, x: float, dt: float) -> float:
        if self.x_prev is None:
            self.x_prev = x
            return x
        # derivada filtrada (velocidade)
        dx = (x - self.x_prev) / dt
        a_d = _smoothing_factor(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev
        # frequência de corte adaptativa — Equação (3)
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = _smoothing_factor(cutoff, dt)
        # passa-baixas exponencial — Equação (1)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        return x_hat


class OneEuroFilter2D:
    name = "one_euro"

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.01, d_cutoff: float = 1.0):
        self._fx = _OneEuro1D(min_cutoff, beta, d_cutoff)
        self._fy = _OneEuro1D(min_cutoff, beta, d_cutoff)
        self._last_t: float | None = None

    def filter(self, x: float, y: float, t: float) -> tuple[float, float]:
        dt = 1 / 30 if self._last_t is None else max(t - self._last_t, 1e-3)
        self._last_t = t
        return self._fx.update(x, dt), self._fy.update(y, dt)

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()
        self._last_t = None


# ----------------------------------------------------------------------------
FILTER_KINDS = ("none", "moving_average", "kalman", "one_euro")


def make_filter(kind: str, cfg=None) -> PointFilter:
    """Cria um filtro pelo nome. `cfg` é um FilterConfig (opcional)."""
    if kind == "none":
        return NoFilter()
    if kind == "moving_average":
        return MovingAverageFilter(window=getattr(cfg, "window", 5))
    if kind == "kalman":
        return KalmanFilter2D(
            process_noise=getattr(cfg, "process_noise", 1.0e6),
            measurement_noise=getattr(cfg, "measurement_noise", 100.0),
        )
    if kind == "one_euro":
        return OneEuroFilter2D(
            min_cutoff=getattr(cfg, "min_cutoff", 1.0),
            beta=getattr(cfg, "beta", 0.01),
            d_cutoff=getattr(cfg, "d_cutoff", 1.0),
        )
    raise ValueError(f"Filtro desconhecido: {kind!r}. Use um de {FILTER_KINDS}")
