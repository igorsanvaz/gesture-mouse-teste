"""Aplicação principal: webcam -> MediaPipe -> mapeamento -> filtro -> clique -> sistema.

Teclas (com a janela da câmera em foco):
    ESPAÇO  ativa/pausa o controle do mouse (começa pausado)
    C       calibra a área de movimento
    M       alterna o modo de clique (permanência / pinça)
    B       escolhe o próximo clique por permanência (esquerdo / duplo / direito / meio / arrastar)
    F       alterna o filtro (nenhum / média móvel / Kalman / 1€)
    T       liga/desliga o tremor sintético (experimentos)
    S       salva a configuração atual em config.json
    Q / ESC sai

Gestos (com o controle ativo):
    indicador + médio esticados  rolagem (mão acima/abaixo do ponto inicial)
    pinça polegar + indicador    clique esquerdo; mantida, arrasta (modo pinça)
    pinça polegar + médio        clique direito
    pinça polegar + anelar       clique duplo
"""

from __future__ import annotations

import argparse
import sys
import time

import cv2

from .calibration import CalibrationPhase, Calibrator
from .clicks import ClickEvent, DwellClicker, PinchClicker, pinch_ratio
from .config import DEFAULT_CONFIG_PATH, AppConfig
from .cursor import CursorController
from .filters import FILTER_KINDS, make_filter
from .gestures import (DWELL_ACTION_LABELS, DwellActionSelector, ExtraPinches, Posture,
                       PostureDetector, ScrollController, _hand_size, classify_posture,
                       finger_pinch_ratios)
from .mapping import ControlBox, image_to_screen
from .metrics import FpsMeter, SessionLogger
from .overlay import (draw_banner, draw_box, draw_dwell, draw_hand, draw_points, draw_scroll,
                      draw_status)
from .tracker import HandTracker
from .tremor import TremorInjector

WINDOW = "Gesture Mouse - TCC"
ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
FILTER_LABELS = {"none": "nenhum", "moving_average": "media movel", "kalman": "Kalman", "one_euro": "1 Euro"}
CLICK_LABELS = {"dwell": "permanencia", "pinch": "pinca"}


