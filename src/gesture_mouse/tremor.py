"""Tremor sintético para os experimentos controlados.

Soma ao ponto rastreado uma oscilação senoidal nos dois eixos, com fase diferente em
cada um e um pequeno ruído, imitando o tremor de repouso/postural (4–6 Hz, faixa
típica do tremor parkinsoniano). Usado para medir quanto cada filtro estabiliza o
cursor sem depender de participantes do público-alvo.
"""

from __future__ import annotations

import math
import random


class TremorInjector:
    def __init__(self, frequency_hz: float = 5.0, amplitude: float = 0.01,
                 noise: float = 0.15, seed: int | None = None):
        self.frequency_hz = frequency_hz
        self.amplitude = amplitude      # mesma unidade das coordenadas de entrada
        self.noise = noise              # fração da amplitude como ruído aleatório
        self._rng = random.Random(seed)
        self._phase_y = math.pi / 3

    def offset(self, t: float) -> tuple[float, float]:
        w = 2 * math.pi * self.frequency_hz * t
        a = self.amplitude
        dx = a * math.sin(w) + a * self.noise * self._rng.gauss(0, 1)
        dy = a * math.sin(w + self._phase_y) + a * self.noise * self._rng.gauss(0, 1)
        return dx, dy

    def apply(self, x: float, y: float, t: float) -> tuple[float, float]:
        dx, dy = self.offset(t)
        return x + dx, y + dy
