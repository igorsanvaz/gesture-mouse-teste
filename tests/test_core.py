"""Testes dos módulos que não dependem de câmera.

Rodar:  python -m pytest      (ou)      python -m unittest discover tests
"""

import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gesture_mouse.calibration import CalibrationPhase, Calibrator  # noqa: E402
from gesture_mouse.clicks import ClickEvent, DwellClicker, PinchClicker, pinch_ratio  # noqa: E402
from gesture_mouse.config import AppConfig  # noqa: E402
from gesture_mouse.filters import FILTER_KINDS, make_filter  # noqa: E402
from gesture_mouse.fitts import Trial, analyze_sequence, iso_target_order  # noqa: E402
from gesture_mouse.mapping import ControlBox, image_to_screen  # noqa: E402
from gesture_mouse.tremor import TremorInjector  # noqa: E402


class FilterTests(unittest.TestCase):
    def test_constant_input_converges(self):
        for kind in FILTER_KINDS:
            f = make_filter(kind)
            for i in range(60):
                x, y = f.filter(500.0, 300.0, i / 30)
            self.assertAlmostEqual(x, 500.0, delta=0.5, msg=kind)
            self.assertAlmostEqual(y, 300.0, delta=0.5, msg=kind)

    def test_filters_reduce_tremor(self):
        tremor = TremorInjector(frequency_hz=5, amplitude=10, noise=0, seed=1)
        for kind in ("moving_average", "kalman", "one_euro"):
            f = make_filter(kind)
            devs = []
            for i in range(300):
                t = i / 30
                x, y = f.filter(*tremor.apply(500.0, 300.0, t), t)
                if i > 60:
                    devs.append(math.hypot(x - 500, y - 300))
            rms = math.sqrt(sum(d * d for d in devs) / len(devs))
            self.assertLess(rms, 7.0, msg=f"{kind} não reduziu o tremor (RMS={rms:.1f})")

    def test_reset(self):
        f = make_filter("one_euro")
        f.filter(0, 0, 0)
        f.reset()
        self.assertEqual(f.filter(100, 100, 1.0), (100, 100))

    def test_unknown_filter(self):
        with self.assertRaises(ValueError):
            make_filter("xyz")


class MappingTests(unittest.TestCase):
    def test_corners_and_center(self):
        box = ControlBox(0.2, 0.8, 0.3, 0.7)
        cases = [
            ((0.5, 0.5, 0), (500.0, 400.0)),   # centro da caixa -> centro da tela
            ((0.0, 0.0, 1), (1.0, 1.0)),       # fora da caixa: limitado à borda
            ((1.0, 1.0, 1), (999.0, 799.0)),
        ]
        for (nx, ny, edge), expected in cases:
            sx, sy = image_to_screen(nx, ny, box, 1001, 801, edge_px=edge)
            self.assertAlmostEqual(sx, expected[0], places=6)
            self.assertAlmostEqual(sy, expected[1], places=6)

    def test_from_points_respects_min_size(self):
        box = ControlBox.from_points([0.5, 0.51], [0.5, 0.51], margin=0.0, min_size=0.1)
        self.assertGreaterEqual(box.width, 0.1 - 1e-9)
        self.assertGreaterEqual(box.height, 0.1 - 1e-9)

    def test_invalid_box(self):
        with self.assertRaises(ValueError):
            ControlBox(0.6, 0.4, 0.1, 0.9)


class PinchTests(unittest.TestCase):
    @staticmethod
    def hand(gap):
        lms = [(0.5, 0.5)] * 21
        lms[0] = (0.5, 0.8)    # punho
        lms[9] = (0.5, 0.6)    # base do médio -> tamanho da mão 0.2
        lms[4] = (0.5, 0.5)    # polegar
        lms[8] = (0.5 + gap, 0.5)
        return lms

    def test_ratio_normalized(self):
        self.assertAlmostEqual(pinch_ratio(self.hand(0.05)), 0.25)

    def test_hysteresis(self):
        p = PinchClicker(on=0.25, off=0.35, min_hold_s=0.0)
        self.assertEqual(p.update(0.2, 0.0), ClickEvent.DOWN)
        self.assertEqual(p.update(0.30, 0.1), ClickEvent.NONE)   # entre on e off: segue pressionado
        self.assertEqual(p.update(0.24, 0.2), ClickEvent.NONE)   # não repete o DOWN
        self.assertEqual(p.update(0.40, 0.3), ClickEvent.UP)

    def test_min_hold_filters_glitch(self):
        p = PinchClicker(on=0.25, off=0.35, min_hold_s=0.05)
        self.assertEqual(p.update(0.1, 0.00), ClickEvent.NONE)
        self.assertEqual(p.update(0.5, 0.02), ClickEvent.NONE)   # abriu antes do tempo mínimo
        self.assertEqual(p.update(0.1, 0.10), ClickEvent.NONE)
        self.assertEqual(p.update(0.1, 0.16), ClickEvent.DOWN)

    def test_freeze(self):
        p = PinchClicker(on=0.25, off=0.35, freeze=0.45, min_hold_s=0.0, freeze_after_press_s=0.3)
        p.update(0.4, 0.0)
        self.assertTrue(p.should_freeze(0.0))
        p.update(0.2, 0.1)                    # pressionou
        self.assertTrue(p.should_freeze(0.2))
        self.assertFalse(p.should_freeze(0.5))  # pressionado há mais de 0,3 s: permite arrastar


