# Gesture Mouse — controle do cursor por gestos de mão (TCC)

Aplicação inicial do TCC de Engenharia da Computação (UNIFEI Itabira): controla o
cursor do computador por gestos de mão capturados por uma webcam comum, voltada a
pessoas com dificuldade no uso do mouse.

Recursos implementados:

- **Rastreamento da mão** com MediaPipe Hand Landmarker (21 pontos, tempo real).
- **Estabilização do cursor** com quatro filtros comparáveis: nenhum, média móvel,
  Kalman e **filtro 1€** (padrão).
- **Clique por permanência** (padrão): o cursor parado por 1 s clica, com anel de progresso.
- **Clique por pinça** (polegar + indicador), com histerese e congelamento do cursor
  no momento do clique; manter a pinça fechada permite arrastar.
- **Calibração personalizada**: o usuário mostra a amplitude de movimento que alcança
  com conforto e essa área passa a cobrir a tela toda.
- **Tremor sintético** (4–6 Hz) para os experimentos controlados.
- **Registro em CSV** de cada sessão (trajetória bruta e filtrada, quadros/s, tempo de processamento).
- **Ferramentas de avaliação**: teste de Fitts (ISO 9241-411) com cálculo de
  *throughput* e benchmark offline dos filtros.

## Instalação

Requer **Python 3.10 a 3.12** (3.11 é a opção mais segura para o MediaPipe) e uma webcam.

```bash
# 1. criar e ativar um ambiente virtual
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux / macOS

# 2. instalar as dependências
pip install -r requirements.txt

# 3. baixar o modelo da mão (alguns MB, só na primeira vez)
python scripts/download_model.py
```

## Uso

```bash
python run.py                      # usa config.json (ou os padrões)
python run.py --click pinch        # começa no clique por pinça
python run.py --filter kalman      # escolhe o filtro
python run.py --dry-run            # mostra o rastreamento sem mover o mouse
python run.py --tremor             # liga o tremor sintético
```

A janela da câmera abre com o controle **pausado**. Com ela em foco:

| Tecla | Ação |
| --- | --- |
| `ESPAÇO` | ativa / pausa o controle do mouse |
| `C` | calibra a área de movimento (3 s de preparo + 6 s movendo a mão até os limites confortáveis) |
| `M` | alterna o clique: permanência ↔ pinça |
| `F` | alterna o filtro: nenhum → média móvel → Kalman → 1€ |
| `T` | liga/desliga o tremor sintético |
| `S` | salva a configuração atual (inclusive a calibração) em `config.json` |
| `Q` / `ESC` | sai |

**Dicas de uso:** apoie o cotovelo na mesa para reduzir a fadiga; mantenha boa
iluminação e a mão inteira visível; faça a calibração antes de ativar o controle.
O cursor é controlado pelo centro da palma (ponto 9), que fica estável durante a pinça;
para usar a ponta do indicador, mude `tracker.cursor_landmark` para `8` em `config.json`.

### Configuração

Rode a aplicação e aperte `S` para gerar o `config.json` com todos os parâmetros. Os
principais:

| Parâmetro | Padrão | Efeito |
| --- | --- | --- |
| `filter.min_cutoff` | 1.0 Hz | menor = cursor mais estável e mais lento para reagir |
| `filter.beta` | 0.01 | maior = menos atraso em movimentos rápidos |
| `click.dwell_time` | 1.0 s | tempo parado para clicar |
| `click.dwell_radius` | 30 px | quanto o cursor pode tremer e ainda contar como parado |
| `click.pinch_on` / `pinch_off` | 0.25 / 0.35 | limiares da pinça (relativos ao tamanho da mão) |
| `tremor.frequency_hz` / `amplitude` | 5 Hz / 0.01 | tremor sintético (fração da largura da imagem) |

## Ferramentas de avaliação

### Teste de Fitts (ISO 9241-411)

Abre 13 alvos em círculo; o participante clica no alvo destacado. Funciona com o mouse
comum ou com o controle por gestos rodando em paralelo.

```bash
python tools/fitts_test.py --participante P01 --condicao mouse
python tools/fitts_test.py --participante P01 --condicao gestos_1euro_dwell
```

Gera em `logs/fitts/` um CSV com cada clique e um resumo por sequência com tempo de
movimento, taxa de erro, largura efetiva (*We*), *IDe* e **throughput (bits/s)**.

### Benchmark dos filtros

Simula trajetórias de apontamento com tremor e compara os filtros sem precisar de câmera:

```bash
python tools/filter_benchmark.py --tremor-px 10 --freq 5 --grafico filtros.png --csv filtros.csv
```

Resultado com os parâmetros padrão (tremor de 10 px a 5 Hz + ruído de 2 px):

| Filtro | Tremor residual parado (px) | Erro em movimento (px) | Atraso (ms) |
| --- | --- | --- | --- |
| nenhum | 10,3 | 10,3 | 0 |
| média móvel (5) | 2,4 | 61,3 | 66 |
| Kalman | 4,6 | 24,4 | 12 |
| **1€** | **2,9** | **14,3** | **12** |

## Testes

```bash
python -m pytest                    # ou: python -m unittest discover tests
```

## Estrutura

```
run.py                     atalho para iniciar a aplicação
scripts/download_model.py  baixa o modelo do MediaPipe
src/gesture_mouse/
  app.py                   laço principal, teclas e interface
  tracker.py               MediaPipe Hand Landmarker
  mapping.py               imagem -> tela (caixa de controle)
  calibration.py           calibração da amplitude de movimento
  filters.py               nenhum, média móvel, Kalman, 1€
  clicks.py                clique por pinça e por permanência
  tremor.py                tremor sintético
  cursor.py                envio ao sistema (PyAutoGUI)
  metrics.py               quadros/s e registro CSV
  overlay.py               desenho sobre o vídeo
  fitts.py                 cálculos da Lei de Fitts / ISO 9241-411
  config.py                configuração (config.json)
tools/fitts_test.py        teste de apontamento
tools/filter_benchmark.py  comparação offline dos filtros
tests/                     testes automatizados
```

## Limitações conhecidas

- No macOS, é preciso permitir o acesso à câmera e à **Acessibilidade** (para mover o
  mouse) ao Terminal/IDE nas configurações de privacidade.
- No Linux, o PyAutoGUI exige sessão X11 (no Wayland o cursor pode não se mover).
- O tempo de processamento registrado mede da leitura do quadro até o envio do
  movimento; não inclui o atraso interno da webcam nem do monitor.

## Referências principais

- Zhang et al. (2020), *MediaPipe Hands: On-device Real-time Hand Tracking*.
- Casiez, Roussel e Vogel (2012), *1€ Filter*, CHI '12.
- Betke, Gips e Fleming (2002), *The Camera Mouse*, IEEE TNSRE.
- Soukoreff e MacKenzie (2004), *Towards a standard for pointing device evaluation*, IJHCS.
