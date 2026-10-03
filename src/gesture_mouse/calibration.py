"""Calibração da área de movimento de cada usuário.

Fluxo: contagem regressiva -> o usuário movimenta a mão, de forma confortável, até
os limites que consegue alcançar -> a caixa de controle é calculada a partir desses
pontos. Os extremos (percentis 3 e 97) são descartados para ignorar saltos do
rastreamento.
"""

from __future__ import annotations

from enum import Enum

import numpy as np

from .mapping import ControlBox


class CalibrationPhase(Enum):
    IDLE = "idle"
    COUNTDOWN = "countdown"
    RECORDING = "recording"
    DONE = "done"


class Calibrator:
    def __init__(self, countdown_s: float = 3.0, duration_s: float = 6.0,
                 margin: float = 0.03, low_pct: float = 3.0, high_pct: float = 97.0):
        self.countdown_s = countdown_s
        self.duration_s = duration_s
        self.margin = margin
        self.low_pct = low_pct
        self.high_pct = high_pct
        self.phase = CalibrationPhase.IDLE
        self.result: ControlBox | None = None
        self._t0 = 0.0
        self._xs: list[float] = []
        self._ys: list[float] = []

    @property
    def active(self) -> bool:
        return self.phase in (CalibrationPhase.COUNTDOWN, CalibrationPhase.RECORDING)

    def start(self, t: float) -> None:
        self.phase = CalibrationPhase.COUNTDOWN
        self.result = None
        self._t0 = t
        self._xs.clear()
        self._ys.clear()

    def cancel(self) -> None:
        self.phase = CalibrationPhase.IDLE

    def update(self, t: float, point: tuple[float, float] | None) -> CalibrationPhase:
        """Recebe o ponto normalizado da mão (ou None se não detectada) a cada quadro."""
        if self.phase == CalibrationPhase.COUNTDOWN and t - self._t0 >= self.countdown_s:
            self.phase = CalibrationPhase.RECORDING
            self._t0 = t
        elif self.phase == CalibrationPhase.RECORDING:
            if point is not None:
                self._xs.append(point[0])
                self._ys.append(point[1])
            if t - self._t0 >= self.duration_s:
                self._finish()
        return self.phase

    def _finish(self) -> None:
        if len(self._xs) < 10:
            # mão quase não foi vista: mantém a configuração anterior
            self.phase = CalibrationPhase.IDLE
            self.result = None
            return
        xs = np.asarray(self._xs)
        ys = np.asarray(self._ys)
        x_lo, x_hi = np.percentile(xs, [self.low_pct, self.high_pct])
        y_lo, y_hi = np.percentile(ys, [self.low_pct, self.high_pct])
        self.result = ControlBox.from_points(
            [float(x_lo), float(x_hi)], [float(y_lo), float(y_hi)], margin=self.margin
        )
        self.phase = CalibrationPhase.DONE

    def message(self, t: float) -> str:
        if self.phase == CalibrationPhase.COUNTDOWN:
            left = max(0.0, self.countdown_s - (t - self._t0))
            return f"Calibracao em {left:.0f}s: posicione a mao confortavelmente"
        if self.phase == CalibrationPhase.RECORDING:
            left = max(0.0, self.duration_s - (t - self._t0))
            return f"Mova a mao ate os limites confortaveis ({left:.0f}s)"
        return ""

    @property
    def points(self) -> list[tuple[float, float]]:
        return list(zip(self._xs, self._ys))
