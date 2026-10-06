# CLAUDE.md

Projeto de TCC (Engenharia da Computação, UNIFEI Itabira): controle do cursor por
gestos de mão via webcam, voltado a pessoas com dificuldade motora no uso do mouse.
Diferenciais: filtro 1€ contra tremor, clique por permanência e calibração por usuário.

## Comandos

- Rodar: `python run.py` (opções: `--dry-run`, `--filter`, `--click`, `--tremor`, `--camera`, `--rotate`)
- Testes: `python -m pytest` (os testes não precisam de câmera nem de MediaPipe)
- Benchmark dos filtros: `python tools/filter_benchmark.py`
- Teste de Fitts: `python tools/fitts_test.py --participante P01 --condicao mouse`
- Modelo: `python scripts/download_model.py` (gera `models/hand_landmarker.task`)

## Arquitetura

Pipeline por quadro em `src/gesture_mouse/app.py`:
captura (`camera.CameraManager`: busca automática e reconexão) → `tracker.HandTracker` (MediaPipe Tasks, modo VIDEO) →
ponto da mão (`tracker.cursor_landmark`, padrão 9) → `tremor` (opcional) →
`mapping.image_to_screen` com a `ControlBox` calibrada → `filters` (em px de tela) →
`gestures.PostureDetector` (rolagem com `gestures.ScrollController`, ou cliques:
`clicks.DwellClicker`/`clicks.PinchClicker` + `gestures.ExtraPinches`) → `cursor.CursorController` (PyAutoGUI).

## Convenções

- Coordenadas da mão são normalizadas (0–1); filtros e cliques trabalham em px de tela.
- Filtros recebem o tempo da amostra em segundos (a taxa de quadros varia).
- Detectores de clique retornam `ClickEvent` e não chamam o sistema: mantenha-os testáveis.
- Importações de `mediapipe` e `pyautogui` ficam dentro das classes, para os testes rodarem sem eles.
- Textos de interface e comentários em português; desenhos do OpenCV sem acentos
  (a fonte Hershey não tem acentuação).
- Novas métricas da avaliação devem ir para o CSV da sessão (`metrics.SessionLogger`).
