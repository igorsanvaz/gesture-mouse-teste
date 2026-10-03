"""Baixa o modelo do MediaPipe Hand Landmarker para a pasta models/.

Uso:  python scripts/download_model.py
"""

from pathlib import Path
from urllib.request import urlretrieve

URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
DEST = Path(__file__).resolve().parent.parent / "models" / "hand_landmarker.task"


def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"Modelo já existe: {DEST}")
        return
    print(f"Baixando {URL} ...")
    urlretrieve(URL, DEST)
    print(f"Pronto: {DEST} ({DEST.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
