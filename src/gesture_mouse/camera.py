"""Câmera "conecte e use": encontra sozinha uma webcam ou um celular na rede.

Ordem de busca: fonte configurada → última que funcionou → webcams locais (0, 1, 2...)
→ celulares na rede local (DroidCam na porta 4747, IP Webcam na 8080), em qualquer IP.
Se a câmera cair no meio da sessão, a busca recomeça em segundo plano e o app segue
aberto mostrando "Procurando camera".

As partes que não dependem de hardware (validação da imagem, ordem dos candidatos,
endereços da rede) são funções puras, testadas sem câmera.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

AUTO = "auto"
# porta -> caminho do vídeo MJPEG dos apps de "celular como webcam"
PHONE_APPS = {4747: "/video",   # DroidCam
              8080: "/video"}   # IP Webcam (Android)
DEFAULT_CACHE = Path("logs/ultima_camera.json")


# ----------------------------------------------------------------------------
def frame_looks_valid(frame, min_std: float = 4.0) -> bool:
    """Imagem de verdade tem variação; câmera virtual sem vídeo manda cor chapada
    (ex.: verde do MSMF sem sinal) e webcam tampada/iniciando manda preto."""
    if frame is None or frame.size == 0:
        return False
    return float(frame.reshape(-1, frame.shape[-1] if frame.ndim == 3 else 1).std(axis=0).max()) > min_std


def frames_differ(a, b, min_diff: float = 0.05) -> bool:
    """Câmera de verdade tem ruído: dois quadros nunca são idênticos. Tela de espera
    de câmera virtual (ex.: "Start DroidCam" sem o celular) repete o mesmo quadro."""
    if a is None or b is None or a.shape != b.shape:
        return a is not None and b is not None
    return float(np.mean(cv2.absdiff(a, b))) > min_diff


def parse_source(value) -> int | str:
    """"0" -> 0; "auto" e URLs ficam como texto."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return value


def describe(source) -> str:
    return f"webcam {source}" if isinstance(source, int) else str(source)


def phone_urls(host: str) -> list[str]:
    return [f"http://{host}:{port}{path}" for port, path in PHONE_APPS.items()]


def subnet_hosts(ip: str, prefix: int = 24) -> list[str]:
    """Todos os endereços da sub-rede /24 do computador, exceto ele mesmo."""
    net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    return [str(h) for h in net.hosts() if str(h) != ip]


def candidate_order(configured, last, max_index: int) -> list:
    """Fontes a testar, sem repetir: configurada, última usada e webcams locais.
    (Os celulares da rede entram depois, porque exigem varredura.)"""
    order = []
    for src in (configured, last, *range(max_index)):
        if src is None or src == AUTO or src == "" or src in order:
            continue
        order.append(src)
    return order


def rotate_after(items: list, current) -> list:
    """Mesma lista começando logo depois de `current` (para a tecla "próxima câmera")."""
    if current not in items:
        return list(items)
    i = items.index(current)
    return items[i + 1:] + items[:i + 1]


# ----------------------------------------------------------------------------
def local_ipv4s() -> list[str]:
    """IPs privados deste computador (para saber qual rede varrer)."""
    ips = set()
    try:  # descobre a interface de saída sem enviar nada
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if ipaddress.ip_address(ip).is_private
                  and not ipaddress.ip_address(ip).is_loopback)


def _port_open(host: str, port: int, timeout: float) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def scan_phones(timeout: float = 0.3, workers: int = 128) -> list[str]:
    """Procura na rede local apps de celular-webcam (só testa se a porta está aberta)."""
    targets = [(h, port) for ip in local_ipv4s() for h in subnet_hosts(ip) for port in PHONE_APPS]
    if not targets:
        return []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        found = pool.map(lambda t: _port_open(*t, timeout), targets)
        return [f"http://{h}:{port}{PHONE_APPS[port]}" for (h, port), ok in zip(targets, found) if ok]


