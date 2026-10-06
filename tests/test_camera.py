"""Testes da câmera "conecte e use" (sem hardware: abertura e rede são simuladas)."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gesture_mouse import camera  # noqa: E402
from gesture_mouse.camera import (CameraManager, candidate_order, frame_looks_valid,  # noqa: E402
                                  frames_differ, parse_source, phone_urls, rotate_after,
                                  subnet_hosts)


class FakeCap:
    def __init__(self, source, frames=1000):
        self.source, self.frames, self.released = source, frames, False

    def read(self):
        if self.frames <= 0:
            return False, None
        self.frames -= 1
        return True, np.random.randint(0, 255, (4, 4, 3), np.uint8)

    def release(self):
        self.released = True


class PureFunctionTests(unittest.TestCase):
    def test_flat_frames_are_invalid(self):
        green = np.zeros((48, 64, 3), np.uint8)
        green[:, :, 1] = 135                      # o verde chapado da câmera virtual sem sinal
        self.assertFalse(frame_looks_valid(green))
        self.assertFalse(frame_looks_valid(np.zeros((48, 64, 3), np.uint8)))
        self.assertFalse(frame_looks_valid(None))

    def test_real_image_is_valid(self):
        img = np.random.randint(0, 255, (48, 64, 3), np.uint8)
        self.assertTrue(frame_looks_valid(img))
        self.assertTrue(frame_looks_valid(img[:, :, 0]))   # imagem em tons de cinza

    def test_static_placeholder_detected(self):
        img = np.random.randint(0, 255, (48, 64, 3), np.uint8)
        self.assertFalse(frames_differ(img, img.copy()))      # tela de espera: quadro repetido
        noisy = np.clip(img.astype(int) + np.random.randint(-2, 3, img.shape), 0, 255).astype(np.uint8)
        self.assertTrue(frames_differ(img, noisy))            # câmera real: ruído do sensor

    def test_parse_source(self):
        self.assertEqual(parse_source("1"), 1)
        self.assertEqual(parse_source("auto"), "auto")
        self.assertEqual(parse_source("http://1.2.3.4:4747/video"), "http://1.2.3.4:4747/video")
        self.assertEqual(parse_source(2), 2)

    def test_candidate_order_without_duplicates(self):
        self.assertEqual(candidate_order("auto", None, 3), [0, 1, 2])
        self.assertEqual(candidate_order(1, 1, 3), [1, 0, 2])
        url = "http://10.0.0.5:4747/video"
        self.assertEqual(candidate_order(url, 0, 2), [url, 0, 1])

    def test_subnet_hosts(self):
        hosts = subnet_hosts("192.168.1.10")
        self.assertEqual(len(hosts), 253)
        self.assertNotIn("192.168.1.10", hosts)
        self.assertIn("192.168.1.224", hosts)

    def test_phone_urls(self):
        self.assertIn("http://192.168.1.5:4747/video", phone_urls("192.168.1.5"))
        self.assertIn("http://192.168.1.5:8080/video", phone_urls("192.168.1.5"))

    def test_rotate_after(self):
        self.assertEqual(rotate_after([0, 1, 2], 1), [2, 0, 1])
        self.assertEqual(rotate_after([0, 1, 2], 9), [0, 1, 2])


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "ultima.json"

    def tearDown(self):
        self.tmp.cleanup()

    def manager(self, configured="auto", working=(), phones=()):
        def fake_open(src, w, h):
            return FakeCap(src) if src in working else None
        patches = [mock.patch.object(camera, "open_source", side_effect=fake_open),
                   mock.patch.object(camera, "scan_phones", return_value=list(phones))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        m = CameraManager(configured, max_index=3, cache_path=self.cache, log=lambda *_: None)
        m.retry_delay = 0
        return m

    def test_finds_first_local_webcam(self):
        m = self.manager(working=(1, 2))
        m._search()
        self.assertEqual(m.source, 1)

    def test_falls_back_to_phone_on_any_ip(self):
        url = "http://192.168.0.77:4747/video"
        m = self.manager(working=(url,), phones=(url,))
        m._search()
        self.assertEqual(m.source, url)

    def test_stale_ip_falls_back_to_scan(self):
        old = "http://192.168.1.224:4747/video"    # IP antigo salvo no config
        new = "http://192.168.1.50:4747/video"     # celular pegou outro IP
        m = self.manager(configured=old, working=(new,), phones=(new,))
        m._search()
        self.assertEqual(m.source, new)

    def test_remembers_last_camera(self):
        m = self.manager(working=(0, 2))
        m._search()
        self.assertEqual(m.source, 0)
        m.next_camera()
        m._thread.join()
        self.assertEqual(m.source, 2)
        m2 = self.manager(working=(0, 2))      # nova sessão: começa pela última usada
        m2._search()
        self.assertEqual(m2.source, 2)

    def test_next_camera_keeps_current_when_alone(self):
        m = self.manager(working=(0,))
        m._search()
        m.next_camera()
        m._thread.join()
        self.assertEqual(m.source, 0)

    def test_nothing_found(self):
        m = self.manager()
        m._search()
        self.assertIsNone(m.source)
        self.assertIn("Nenhuma camera", m.status)

    def test_lost_camera_triggers_new_search(self):
        m = self.manager(working=(0,))
        m._search()
        m._cap.frames = 0                         # câmera desconectada
        for _ in range(10):
            ok, _ = m.read()
            self.assertFalse(ok)
        self.assertIsNone(m._cap)                 # largou a câmera morta e vai procurar de novo

    def test_frozen_camera_is_dropped(self):
        m = self.manager(working=(0,))
        m._search()
        still = np.random.randint(0, 255, (4, 4, 3), np.uint8)
        m._cap.read = lambda: (True, still.copy())   # celular desconectou: imagem parada
        m.frozen_timeout = 0.0
        m.read()                                      # primeiro quadro: referência
        ok, _ = m.read()                              # igual ao anterior: congelada
        self.assertFalse(ok)
        self.assertIsNone(m._cap)


if __name__ == "__main__":
    unittest.main()
