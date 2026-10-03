"""Atalho para rodar a aplicação a partir da raiz do projeto:  python run.py [opções]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from gesture_mouse.app import main  # noqa: E402

if __name__ == "__main__":
    main()
