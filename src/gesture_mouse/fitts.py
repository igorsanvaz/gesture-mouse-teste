"""Cálculos da Lei de Fitts conforme ISO 9241-411 e Soukoreff e MacKenzie (2004).

    TP   = IDe / MT                      (bits/s)
    IDe  = log2(De / We + 1)             (bits)
    We   = 4,133 * SDx                   (px)

SDx é o desvio-padrão dos pontos de seleção projetados sobre o eixo da tarefa
(origem -> alvo); De é a média das distâncias efetivamente percorridas ao longo desse
eixo. O throughput é calculado por sequência (mesma distância A e largura W) e depois
promediado — o "mean of means" recomendado pelos autores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, stdev


@dataclass
class Trial:
    from_xy: tuple[float, float]     # centro do alvo de origem (px)
    target_xy: tuple[float, float]   # centro do alvo pedido (px)
    click_xy: tuple[float, float]    # onde o usuário clicou (px)
    movement_time_s: float           # tempo desde a seleção anterior (s)
    hit: bool                        # clique dentro do alvo?


@dataclass
class SequenceResult:
    amplitude: float
    width: float
    n: int
    mt_s: float
    error_rate: float
    ae: float
    we: float
    ide: float
    tp: float
    id_nominal: float


def project_on_axis(trial: Trial) -> tuple[float, float]:
    """Retorna (dx, distância percorrida) ao longo do eixo origem -> alvo.

    dx é o desvio da seleção em relação ao centro do alvo, medido ao longo do eixo
    (positivo = passou do alvo, negativo = ficou antes).
    """
    fx, fy = trial.from_xy
    tx, ty = trial.target_xy
    cx, cy = trial.click_xy
    ax, ay = tx - fx, ty - fy
    a = math.hypot(ax, ay)
    if a == 0:
        return 0.0, 0.0
    ux, uy = ax / a, ay / a
    along = (cx - fx) * ux + (cy - fy) * uy   # projeção da seleção no eixo
    return along - a, along


def analyze_sequence(trials: list[Trial], amplitude: float, width: float) -> SequenceResult:
    if len(trials) < 2:
        raise ValueError("São necessárias pelo menos 2 seleções por sequência")
    dxs, dists = zip(*(project_on_axis(t) for t in trials))
    sdx = stdev(dxs)
    we = 4.133 * sdx
    ae = mean(dists)
    ide = math.log2(ae / we + 1) if we > 0 else float("nan")
    mt = mean(t.movement_time_s for t in trials)
    errors = sum(not t.hit for t in trials)
    return SequenceResult(
        amplitude=amplitude, width=width, n=len(trials), mt_s=mt,
        error_rate=errors / len(trials), ae=ae, we=we, ide=ide,
        tp=ide / mt if mt > 0 else float("nan"),
        id_nominal=math.log2(amplitude / width + 1),
    )


def iso_target_order(n_targets: int) -> list[int]:
    """Ordem de seleção da tarefa multidirecional da ISO 9241-411.

    Os alvos ficam em círculo e a seleção alterna entre lados opostos:
    0 -> meio -> 1 -> meio+1 -> ... cobrindo todos os n alvos (n ímpar).
    """
    if n_targets % 2 == 0:
        raise ValueError("Use um número ímpar de alvos (ex.: 13)")
    half = (n_targets + 1) // 2
    return [(i * half) % n_targets for i in range(n_targets)]


def circle_positions(n_targets: int, amplitude: float, cx: float, cy: float) -> list[tuple[float, float]]:
    """Centros dos alvos em um círculo de diâmetro `amplitude`."""
    r = amplitude / 2
    return [
        (cx + r * math.cos(2 * math.pi * i / n_targets - math.pi / 2),
         cy + r * math.sin(2 * math.pi * i / n_targets - math.pi / 2))
        for i in range(n_targets)
    ]
