"""Métricas de desempenho e registro de sessão em CSV.

O CSV de cada sessão alimenta a avaliação técnica (Seção 4.4 do plano de trabalho):
taxa de quadros, tempo de processamento por quadro e trajetória bruta x filtrada.
"""

from __future__ import annotations

import csv
import time
from collections import deque
from datetime import datetime
from pathlib import Path


class FpsMeter:
    """Média móvel da taxa de quadros (quadros/s)."""

    def __init__(self, window: int = 30):
        self._times: deque[float] = deque(maxlen=window)

    def tick(self, t: float) -> float:
        self._times.append(t)
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0


class SessionLogger:
    FIELDS = (
        "t_s", "hand", "raw_x", "raw_y", "filt_x", "filt_y",
        "pinch_ratio", "event", "fps", "proc_ms", "filter", "click_mode", "tremor",
        "gesture", "scroll",
    )

    def __init__(self, directory: str | Path, enabled: bool = True):
        self.enabled = enabled
        self.path: Path | None = None
        self._fh = None
        self._writer = None
        if not enabled:
            return
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = directory / f"sessao_{stamp}.csv"
        self._fh = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=self.FIELDS)
        self._writer.writeheader()
        self._t0 = time.perf_counter()

    def log(self, **row) -> None:
        if not self._writer:
            return
        row.setdefault("t_s", time.perf_counter() - self._t0)
        for key in ("t_s", "raw_x", "raw_y", "filt_x", "filt_y", "pinch_ratio", "fps", "proc_ms", "scroll"):
            if isinstance(row.get(key), float):
                row[key] = f"{row[key]:.4f}"
        self._writer.writerow({k: row.get(k, "") for k in self.FIELDS})

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None
            self._writer = None
