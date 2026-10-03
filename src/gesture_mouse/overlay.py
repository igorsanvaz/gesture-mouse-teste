"""Desenho de informações sobre o vídeo da câmera (janela de acompanhamento)."""

from __future__ import annotations

import cv2
import numpy as np

from .mapping import ControlBox
from .tracker import HAND_CONNECTIONS

GREEN = (80, 200, 80)
YELLOW = (0, 210, 255)
RED = (60, 60, 230)
WHITE = (255, 255, 255)
GRAY = (160, 160, 160)
BLUE = (230, 160, 40)


def _px(p, w, h) -> tuple[int, int]:
    return int(p[0] * w), int(p[1] * h)


def draw_hand(frame: np.ndarray, landmarks, cursor_idx: int, pressed: bool) -> None:
    h, w = frame.shape[:2]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, _px(landmarks[a], w, h), _px(landmarks[b], w, h), GRAY, 2)
    for p in landmarks:
        cv2.circle(frame, _px(p, w, h), 3, WHITE, -1)
    color = RED if pressed else YELLOW
    cv2.circle(frame, _px(landmarks[cursor_idx], w, h), 9, color, 2)


def draw_box(frame: np.ndarray, box: ControlBox, color=GREEN) -> None:
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (int(box.x_min * w), int(box.y_min * h)),
                  (int(box.x_max * w), int(box.y_max * h)), color, 2)


def draw_points(frame: np.ndarray, points, color=BLUE) -> None:
    h, w = frame.shape[:2]
    for p in points[-400:]:
        cv2.circle(frame, _px(p, w, h), 2, color, -1)


def draw_dwell(frame: np.ndarray, progress: float, center=(50, 120), radius=26) -> None:
    """Anel que se completa conforme o tempo de permanência."""
    cv2.circle(frame, center, radius, GRAY, 2)
    if progress > 0:
        cv2.ellipse(frame, center, (radius, radius), -90, 0, int(360 * progress), GREEN, 5)


def draw_status(frame: np.ndarray, lines: list[str], color=WHITE) -> None:
    y = 24
    for text in lines:
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
        y += 22


def draw_banner(frame: np.ndarray, text: str, color=YELLOW) -> None:
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, h - 40), (w, h), (0, 0, 0), -1)
    cv2.putText(frame, text, (10, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
