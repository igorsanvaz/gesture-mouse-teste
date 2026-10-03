"""Envio de movimento e cliques para o sistema operacional."""

from __future__ import annotations


class CursorController:
    """Envolve o PyAutoGUI. Com `dry_run=True`, nada é enviado ao sistema
    (útil para depurar o rastreamento sem perder o controle do mouse)."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.button_down = False
        if dry_run:
            self.screen_w, self.screen_h = 1920, 1080
            self._pg = None
            return
        import pyautogui

        pyautogui.PAUSE = 0           # sem atraso artificial entre comandos
        pyautogui.FAILSAFE = False    # o mapeamento nunca chega aos cantos; saída pela tecla Q
        self._pg = pyautogui
        self.screen_w, self.screen_h = pyautogui.size()

    def move(self, x: float, y: float) -> None:
        if self._pg:
            self._pg.moveTo(int(round(x)), int(round(y)), _pause=False)

    def press(self) -> None:
        if self._pg and not self.button_down:
            self._pg.mouseDown(_pause=False)
        self.button_down = True

    def release(self) -> None:
        if self._pg and self.button_down:
            self._pg.mouseUp(_pause=False)
        self.button_down = False

    def click(self) -> None:
        if self._pg:
            self._pg.click(_pause=False)

    def release_all(self) -> None:
        """Garante que o botão não fique preso ao pausar ou sair."""
        if self.button_down:
            self.release()
