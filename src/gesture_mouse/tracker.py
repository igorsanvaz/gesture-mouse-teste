"""Rastreamento da mão com o MediaPipe Hand Landmarker (API "Tasks").

O modelo `hand_landmarker.task` precisa ser baixado uma vez:
    python scripts/download_model.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)

# Ligações entre os 21 pontos, para desenhar o esqueleto da mão
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),          # polegar
    (0, 5), (5, 6), (6, 7), (7, 8),          # indicador
    (5, 9), (9, 10), (10, 11), (11, 12),     # médio
    (9, 13), (13, 14), (14, 15), (15, 16),   # anelar
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),  # mínimo e palma
)


@dataclass
class HandObservation:
    landmarks: list[tuple[float, float, float]]  # 21 pontos (x, y, z) normalizados
    handedness: str                               # "Left" ou "Right"
    score: float


class HandTracker:
    def __init__(self, model_path: str, min_detection_confidence: float = 0.6,
                 min_presence_confidence: float = 0.6, min_tracking_confidence: float = 0.5):
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Modelo não encontrado em '{path}'. Rode: python scripts/download_model.py"
            )
        # importação adiada: permite testar o resto do projeto sem MediaPipe instalado
        import mediapipe as mp
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision

        self._mp = mp
        options = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_ts_ms = -1

    def process(self, frame_bgr: np.ndarray, timestamp_s: float) -> HandObservation | None:
        """Detecta a mão em um quadro BGR (OpenCV). Retorna None se não houver mão."""
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        # o modo VIDEO exige timestamps estritamente crescentes em milissegundos
        ts_ms = max(int(timestamp_s * 1000), self._last_ts_ms + 1)
        self._last_ts_ms = ts_ms
        result = self._landmarker.detect_for_video(image, ts_ms)
        if not result.hand_landmarks:
            return None
        lms = [(p.x, p.y, p.z) for p in result.hand_landmarks[0]]
        side, score = "Unknown", 0.0
        if result.handedness and result.handedness[0]:
            cat = result.handedness[0][0]
            side, score = cat.category_name, cat.score
        return HandObservation(landmarks=lms, handedness=side, score=score)

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