class GestureMouseApp:
    def __init__(self, cfg: AppConfig, config_path=DEFAULT_CONFIG_PATH, dry_run: bool = False):
        self.cfg = cfg
        self.config_path = config_path
        self.cursor = CursorController(dry_run=dry_run)
        self.box = ControlBox(cfg.mapping.x_min, cfg.mapping.x_max, cfg.mapping.y_min, cfg.mapping.y_max)
        self.filter = make_filter(cfg.filter.kind, cfg.filter)
        c = cfg.click
        self.pinch = PinchClicker(c.pinch_on, c.pinch_off, c.pinch_freeze)
        self.dwell = DwellClicker(c.dwell_time, c.dwell_radius, c.dwell_rearm_distance)
        self.extra_pinches = ExtraPinches(c.pinch_on, c.pinch_off)
        self.dwell_action = DwellActionSelector()
        g = cfg.gestures
        self.posture = PostureDetector(g.posture_hold_s)
        self.scroller = ScrollController(g.scroll_dead_zone, g.scroll_full_range, g.scroll_max_speed)
        self.tremor = TremorInjector(cfg.tremor.frequency_hz, cfg.tremor.amplitude)
        self.calibrator = Calibrator(margin=cfg.mapping.calibration_margin)
        self.logger = SessionLogger(cfg.log.directory, cfg.log.enabled)
        self.fps = FpsMeter()
        self.active = False           # começa pausado por segurança
        self.last_screen = None       # última posição enviada ao cursor
        self.message = ""
        self.message_until = 0.0
        self._pending_log: dict = {}

    # ------------------------------------------------------------------
    def notify(self, text: str, now: float, seconds: float = 2.5) -> None:
        self.message, self.message_until = text, now + seconds
        print(text)

    def set_filter(self, kind: str) -> None:
        self.cfg.filter.kind = kind
        self.filter = make_filter(kind, self.cfg.filter)

    def reset_interaction(self) -> None:
        self.filter.reset()
        self.pinch.reset()
        self.dwell.reset()
        self.extra_pinches.reset()
        self.dwell_action.reset()
        self.posture.reset()
        self.scroller.reset()
        self.cursor.release_all()

    # ------------------------------------------------------------------
    def handle_key(self, key: int, now: float) -> bool:
        """Retorna False quando o usuário pede para sair."""
        if key in (ord("q"), ord("Q"), 27):
            return False
        if key == ord(" "):
            self.active = not self.active
            self.reset_interaction()
            self.notify("Controle ATIVO" if self.active else "Controle PAUSADO", now)
        elif key in (ord("c"), ord("C")):
            self.active = False
            self.reset_interaction()
            self.calibrator.start(now)
        elif key in (ord("m"), ord("M")):
            self.cfg.click.mode = "pinch" if self.cfg.click.mode == "dwell" else "dwell"
            self.reset_interaction()
            self.notify(f"Clique: {CLICK_LABELS[self.cfg.click.mode]}", now)
        elif key in (ord("b"), ord("B")):
            if self.cfg.click.mode != "dwell":
                self.notify("Tipo de clique (B) vale no modo permanencia (M)", now)
            elif self.dwell_action.dragging:
                self.notify("Termine o arraste antes (permaneca parado para soltar)", now)
            else:
                action = self.dwell_action.cycle()
                self.notify(f"Proximo clique: {DWELL_ACTION_LABELS[action]}", now)
        elif key in (ord("f"), ord("F")):
            i = FILTER_KINDS.index(self.cfg.filter.kind)
            self.set_filter(FILTER_KINDS[(i + 1) % len(FILTER_KINDS)])
            self.notify(f"Filtro: {FILTER_LABELS[self.cfg.filter.kind]}", now)
        elif key in (ord("t"), ord("T")):
            self.cfg.tremor.enabled = not self.cfg.tremor.enabled
            self.notify(f"Tremor sintetico: {'ligado' if self.cfg.tremor.enabled else 'desligado'}", now)
        elif key in (ord("s"), ord("S")):
            self.cfg.save(self.config_path)
            self.notify(f"Configuracao salva em {self.config_path}", now)
        return True

    # ------------------------------------------------------------------
    def step(self, frame, obs, now: float) -> None:
        """Processa um quadro já rastreado."""
        cfg = self.cfg
        event = ClickEvent.NONE
        raw = filt = None
        ratio = float("nan")
        gesture, scroll = "", 0.0

        if obs is not None:
            lms = [(p[0], p[1]) for p in obs.landmarks]
            nx, ny = lms[cfg.tracker.cursor_landmark]
            if cfg.tremor.enabled:
                nx, ny = self.tremor.apply(nx, ny, now)
            ratio = pinch_ratio(lms)

            # --- calibração tem prioridade sobre o controle
            if self.calibrator.active:
                phase = self.calibrator.update(now, (nx, ny))
                self._finish_calibration_if_done(phase, now)
            elif self.active:
                raw = image_to_screen(nx, ny, self.box, self.cursor.screen_w, self.cursor.screen_h)
                filt = self.filter.filter(raw[0], raw[1], now)
                posture = self.posture.update(classify_posture(lms), now)
                gesture = posture.value

                if posture == Posture.SCROLL:
                    # rolagem: cursor parado e cliques suspensos enquanto durar o gesto
                    if self.cursor.button_down and not self.dwell_action.dragging:
                        self.cursor.release()
                    self.pinch.reset()
                    self.extra_pinches.reset()
                    self.dwell.reset()
                    scroll = self.scroller.update(ny, _hand_size(lms), now)
                    self.cursor.scroll(scroll)
                else:
                    self.scroller.reset()
                    action = self._update_clicks(lms, ratio, filt, now)
                    if action:
                        gesture = action
                        event = ClickEvent.CLICK

            draw_hand(frame, obs.landmarks, cfg.tracker.cursor_landmark, self.pinch.pressed)
        else:
            if self.calibrator.active:
                phase = self.calibrator.update(now, None)
                self._finish_calibration_if_done(phase, now)
            # mão sumiu: solta o botão e zera o filtro para não "puxar" o cursor depois
            if self.cursor.button_down or self.pinch.pressed or self.extra_pinches.pressed:
                self.reset_interaction()
            self.filter.reset()
            self.posture.reset()
            self.scroller.reset()

        self._log(obs, raw, filt, ratio, event, gesture, scroll)

    def _update_clicks(self, lms, ratio: float, filt, now: float) -> str:
        """Cliques fora da rolagem. Devolve a ação executada ("left", "right"...) ou ""."""
        ratios = finger_pinch_ratios(lms)
        # pinças do médio (direito) e do anelar (duplo) valem nos dois modos
        extra = self.extra_pinches.update(ratios, now)
        if extra == "right":
            self.cursor.click("right")
        elif extra == "double":
            self.cursor.double_click()

        if self.cfg.click.mode == "pinch":
            # pinça esquerda ignorada enquanto outro dedo está mais perto do polegar
            blocked = self.extra_pinches.blocks_left(ratios) and not self.pinch.pressed
            event = self.pinch.update(float("inf") if blocked else ratio, now)
            if not (self.pinch.should_freeze(now) or self.extra_pinches.pressed):
                self.cursor.move(*filt)
                self.last_screen = filt
            if event == ClickEvent.DOWN:
                self.cursor.press()
            elif event == ClickEvent.UP:
                self.cursor.release()
            return extra or ("left" if event == ClickEvent.DOWN else "")

        # permanência: o cursor para enquanto uma pinça extra estiver fechada
        if not self.extra_pinches.pressed:
            self.cursor.move(*filt)
            self.last_screen = filt
        if self.dwell.update(filt[0], filt[1], now) != ClickEvent.CLICK:
            return extra or ""
        action = self.dwell_action.on_dwell()
        if action == "press":
            self.cursor.press()
        elif action == "release":
            self.cursor.release()
        elif action == "double":
            self.cursor.double_click()
        else:
            self.cursor.click(action)
        return action

    def _finish_calibration_if_done(self, phase: CalibrationPhase, now: float) -> None:
        if phase == CalibrationPhase.DONE and self.calibrator.result is not None:
            self.box = self.calibrator.result
            m = self.cfg.mapping
            m.x_min, m.x_max, m.y_min, m.y_max = (self.box.x_min, self.box.x_max,
                                                  self.box.y_min, self.box.y_max)
            self.calibrator.phase = CalibrationPhase.IDLE
            self.reset_interaction()
            self.notify("Calibracao concluida (S para salvar, ESPACO para ativar)", now, 4)
        elif phase == CalibrationPhase.IDLE:
            # o calibrador desiste quando a mão quase não foi vista
            self.notify("Calibracao falhou: mao pouco visivel. Tente de novo (C)", now, 4)

    def _log(self, obs, raw, filt, ratio, event, gesture="", scroll=0.0) -> None:
        self._pending_log = dict(
            hand=int(obs is not None),
            raw_x=raw[0] if raw else "", raw_y=raw[1] if raw else "",
            filt_x=filt[0] if filt else "", filt_y=filt[1] if filt else "",
            pinch_ratio=ratio if ratio == ratio else "",  # NaN -> vazio
            event=event.value if event != ClickEvent.NONE else "",
            filter=self.cfg.filter.kind, click_mode=self.cfg.click.mode,
            tremor=int(self.cfg.tremor.enabled),
            gesture=gesture, scroll=scroll if scroll else "",
        )

    # ------------------------------------------------------------------
    def draw_ui(self, frame, now: float, fps: float, proc_ms: float) -> None:
        cfg = self.cfg
        if self.calibrator.active:
            draw_points(frame, self.calibrator.points)
            draw_banner(frame, self.calibrator.message(now))
        else:
            draw_box(frame, self.box)
        status = "ATIVO" if self.active else "PAUSADO (espaco)"
        click = CLICK_LABELS[cfg.click.mode]
        if cfg.click.mode == "dwell":
            click += f" ({DWELL_ACTION_LABELS[self.dwell_action.action]}"
            click += ", segurando)" if self.dwell_action.dragging else ")"
        draw_status(frame, [
            f"{status} | clique: {click} | filtro: {FILTER_LABELS[cfg.filter.kind]}"
            + (" | TREMOR" if cfg.tremor.enabled else ""),
            f"{fps:4.1f} quadros/s | processamento {proc_ms:4.1f} ms",
        ])
        if self.active and self.posture.posture == Posture.SCROLL:
            draw_scroll(frame, self.scroller.offset, self.scroller.dead_zone,
                        self.scroller.full_range)
        elif self.active and cfg.click.mode == "dwell":
            draw_dwell(frame, self.dwell.state.progress, center=(40, 90))
        if now < self.message_until and not self.calibrator.active:
            draw_banner(frame, self.message)

    # ------------------------------------------------------------------
    def run(self) -> None:
        cam = self.cfg.camera
        # No Windows o DirectShow abre mais rápido, mas algumas câmeras virtuais
        # (ex.: DroidCam) só funcionam pelo backend padrão (MSMF)
        backends = [cv2.CAP_DSHOW, cv2.CAP_ANY] if sys.platform == "win32" else [cv2.CAP_ANY]
        if isinstance(cam.index, str):  # URL de vídeo (câmera IP)
            backends = [cv2.CAP_ANY]
        for backend in backends:
            cap = cv2.VideoCapture(cam.index, backend)
            if cap.isOpened():
                break
            cap.release()
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam.height)
        if not cap.isOpened():
            raise RuntimeError(f"Não foi possível abrir a webcam {cam.index}")

        t = self.cfg.tracker
        tracker = HandTracker(t.model_path, t.min_detection_confidence,
                              t.min_presence_confidence, t.min_tracking_confidence)
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        print(__doc__)
        if self.logger.path:
            print(f"Registrando sessão em {self.logger.path}")

        t_start = time.perf_counter()
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("Falha ao ler a webcam")
                    break
                t_frame = time.perf_counter()
                now = t_frame - t_start
                if cam.rotate in ROTATIONS:
                    frame = cv2.rotate(frame, ROTATIONS[cam.rotate])
                if cam.mirror:
                    frame = cv2.flip(frame, 1)

                obs = tracker.process(frame, now)
                self.step(frame, obs, now)

                proc_ms = (time.perf_counter() - t_frame) * 1000
                fps = self.fps.tick(t_frame)
                self.logger.log(t_s=now, fps=fps, proc_ms=proc_ms, **self._pending_log)

                self.draw_ui(frame, now, fps, proc_ms)
                cv2.imshow(WINDOW, frame)
                key = cv2.waitKey(1) & 0xFF
                if key != 255 and not self.handle_key(key, now):
                    break
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            self.cursor.release_all()
            tracker.close()
            cap.release()
            cv2.destroyAllWindows()
            self.logger.close()


