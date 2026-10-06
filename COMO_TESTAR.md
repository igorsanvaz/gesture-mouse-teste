# Como testar o Gesture Mouse

Obrigado por ajudar! Este guia leva uns 10 minutos e não exige saber programar.
O programa controla o cursor do mouse com gestos da mão, usando a webcam.

## 1. O que você precisa

- Computador com **Windows 10 ou 11** (também funciona em Linux e macOS; veja o passo 3).
- Uma **webcam** (do notebook ou USB) **ou** um celular com o app **DroidCam** ou
  **IP Webcam**, na mesma rede Wi-Fi do computador.
- **Python** 3.10, 3.11, 3.12 ou 3.13. Para instalar:
  1. Baixe em <https://www.python.org/downloads/>.
  2. Na primeira tela do instalador, **marque "Add python.exe to PATH"** antes de clicar
     em *Install Now*.
- **Git** (para baixar o projeto): <https://git-scm.com/download/win>, instalação padrão.
  Sem Git, você pode baixar o ZIP (passo 2).

Para conferir se ficou tudo instalado, abra o **PowerShell** (menu Iniciar → digite
"PowerShell") e rode:

```powershell
python --version
git --version
```

Os dois devem mostrar um número de versão.

## 2. Baixar o projeto

No PowerShell:

```powershell
cd $HOME\Downloads
git clone https://github.com/igorsanvaz/gesture-mouse-teste.git
cd gesture-mouse-teste
```

**Sem Git:** na página do projeto no GitHub, clique em **Code → Download ZIP**, extraia o
ZIP na pasta Downloads e, no PowerShell, entre na pasta extraída:

```powershell
cd $HOME\Downloads\gesture-mouse-teste-main
```

## 3. Instalar (só na primeira vez)

Ainda no PowerShell, dentro da pasta do projeto, rode um comando de cada vez:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts\download_model.py
```

A instalação baixa algumas centenas de MB e pode levar alguns minutos. O último
comando deve terminar com `Pronto: ...hand_landmarker.task`.

**Linux / macOS:** use `python3` e troque `.venv\Scripts\python` por `.venv/bin/python`.

## 4. Rodar

```powershell
.venv\Scripts\python run.py
```

Uma janela com a imagem da câmera vai abrir. A câmera é encontrada sozinha:

- **Webcam:** basta estar conectada.
- **Celular:** abra o DroidCam ou o IP Webcam no celular, na mesma rede Wi-Fi. O programa
  procura o celular na rede automaticamente, em qualquer IP. Se a imagem vier deitada,
  aperte `R` para girar.

Nas próximas vezes, basta abrir o PowerShell na pasta do projeto e rodar só este comando.

## 5. Usar

O programa **começa pausado** e não mexe no mouse até você mandar. Clique na janela da
câmera para as teclas funcionarem.

1. Sente-se de frente para a câmera, com boa luz e a mão inteira visível.
   Apoiar o cotovelo na mesa cansa menos.
2. Aperte **`C`** para **calibrar**: espere a contagem de 3 s e, durante 6 s, mova a mão
   até os limites que você alcança **com conforto**. Essa área vira a tela inteira.
3. Aperte **`ESPAÇO`** para **ativar** o controle do mouse.
4. Mova a mão para mover o cursor. Para clicar, **deixe o cursor parado por 1 segundo**
   (um anel verde se completa e o clique acontece).

**Para parar a qualquer momento:** clique na janela da câmera e aperte `ESPAÇO` (pausa)
ou `Q` (fecha o programa).

### Gestos

| Gesto | O que faz |
| --- | --- |
| mão aberta / relaxada | move o cursor |
| cursor parado por 1 s | clique |
| indicador + médio esticados (anelar e mínimo dobrados) | rolagem: mão acima do ponto inicial rola para cima, abaixo rola para baixo |
| pinça polegar + médio | clique direito |
| pinça polegar + anelar | clique duplo |

### Teclas

| Tecla | Ação |
| --- | --- |
| `ESPAÇO` | ativa / pausa o controle |
| `C` | calibra a área de movimento |
| `M` | troca o clique: por permanência ↔ por pinça (polegar + indicador) |
| `B` | escolhe o tipo do próximo clique por permanência: esquerdo, duplo, direito, meio, arrastar |
| `F` | troca o filtro contra tremor |
| `N` | troca para a próxima câmera encontrada |
| `R` | gira a imagem da câmera |
| `S` | salva as configurações |
| `Q` | sai |

## 6. Problemas comuns

| Problema | Solução |
| --- | --- |
| `python` não é reconhecido | Reinstale o Python marcando **"Add python.exe to PATH"** e abra um PowerShell novo. |
| Erro ao instalar o `mediapipe` | Confira a versão com `python --version`; use Python 3.11 ou 3.12 se a sua for mais nova ou mais antiga que as listadas. |
| "Procurando camera" não termina | Feche outros programas que usam a câmera (Teams, Zoom, navegador). No celular, deixe o app aberto na tela e confira se está no mesmo Wi-Fi. Aperte `N` para tentar a próxima câmera. |
| Imagem deitada ou de cabeça para baixo | Aperte `R` até ficar certa e depois `S` para salvar. |
| A mão não é reconhecida | Melhore a iluminação, afaste-se um pouco e mostre a mão inteira, com a palma para a câmera. |
| O cursor treme ou fica lento | Refaça a calibração (`C`) e teste outros filtros com `F`. |
| Cliques sem querer | Mova o cursor um pouco depois de cada clique, ou pause com `ESPAÇO`. |

## 7. Enviar seu retorno

Cada uso gera um arquivo de registro na pasta `logs` do projeto (`sessao_AAAAMMDD_HHMMSS.csv`).
Ele guarda só números (posição do cursor, quadros por segundo, cliques): **nenhuma imagem
da câmera é salva**.

Envie para quem te pediu o teste:

1. O arquivo `.csv` mais recente da pasta `logs`.
2. Respostas curtas:
   - Conseguiu instalar e abrir? Teve algum erro (cole a mensagem)?
   - Usou webcam ou celular?
   - O cursor foi fácil de controlar? Tremeu?
   - Os cliques funcionaram? Algum clique sem querer?
   - A rolagem funcionou?
   - De 0 a 10, quão cansativo foi?
