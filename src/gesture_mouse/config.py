"""Configuração da aplicação, carregada de/para um arquivo JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass
class CameraConfig:
    index: int = 0              # índice da webcam (0 = padrão)
    width: int = 640            # resolução de captura (px)
    height: int = 480
    mirror: bool = True         # espelha a imagem para o movimento parecer natural


@dataclass
class TrackerConfig:
    model_path: str = "models/hand_landmarker.task"
    min_detection_confidence: float = 0.6
    min_presence_confidence: float = 0.6
    min_tracking_confidence: float = 0.5
    # Ponto da mão que controla o cursor (índices do MediaPipe):
    # 8 = ponta do indicador, 5 = base do indicador, 9 = centro da palma (base do médio)
    cursor_landmark: int = 9


@dataclass
class FilterConfig:
    # "none", "moving_average", "kalman" ou "one_euro"
    kind: str = "one_euro"
    # média móvel
    window: int = 5
    # filtro 1€ (Casiez et al., 2012)
    min_cutoff: float = 1.0     # Hz — menor = menos tremor, mais atraso
    beta: float = 0.01          # coeficiente de velocidade — maior = menos atraso em movimentos rápidos
    d_cutoff: float = 1.0       # Hz — corte da derivada
    # Kalman (velocidade constante)
    process_noise: float = 1.0e6
    measurement_noise: float = 100.0


@dataclass
class ClickConfig:
    # "pinch" (pinça) ou "dwell" (permanência)
    mode: str = "dwell"
    # pinça: distância polegar–indicador normalizada pelo tamanho da mão
    pinch_on: float = 0.25      # abaixo disso = pinça fechada (clique)
    pinch_off: float = 0.35     # acima disso = pinça aberta (histerese)
    pinch_freeze: float = 0.45  # abaixo disso o cursor congela para não "escorregar" no clique
    # permanência
    dwell_time: float = 1.0     # segundos parado para clicar
    dwell_radius: float = 30.0  # px de tolerância na tela
    dwell_rearm_distance: float = 60.0  # px que o cursor precisa se mover para armar outro clique


@dataclass
class MappingConfig:
    # Região da imagem (coordenadas normalizadas 0–1) mapeada para a tela inteira.
    # É substituída pela calibração do usuário.
    x_min: float = 0.25
    x_max: float = 0.75
    y_min: float = 0.25
    y_max: float = 0.75
    calibration_margin: float = 0.03  # folga retirada de cada lado da área calibrada


@dataclass
class TremorConfig:
    # Tremor sintético para os experimentos (Seção 4.2 do plano de trabalho)
    enabled: bool = False
    frequency_hz: float = 5.0
    amplitude: float = 0.01     # em coordenadas normalizadas da imagem (~1% da largura)


@dataclass
class LogConfig:
    enabled: bool = True
    directory: str = "logs"


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    click: ClickConfig = field(default_factory=ClickConfig)
    mapping: MappingConfig = field(default_factory=MappingConfig)
    tremor: TremorConfig = field(default_factory=TremorConfig)
    log: LogConfig = field(default_factory=LogConfig)

    # ---------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        cfg = cls()
        for f in fields(cls):
            section = data.get(f.name)
            if not isinstance(section, dict):
                continue
            target = getattr(cfg, f.name)
            for key, value in section.items():
                if hasattr(target, key):
                    setattr(target, key, value)
        return cfg

    @classmethod
    def load(cls, path: Path | str = DEFAULT_CONFIG_PATH) -> "AppConfig":
        path = Path(path)
        if not path.exists():
            return cls()
        with path.open(encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def save(self, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
