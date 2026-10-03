"""Comparação offline dos filtros com tremor sintético (Seção 4.2 do plano de trabalho).

Gera trajetórias de apontamento artificiais (movimentos de jerk mínimo entre alvos,
com pausas sobre cada alvo), soma tremor senoidal e ruído de rastreamento, amostra a
~30 quadros/s com variação de tempo e mede, para cada filtro:

  - tremor residual (px): RMS do erro enquanto a mão "deveria" estar parada
  - erro em movimento (px): RMS do erro durante os deslocamentos
  - atraso (ms): deslocamento temporal que melhor alinha a saída à trajetória real

Uso:
    python tools/filter_benchmark.py
    python tools/filter_benchmark.py --tremor-px 12 --freq 5 --grafico resultados.png
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gesture_mouse.config import FilterConfig  # noqa: E402
from gesture_mouse.filters import FILTER_KINDS, make_filter  # noqa: E402


def min_jerk(p0: np.ndarray, p1: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Perfil de jerk mínimo (Flash e Hogan, 1985) para s em [0, 1]."""
    k = 10 * s ** 3 - 15 * s ** 4 + 6 * s ** 5
    return p0 + (p1 - p0) * k[:, None]


def synthetic_trajectory(n_moves: int, rng: random.Random, screen=(1920, 1080),
                         fps: float = 30.0, jitter: float = 0.15):
    """Retorna tempos (s), posições reais (px) e máscara 'parado'."""
    times, pts, still = [], [], []
    t = 0.0
    pos = np.array([screen[0] / 2, screen[1] / 2])
    for _ in range(n_moves):
        target = np.array([rng.uniform(100, screen[0] - 100), rng.uniform(100, screen[1] - 100)])
        dist = float(np.linalg.norm(target - pos))
        move_s = 0.35 + dist / 1500           # movimentos maiores levam mais tempo
        hold_s = rng.uniform(0.8, 1.5)          # pausa sobre o alvo (como no clique por permanência)
        for phase, dur in (("move", move_s), ("hold", hold_s)):
            t_end = t + dur
            while t < t_end:
                if phase == "move":
                    s = np.array([(t - (t_end - dur)) / dur])
                    p = min_jerk(pos, target, s)[0]
                else:
                    p = target
                times.append(t)
                pts.append(p.copy())
                still.append(phase == "hold" and t - (t_end - dur) > 0.25)
                t += (1 / fps) * (1 + rng.uniform(-jitter, jitter))
        pos = target
    return np.array(times), np.array(pts), np.array(still)


def add_tremor(times, pts, freq, amp_px, noise_px, rng: np.random.Generator):
    w = 2 * math.pi * freq * times
    tremor = np.stack([amp_px * np.sin(w), amp_px * np.sin(w + math.pi / 3)], axis=1)
    noise = rng.normal(0, noise_px, size=pts.shape)
    return pts + tremor + noise


def estimate_lag_ms(times, truth, out, max_ms=300, step_ms=2) -> float:
    """Atraso que minimiza o erro entre a saída e a trajetória real deslocada no tempo."""
    best, best_err = 0.0, float("inf")
    for lag_ms in range(0, max_ms + 1, step_ms):
        shifted_t = times - lag_ms / 1000
        valid = shifted_t >= times[0]
        tx = np.interp(shifted_t[valid], times, truth[:, 0])
        ty = np.interp(shifted_t[valid], times, truth[:, 1])
        err = np.mean((out[valid, 0] - tx) ** 2 + (out[valid, 1] - ty) ** 2)
        if err < best_err:
            best, best_err = lag_ms, err
    return float(best)


def run(args) -> list[dict]:
    rng = random.Random(args.semente)
    nrng = np.random.default_rng(args.semente)
    times, truth, still = synthetic_trajectory(args.movimentos, rng)
    noisy = add_tremor(times, truth, args.freq, args.tremor_px, args.ruido_px, nrng)
    cfg = FilterConfig()
    results = []
    outputs = {}
    for kind in FILTER_KINDS:
        f = make_filter(kind, cfg)
        out = np.array([f.filter(x, y, t) for (x, y), t in zip(noisy, times)])
        outputs[kind] = out
        err = np.linalg.norm(out - truth, axis=1)
        results.append(dict(
            filtro=kind,
            tremor_residual_px=float(np.sqrt(np.mean(err[still] ** 2))),
            erro_movimento_px=float(np.sqrt(np.mean(err[~still] ** 2))),
            atraso_ms=estimate_lag_ms(times, truth, out),
        ))
    raw_err = np.linalg.norm(noisy - truth, axis=1)
    print(f"\nEntrada: tremor {args.tremor_px} px a {args.freq} Hz + ruído {args.ruido_px} px; "
          f"{len(times)} amostras; tremor bruto parado = {np.sqrt(np.mean(raw_err[still] ** 2)):.2f} px\n")
    print(f"{'filtro':<16}{'tremor residual (px)':>22}{'erro em movimento (px)':>25}{'atraso (ms)':>14}")
    for r in results:
        print(f"{r['filtro']:<16}{r['tremor_residual_px']:>22.2f}{r['erro_movimento_px']:>25.2f}{r['atraso_ms']:>14.0f}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)
        print(f"\nCSV salvo em {args.csv}")
    if args.grafico:
        plot(times, truth, noisy, outputs, args.grafico)
    return results


def plot(times, truth, noisy, outputs, path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    end = np.searchsorted(times, min(times[-1], 6.0))
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(times[:end], noisy[:end, 0], color="#bbbbbb", lw=1, label="com tremor")
    ax.plot(times[:end], truth[:end, 0], color="black", lw=2, label="trajetória real")
    for kind, color in zip(("moving_average", "kalman", "one_euro"), ("#e07b39", "#3a7dc9", "#2e9e5b")):
        ax.plot(times[:end], outputs[kind][:end, 0], lw=1.6, color=color, label=kind)
    ax.set_xlabel("tempo (s)")
    ax.set_ylabel("posição x do cursor (px)")
    ax.legend(frameon=False, ncol=3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Gráfico salvo em {path}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Benchmark dos filtros de suavização")
    p.add_argument("--tremor-px", type=float, default=10.0, help="amplitude do tremor (px)")
    p.add_argument("--freq", type=float, default=5.0, help="frequência do tremor (Hz)")
    p.add_argument("--ruido-px", type=float, default=2.0, help="ruído de rastreamento (desvio-padrão, px)")
    p.add_argument("--movimentos", type=int, default=40, help="número de movimentos simulados")
    p.add_argument("--semente", type=int, default=42)
    p.add_argument("--csv", help="salva o resultado em CSV")
    p.add_argument("--grafico", help="salva um gráfico PNG (requer matplotlib)")
    return p.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
