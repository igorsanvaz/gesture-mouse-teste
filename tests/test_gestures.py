"""Testes dos gestos de navegação (rolagem, cliques extras, tipo de clique por permanência)."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gesture_mouse.cursor import CursorController  # noqa: E402
from gesture_mouse.gestures import (DwellActionSelector, ExtraPinches, Posture,  # noqa: E402
                                    PostureDetector, ScrollController, classify_posture,
                                    finger_pinch_ratios, fingers_extended)


def make_hand(extended=("index", "middle", "ring", "pinky"), thumb=(0.35, 0.6)):
    """Mão sintética em pé: punho embaixo, dedos para cima (tamanho da mão = 0,2).

    Dedo esticado: ponta bem acima da articulação. Dobrado: ponta volta para a palma.
    """
    lms = [(0.5, 0.5)] * 21
    lms[0] = (0.5, 0.8)
    lms[4] = thumb
    for name, x, mcp, pip, tip in (("index", 0.44, 5, 6, 8), ("middle", 0.5, 9, 10, 12),
                                   ("ring", 0.56, 13, 14, 16), ("pinky", 0.62, 17, 18, 20)):
        lms[mcp] = (x, 0.6)
        lms[pip] = (x, 0.52)
        lms[pip + 1] = (x, 0.47)
        lms[tip] = (x, 0.42) if name in extended else (x, 0.62)
    return lms


class FingerTests(unittest.TestCase):
    def test_open_hand(self):
        self.assertTrue(all(fingers_extended(make_hand()).values()))

    def test_fist(self):
        self.assertFalse(any(fingers_extended(make_hand(extended=())).values()))

    def test_scroll_posture(self):
        self.assertEqual(classify_posture(make_hand(("index", "middle"))), Posture.SCROLL)
        self.assertEqual(classify_posture(make_hand()), Posture.POINT)
        self.assertEqual(classify_posture(make_hand(("index",))), Posture.POINT)

    def test_rotation_invariant(self):
        # mão deitada (girada 90°): continua reconhecida
        rotated = [(0.5 + (y - 0.5), 0.5 - (x - 0.5)) for x, y in make_hand(("index", "middle"))]
        self.assertEqual(classify_posture(rotated), Posture.SCROLL)

    def test_pinch_ratios(self):
        lms = make_hand(thumb=(0.5, 0.42))   # polegar na ponta do médio
        r = finger_pinch_ratios(lms)
        self.assertAlmostEqual(r["middle"], 0.0)
        self.assertLess(r["middle"], r["index"])
        self.assertLess(r["middle"], r["ring"])


class PostureDetectorTests(unittest.TestCase):
    def test_needs_hold_time(self):
        d = PostureDetector(hold_s=0.25)
        self.assertEqual(d.update(Posture.SCROLL, 0.0), Posture.POINT)
        self.assertEqual(d.update(Posture.SCROLL, 0.1), Posture.POINT)
        self.assertEqual(d.update(Posture.SCROLL, 0.3), Posture.SCROLL)

    def test_flicker_does_not_switch(self):
        d = PostureDetector(hold_s=0.25)
        for i in range(20):
            obs = Posture.SCROLL if i % 2 else Posture.POINT
            self.assertEqual(d.update(obs, i * 0.05), Posture.POINT)


class ScrollTests(unittest.TestCase):
    def test_dead_zone(self):
        s = ScrollController(dead_zone=0.12, full_range=0.5, max_speed=10)
        s.update(0.5, 0.2, 0.0)                   # define o centro
        self.assertEqual(s.update(0.48, 0.2, 0.1), 0.0)   # 0,1 mão: dentro da zona morta

    def test_direction_and_speed(self):
        s = ScrollController(dead_zone=0.12, full_range=0.5, max_speed=10)
        s.update(0.5, 0.2, 0.0)
        up = s.update(0.5 - 0.2, 0.2, 1.0)        # mão 1 tamanho acima: velocidade máxima por 1 s
        self.assertAlmostEqual(up, 10.0)
        down = s.update(0.5 + 0.06, 0.2, 2.0)     # 0,3 mão abaixo: velocidade parcial
        self.assertLess(down, 0)
        self.assertGreater(down, -10.0)

    def test_reset_recenters(self):
        s = ScrollController()
        s.update(0.5, 0.2, 0.0)
        s.reset()
        self.assertEqual(s.update(0.1, 0.2, 1.0), 0.0)   # novo centro, não rola


class ExtraPinchTests(unittest.TestCase):
    @staticmethod
    def ratios(index=1.0, middle=1.0, ring=1.0):
        return {"index": index, "middle": middle, "ring": ring}

    def test_right_and_double(self):
        p = ExtraPinches(on=0.25, off=0.35)
        for f in p.pinches.values():
            f.min_hold_s = 0.0
        self.assertEqual(p.update(self.ratios(middle=0.1), 0.0), "right")
        self.assertIsNone(p.update(self.ratios(middle=0.1), 0.1))   # mantida: não repete
        self.assertIsNone(p.update(self.ratios(), 0.2))             # abriu
        self.assertEqual(p.update(self.ratios(ring=0.1), 0.3), "double")

    def test_only_closest_finger_counts(self):
        p = ExtraPinches(on=0.25, off=0.35)
        for f in p.pinches.values():
            f.min_hold_s = 0.0
        # indicador mais perto que o médio: é clique esquerdo, não direito
        self.assertIsNone(p.update(self.ratios(index=0.05, middle=0.2), 0.0))
        self.assertFalse(p.blocks_left(self.ratios(index=0.05, middle=0.2)))
        self.assertTrue(p.blocks_left(self.ratios(index=0.2, middle=0.05)))


class DwellActionTests(unittest.TestCase):
    def test_one_shot_returns_to_left(self):
        d = DwellActionSelector()
        self.assertEqual(d.cycle(), "double")
        self.assertEqual(d.on_dwell(), "double")
        self.assertEqual(d.on_dwell(), "left")

    def test_drag_uses_two_dwells(self):
        d = DwellActionSelector()
        while d.action != "drag":
            d.cycle()
        self.assertEqual(d.on_dwell(), "press")
        self.assertTrue(d.dragging)
        self.assertEqual(d.cycle(), "drag")       # não troca no meio do arraste
        self.assertEqual(d.on_dwell(), "release")
        self.assertEqual(d.action, "left")

    def test_cycle_wraps(self):
        d = DwellActionSelector()
        for _ in range(5):
            d.cycle()
        self.assertEqual(d.action, "left")


class CursorScrollTests(unittest.TestCase):
    def test_fractions_accumulate(self):
        c = CursorController(dry_run=True)
        unit = 120 if sys.platform == "win32" else 1
        for _ in range(10):
            c.scroll(0.25)
        # o que sobrou é sempre menos de uma unidade da roda
        self.assertLess(abs(c._scroll_rest), 1 / unit + 1e-9)
        self.assertFalse(math.isnan(c._scroll_rest))


if __name__ == "__main__":
    unittest.main()
