"""Teste de apontamento multidirecional (ISO 9241-411) para comparar condições.

Funciona com qualquer dispositivo: mouse comum ou o controle por gestos rodando em
paralelo. Grava os cliques brutos e o resumo (throughput, tempo, erro) em CSV.

Exemplos:
    python tools/fitts_test.py --participante P01 --condicao mouse
    python tools/fitts_test.py --participante P01 --condicao gestos_1euro_dwell

Durante o teste: clique no alvo destacado (laranja). O primeiro clique de cada
sequência só inicia a contagem. ESC interrompe.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gesture_mouse.fitts import (  # noqa: E402
    Trial, analyze_sequence, circle_positions, iso_target_order,
)

BG = "#111418"
IDLE = "#3a4350"
ACTIVE = "#f28c28"
TEXT = "#e8e8e8"


class FittsTest:
    def __init__(self, root: tk.Tk, args: argparse.Namespace):
        self.root = root
        self.args = args
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.on_click)
        root.bind("<Escape>", lambda e: self.finish(aborted=True))

        self.conditions = [(a, w) for a in args.amplitudes for w in args.larguras]
        random.Random(args.semente).shuffle(self.conditions)
        self.cond_idx = -1
        self.raw_rows: list[dict] = []
        self.summary: list = []

        out = Path(args.saida)
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{args.participante}_{args.condicao}_{stamp}"
        self.raw_path = out / f"{base}_cliques.csv"
        self.summary_path = out / f"{base}_resumo.csv"

        root.after(300, self.show_intro)

    # ------------------------------------------------------------------
    def show_intro(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        c.create_text(w / 2, h / 2 - 40, fill=TEXT, font=("Arial", 22),
                      text=f"Teste de apontamento — {self.args.condicao}")
        c.create_text(w / 2, h / 2 + 10, fill=TEXT, font=("Arial", 14),
                      text="Clique no alvo laranja o mais rápido e preciso possível.\n"
                           "Clique em qualquer lugar para começar. ESC encerra.",
                      justify="center")
        self.state = "intro"

    def next_condition(self) -> None:
        self.cond_idx += 1
        if self.cond_idx >= len(self.conditions):
            self.finish()
            return
        self.amplitude, self.width = self.conditions[self.cond_idx]
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.positions = circle_positions(self.args.alvos, self.amplitude, w / 2, h / 2)
        order = iso_target_order(self.args.alvos)
        # começa no alvo 0 (não contado) e volta a ele no fim: n seleções medidas
        self.sequence = order[1:] + [order[0]]
        self.step = -1            # -1 = aguardando o clique inicial no alvo 0
        self.current = order[0]
        self.prev_pos = self.positions[order[0]]
        self.trials: list[Trial] = []
        self.state = "running"
        self.draw()

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        r = self.width / 2
        for i, (x, y) in enumerate(self.positions):
            color = ACTIVE if i == self.current else IDLE
            c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")
        c.create_text(12, 12, anchor="nw", fill="#8a94a3", font=("Arial", 11),
                      text=f"Sequência {self.cond_idx + 1}/{len(self.conditions)}  "
                           f"A={self.amplitude:.0f}px  W={self.width:.0f}px")
        if self.step == -1:
            c.create_text(c.winfo_width() / 2, c.winfo_height() / 2, fill=TEXT,
                          font=("Arial", 14), text="Clique no alvo laranja para iniciar")

    # ------------------------------------------------------------------
    def on_click(self, event) -> None:
        if self.state == "intro":
            self.next_condition()
            return
        if self.state != "running":
            return
        now = time.perf_counter()
        tx, ty = self.positions[self.current]
        hit = (event.x - tx) ** 2 + (event.y - ty) ** 2 <= (self.width / 2) ** 2

        if self.step == -1:
            if not hit:
                return  # o início exige acertar o alvo 0
            self.t_prev = now
            self.prev_pos = (tx, ty)
        else:
            trial = Trial(from_xy=self.prev_pos, target_xy=(tx, ty), click_xy=(event.x, event.y),
                          movement_time_s=now - self.t_prev, hit=hit)
            self.trials.append(trial)
            self.raw_rows.append(dict(
                participante=self.args.participante, condicao=self.args.condicao,
                sequencia=self.cond_idx + 1, amplitude_px=self.amplitude, largura_px=self.width,
                tentativa=self.step + 1, origem_x=f"{self.prev_pos[0]:.1f}", origem_y=f"{self.prev_pos[1]:.1f}",
                alvo_x=f"{tx:.1f}", alvo_y=f"{ty:.1f}", clique_x=event.x, clique_y=event.y,
                tempo_s=f"{trial.movement_time_s:.4f}", acerto=int(hit),
            ))
            self.t_prev = now
            # a próxima origem é o centro do alvo atual (convenção da ISO)
            self.prev_pos = (tx, ty)

        self.step += 1
        if self.step >= len(self.sequence):
            res = analyze_sequence(self.trials, self.amplitude, self.width)
            self.summary.append(res)
            print(f"A={res.amplitude:.0f} W={res.width:.0f}: TP={res.tp:.2f} bits/s, "
                  f"MT={res.mt_s * 1000:.0f} ms, erro={res.error_rate:.0%}")
            self.next_condition()
            return
        self.current = self.sequence[self.step]
        self.draw()

    # ------------------------------------------------------------------
    def finish(self, aborted: bool = False) -> None:
        self.state = "done"
        if self.raw_rows:
            with self.raw_path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(self.raw_rows[0].keys()))
                w.writeheader()
                w.writerows(self.raw_rows)
        if self.summary:
            with self.summary_path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["participante", "condicao", "amplitude_px", "largura_px", "id_nominal_bits",
                            "n", "mt_ms", "taxa_erro", "ae_px", "we_px", "ide_bits", "tp_bits_s"])
                for r in self.summary:
                    w.writerow([self.args.participante, self.args.condicao, r.amplitude, r.width,
                                f"{r.id_nominal:.3f}", r.n, f"{r.mt_s * 1000:.1f}", f"{r.error_rate:.3f}",
                                f"{r.ae:.1f}", f"{r.we:.1f}", f"{r.ide:.3f}", f"{r.tp:.3f}"])
            tp_mean = sum(r.tp for r in self.summary) / len(self.summary)
            print(f"\nThroughput médio ({self.args.condicao}): {tp_mean:.2f} bits/s")
            print(f"Arquivos: {self.raw_path}\n          {self.summary_path}")
        if aborted:
            print("Teste interrompido.")
        self.root.destroy()


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Teste de Fitts (ISO 9241-411)")
    p.add_argument("--participante", required=True, help="código do participante, ex.: P01")
    p.add_argument("--condicao", required=True, help="nome da condição, ex.: mouse, gestos_1euro_dwell")
    p.add_argument("--amplitudes", type=float, nargs="+", default=[300, 600], help="diâmetros do círculo (px)")
    p.add_argument("--larguras", type=float, nargs="+", default=[40, 80], help="diâmetros dos alvos (px)")
    p.add_argument("--alvos", type=int, default=13, help="número de alvos (ímpar)")
    p.add_argument("--semente", type=int, default=None, help="semente da ordem aleatória das sequências")
    p.add_argument("--saida", default="logs/fitts", help="pasta de saída")
    p.add_argument("--janela", action="store_true", help="roda em janela em vez de tela cheia")
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    root = tk.Tk()
    root.title("Teste de Fitts — TCC")
    root.configure(bg=BG)
    if args.janela:
        root.geometry("1280x800")
    else:
        root.attributes("-fullscreen", True)
    FittsTest(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
