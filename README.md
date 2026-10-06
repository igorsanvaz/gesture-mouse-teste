# Gesture Mouse — controle do cursor por gestos de mão (TCC)

Aplicação inicial do TCC de Engenharia da Computação (UNIFEI Itabira): controla o
cursor do computador por gestos de mão capturados por uma webcam comum, voltada a
pessoas com dificuldade no uso do mouse.

Recursos implementados:

- **Rastreamento da mão** com MediaPipe Hand Landmarker (21 pontos, tempo real).
- **Estabilização do cursor** com quatro filtros comparáveis: nenhum, média móvel,
  Kalman e **filtro 1€** (padrão).
- **Clique por permanência** (padrão): o cursor parado por 1 s clica, com anel de progresso.
- **Rolagem por gesto** (indicador + médio esticados), no estilo joystick: a mão acima
  ou abaixo do ponto inicial rola a página, mais rápido quanto mais longe.
- **Clique direito** (pinça polegar + médio) e **clique duplo** (pinça polegar + anelar).
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
python run.py --camera 1          # força a webcam 1 (o padrão, auto, procura sozinho)
python run.py --tremor             # liga o tremor sintético
```

### Câmera (conecte e use)

Por padrão (`--camera auto`) o app encontra a câmera sozinho, nesta ordem: a câmera
configurada → a última que funcionou → webcams locais (0, 1, 2, 3) → celulares na mesma
rede Wi-Fi com **DroidCam** (porta 4747) ou **IP Webcam** (porta 8080), **em qualquer IP**.

- Câmeras que só entregam imagem parada ou de cor única (ex.: a tela "Start DroidCam" da
  câmera virtual sem o celular conectado) são ignoradas.
- Se a câmera for desconectada ou parar de mandar imagem, o app não fecha: mostra
  "Procurando camera" e reconecta sozinho, inclusive quando o celular muda de IP.
- `N` troca para a próxima câmera encontrada; `R` gira a imagem (celular em pé). `S` salva.

A janela da câmera abre com o controle **pausado**. Com ela em foco:

| Tecla | Ação |
| --- | --- |
| `ESPAÇO` | ativa / pausa o controle do mouse |
| `C` | calibra a área de movimento (3 s de preparo + 6 s movendo a mão até os limites confortáveis) |
| `M` | alterna o clique: permanência ↔ pinça |
| `B` | escolhe o próximo clique por permanência: esquerdo → duplo → direito → meio → arrastar |
| `F` | alterna o filtro: nenhum → média móvel → Kalman → 1€ |
| `T` | liga/desliga o tremor sintético |
| `N` | troca para a próxima câmera encontrada (webcam ou celular na rede) |
| `R` | gira a imagem da câmera em 90° |
| `S` | salva a configuração atual (inclusive a calibração) em `config.json` |
| `Q` / `ESC` | sai |

### Gestos

| Gesto | Ação | Modo |
| --- | --- | --- |
| mão aberta / relaxada | move o cursor | ambos |
| indicador + médio esticados (anelar e mínimo dobrados) | rolagem: mão acima do ponto inicial rola para cima, abaixo rola para baixo | ambos |
| pinça polegar + indicador | clique esquerdo; mantida, arrasta | pinça |
| pinça polegar + médio | clique direito | ambos |
| pinça polegar + anelar | clique duplo | ambos |
| cursor parado por 1 s | clique do tipo escolhido com `B` | permanência |

No modo permanência, duplo, direito e meio valem para um clique e voltam ao esquerdo.
Arrastar usa duas permanências: a primeira segura o botão, a segunda solta. Durante a
rolagem o cursor fica parado e os cliques ficam suspensos; a pose precisa se manter por
0,25 s para valer, o que evita trocas acidentais.

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
| `gestures.scroll_dead_zone` | 0.12 | quanto a mão pode se afastar do ponto inicial sem rolar (tamanhos de mão) |
| `gestures.scroll_max_speed` | 12 | velocidade máxima da rolagem (dentes da roda por segundo) |
| `camera.index` / `camera.rotate` | auto / 0 | `auto`, índice ou URL da câmera; rotação da imagem em graus |
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
  camera.py                busca automática da câmera (webcam ou celular na rede) e reconexão
  filters.py               nenhum, média móvel, Kalman, 1€
  clicks.py                clique por pinça e por permanência
  gestures.py              rolagem, clique direito/duplo e tipo de clique por permanência
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


## Referências principais

- Zhang et al. (2020), *MediaPipe Hands: On-device Real-time Hand Tracking*.
- Casiez, Roussel e Vogel (2012), *1€ Filter*, CHI '12.
- Betke, Gips e Fleming (2002), *The Camera Mouse*, IEEE TNSRE.
- Soukoreff e MacKenzie (2004), *Towards a standard for pointing device evaluation*, IJHCS.