# ----------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Controle do cursor por gestos de mão (TCC)")
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="arquivo de configuração JSON")
    p.add_argument("--filter", choices=FILTER_KINDS, help="filtro de suavização")
    p.add_argument("--click", choices=("dwell", "pinch"), help="modo de clique")
    p.add_argument("--camera", help="índice da webcam ou URL de vídeo (ex.: http://IP:4747/video)")
    p.add_argument("--rotate", type=int, choices=(0, 90, 180, 270),
                   help="gira a imagem da câmera (graus, sentido horário)")
    p.add_argument("--tremor", action="store_true", help="liga o tremor sintético")
    p.add_argument("--dry-run", action="store_true", help="não move o mouse de verdade")
    p.add_argument("--no-log", action="store_true", help="não grava CSV da sessão")
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = AppConfig.load(args.config)
    if args.filter:
        cfg.filter.kind = args.filter
    if args.click:
        cfg.click.mode = args.click
    if args.camera is not None:
        cfg.camera.index = int(args.camera) if args.camera.isdigit() else args.camera
    if args.rotate is not None:
        cfg.camera.rotate = args.rotate
    if args.tremor:
        cfg.tremor.enabled = True
    if args.no_log:
        cfg.log.enabled = False
    GestureMouseApp(cfg, config_path=args.config, dry_run=args.dry_run).run()


if __name__ == "__main__":
    main()