def open_source(source, width: int, height: int, warmup_frames: int = 30):
    """Abre e confirma que a fonte entrega imagem de verdade. Retorna o VideoCapture ou None."""
    if isinstance(source, int):
        # DirectShow abre rápido no Windows; algumas câmeras virtuais só funcionam no MSMF
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF] if sys.platform == "win32" else [cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_ANY]
    for backend in backends:
        cap = cv2.VideoCapture(source, backend)
        if not cap.isOpened():
            cap.release()
            continue
        if isinstance(source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        first = None
        for _ in range(warmup_frames):  # webcams costumam mandar quadros pretos ao ligar
            ok, frame = cap.read()
            if not ok or not frame_looks_valid(frame):
                continue
            if first is None:
                first = frame.copy()
            elif frames_differ(first, frame):   # imagem viva, não uma tela de espera
                return cap
        cap.release()
    return None


# ----------------------------------------------------------------------------
class CameraManager:
    """Mantém uma câmera aberta; procura outra em segundo plano quando não há nenhuma."""

    def __init__(self, configured=AUTO, width: int = 640, height: int = 480,
                 max_index: int = 4, scan_network: bool = True,
                 cache_path: Path | str | None = DEFAULT_CACHE, log=print):
        self.configured = parse_source(configured)
        self.width, self.height = width, height
        self.max_index = max_index
        self.scan_network = scan_network
        self.cache_path = Path(cache_path) if cache_path else None
        self.log = log
        self.source = None          # fonte em uso
        self.status = "Procurando camera..."
        self._cap = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._skip_until_after = None   # para a tecla "próxima câmera"
        self._failures = 0
        self._last_frame = None
        self._frozen_since: float | None = None
        self.frozen_timeout = 3.0   # s com quadros idênticos = câmera sem sinal
        self.retry_delay = 2.0      # s entre uma busca sem sucesso e a próxima

    # -- cache da última câmera que funcionou --------------------------------
    def _load_last(self):
        if not self.cache_path or not self.cache_path.exists():
            return None
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8")).get("source")
        except (OSError, ValueError):
            return None

    def _save_last(self, source) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps({"source": source}), encoding="utf-8")
        except OSError:
            pass

    # -- busca ----------------------------------------------------------------
    def _search(self) -> None:
        after = self._skip_until_after
        tried = []

        def attempt(src) -> bool:
            tried.append(src)
            self.status = f"Testando {describe(src)}..."
            cap = open_source(src, self.width, self.height)
            if cap is None:
                return False
            with self._lock:
                self._cap, self.source = cap, src
            self._failures = 0
            self.status = f"Camera: {describe(src)}"
            self.log(f"Câmera conectada: {describe(src)}")
            self._save_last(src)
            return True

        local = candidate_order(self.configured, self._load_last(), self.max_index)
        if after is not None:
            local = [s for s in rotate_after(local, after) if s != after]
        for src in local:
            if attempt(src):
                return
        if self.scan_network:
            self.status = "Procurando celular na rede (DroidCam / IP Webcam)..."
            phones = [u for u in scan_phones() if u not in tried and u != after]
            for url in phones:
                if attempt(url):
                    return
        if after is not None and attempt(after):   # não achou outra: volta para a atual
            return
        self.status = "Nenhuma camera encontrada. Conecte uma webcam ou abra a DroidCam."
        time.sleep(self.retry_delay)

    def _start_search(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._search, daemon=True)
        self._thread.start()

    @property
    def searching(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # -- uso pelo app ---------------------------------------------------------
    def read(self):
        """Devolve (True, quadro) ou (False, None) enquanto não há câmera."""
        with self._lock:
            cap = self._cap
        if cap is None:
            if not self.searching:
                self._skip_until_after = None
                self._start_search()
            return False, None
        ok, frame = cap.read()
        if ok and frame is not None:
            self._failures = 0
            if self._is_frozen(frame):
                self.log(f"Câmera sem sinal (imagem parada): {describe(self.source)}. Procurando de novo...")
                self._drop()
                return False, None
            return True, frame
        self._failures += 1
        if self._failures >= 10:   # ~1/3 s sem quadros: câmera caiu ou foi desconectada
            self.log(f"Câmera perdida: {describe(self.source)}. Procurando de novo...")
            self._drop()
        return False, None

    def _is_frozen(self, frame) -> bool:
        now = time.monotonic()
        if self._last_frame is None or frames_differ(self._last_frame, frame):
            self._frozen_since = None
        elif self._frozen_since is None:
            self._frozen_since = now
        self._last_frame = frame
        return self._frozen_since is not None and now - self._frozen_since >= self.frozen_timeout

    def next_camera(self) -> None:
        """Troca para a próxima câmera disponível (tecla N)."""
        if self.searching:
            return
        current = self.source
        self._drop()
        self._skip_until_after = current
        self._start_search()

    def _drop(self) -> None:
        with self._lock:
            cap, self._cap = self._cap, None
        self._last_frame, self._frozen_since = None, None
        if cap is not None:
            cap.release()
        self.status = "Procurando camera..."

    def close(self) -> None:
        self._drop()


def waiting_frame(text: str, width: int = 640, height: int = 480) -> np.ndarray:
    """Tela exibida enquanto não há câmera (texto sem acentos: fonte Hershey)."""
    frame = np.zeros((height, width, 3), np.uint8)
    dots = "." * (int(time.time() * 2) % 4)
    lines = [text.rstrip(".") + dots, "", "Webcam USB: conecte e aguarde",
             "Celular: abra a DroidCam ou IP Webcam na mesma rede Wi-Fi",
             "N: proxima camera   Q: sair"]
    y = height // 2 - 50
    for line in lines:
        cv2.putText(frame, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        y += 28
    return frame