class DwellTests(unittest.TestCase):
    def test_click_after_dwell_time(self):
        d = DwellClicker(dwell_time=1.0, radius=20, rearm_distance=50)
        events = [d.update(100 + (i % 3), 100, i * 0.1) for i in range(12)]
        self.assertEqual(events.count(ClickEvent.CLICK), 1)

    def test_no_repeat_without_moving(self):
        d = DwellClicker(dwell_time=0.5, radius=20, rearm_distance=50)
        events = [d.update(100, 100, i * 0.1) for i in range(40)]
        self.assertEqual(events.count(ClickEvent.CLICK), 1)

    def test_rearm_after_moving_away(self):
        d = DwellClicker(dwell_time=0.5, radius=20, rearm_distance=50)
        ev = [d.update(100, 100, i * 0.1) for i in range(10)]
        ev += [d.update(300, 100, 1.0 + i * 0.1) for i in range(10)]
        self.assertEqual(ev.count(ClickEvent.CLICK), 2)

    def test_moving_does_not_click(self):
        d = DwellClicker(dwell_time=0.5, radius=20)
        events = [d.update(i * 30, 0, i * 0.1) for i in range(30)]
        self.assertNotIn(ClickEvent.CLICK, events)


class CalibrationTests(unittest.TestCase):
    def test_box_from_recorded_motion(self):
        c = Calibrator(countdown_s=0.5, duration_s=2.0, margin=0.0)
        c.start(0.0)
        t = 0.0
        while c.phase in (CalibrationPhase.COUNTDOWN, CalibrationPhase.RECORDING):
            t += 1 / 30
            # movimento circular entre 0,3 e 0,7
            p = (0.5 + 0.2 * math.cos(t * 4), 0.5 + 0.2 * math.sin(t * 4))
            c.update(t, p)
        self.assertEqual(c.phase, CalibrationPhase.DONE)
        self.assertAlmostEqual(c.result.x_min, 0.3, delta=0.03)
        self.assertAlmostEqual(c.result.x_max, 0.7, delta=0.03)

    def test_fails_without_hand(self):
        c = Calibrator(countdown_s=0.1, duration_s=0.5)
        c.start(0.0)
        for i in range(30):
            c.update(i / 30, None)
        self.assertEqual(c.phase, CalibrationPhase.IDLE)
        self.assertIsNone(c.result)


class FittsTests(unittest.TestCase):
    def test_iso_order_visits_all(self):
        order = iso_target_order(13)
        self.assertEqual(sorted(order), list(range(13)))
        self.assertEqual(order[:3], [0, 7, 1])

    def test_throughput(self):
        # cliques perfeitos ao longo do eixo com dispersão conhecida
        offsets = [-4, -2, 0, 2, 4, -4, -2, 0, 2, 4]
        trials = [Trial((0, 0), (400, 0), (400 + d, 0), 1.0, True) for d in offsets]
        r = analyze_sequence(trials, amplitude=400, width=40)
        sdx = (sum(d * d for d in offsets) / (len(offsets) - 1)) ** 0.5
        we = 4.133 * sdx
        self.assertAlmostEqual(r.we, we, places=6)
        self.assertAlmostEqual(r.tp, math.log2(400 / we + 1), places=6)
        self.assertEqual(r.error_rate, 0.0)


class ConfigTests(unittest.TestCase):
    def test_roundtrip(self):
        cfg = AppConfig()
        cfg.filter.kind = "kalman"
        cfg.click.dwell_time = 1.4
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.json"
            cfg.save(path)
            loaded = AppConfig.load(path)
        self.assertEqual(loaded.filter.kind, "kalman")
        self.assertEqual(loaded.click.dwell_time, 1.4)

    def test_missing_file_gives_defaults(self):
        self.assertEqual(AppConfig.load("nao_existe.json").filter.kind, "one_euro")


if __name__ == "__main__":
    unittest.main()
