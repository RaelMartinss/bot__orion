# 🛰️ Orion Bot

Bot Telegram para controle remoto do seu PC Windows com suporte a **comandos por voz, texto livre e microfone**.

---

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (gerenciador de pacotes)
- Steam instalado (para comandos de jogos)
- Windows 10/11

---

## Instalação

```bash
# 1. Clone o repositório
git clone <repo-url>
cd orion_bot

# 2. Instale as dependências
uv sync

# 3. Configure o token (veja abaixo)
# 4. Execute
uv run python main.py
```

### Configurar o Token

1. Crie um bot no [@BotFather](https://t.me/BotFather) e copie o token.
2. Abra `main.py` e substitua o valor de `TOKEN` pelo seu token.

> Na **primeira execução** o modelo Whisper (`small`, ~240 MB) é baixado automaticamente.

---

## Formas de enviar comandos

O Orion aceita comandos de **três formas diferentes**:

| Forma | Como usar |
|---|---|
| 🎙️ **Áudio no Telegram** | Grave e envie um áudio no chat do bot |
| ✍️ **Texto livre no Telegram** | Digite normalmente, sem precisar usar `/` |
| 🖥️ **Microfone do PC** | Fale direto no microfone — o bot executa e te notifica no Telegram |

---

## Comandos por Voz e Texto Livre

Fale ou escreva naturalmente em português. Não é necessário usar nenhuma palavra de ativação.

### 🎵 Música (Spotify)

| Exemplo | Ação |
|---|---|
| *"toca menino da porteira"* | Abre Spotify buscando a música |
| *"coloca raul seixas"* | Busca o artista no Spotify |
| *"play bohemian rhapsody"* | Busca no Spotify |
| *"ouvir legião urbana"* | Busca no Spotify |

### ▶️ YouTube

| Exemplo | Ação |
|---|---|
| *"youtube lofi hip hop"* | Busca no YouTube |
| *"assistir vídeo de minecraft"* | Busca no YouTube |

### 🎬 Netflix

| Exemplo | Ação |
|---|---|
| *"netflix breaking bad"* | Busca na Netflix |
| *"filme interestelar"* | Busca na Netflix |

### 🎮 Jogos

| Exemplo | Ação |
|---|---|
| *"abre o minecraft"* | Abre o jogo pelo nome (busca aproximada) |
| *"joga counter strike"* | Abre o jogo |
| *"lança the witcher"* | Abre o jogo |

### 🔊 Volume

| Exemplo | Ação |
|---|---|
| *"aumenta o volume"* | +10% |
| *"baixa o volume 20"* | −20% |
| *"muta"* / *"silencia"* | Muta/desmuta |

### ⚙️ Sistema

| Exemplo | Ação |
|---|---|
| *"desliga o pc"* | Desliga em 60s |
| *"desliga em 300"* | Desliga em 5 minutos |
| *"reinicia"* | Reinicia em 60s |
| *"cancela"* | Cancela desligamento agendado |

---

## Comandos Telegram (barra)

Também funcionam os comandos tradicionais com `/`:

| Comando | Descrição |
|---|---|
| `/jogos` | Lista todos os jogos Steam instalados |
| `/jogo <nome>` | Abre um jogo (aceita nome parcial) |
| `/youtube <busca>` | Abre o YouTube com busca |
| `/netflix <busca>` | Abre a Netflix com busca |
| `/spotify <busca>` | Abre o Spotify com busca |
| `/vol_up [%]` | Aumenta o volume (padrão 10%) |
| `/vol_down [%]` | Diminui o volume (padrão 10%) |
| `/mute` | Muta/desmuta |
| `/desligar [s]` | Desliga o PC em N segundos (padrão 60) |
| `/reiniciar [s]` | Reinicia o PC em N segundos (padrão 60) |
| `/cancelar` | Cancela desligamento agendado |
| `/ajuda` | Exibe o menu de ajuda |

---

## Como a descoberta de jogos funciona

O bot lê os arquivos `.acf` (AppManifest) do Steam para encontrar todos os jogos instalados em todas as bibliotecas — incluindo jogos em outros HDs/SSDs configurados no Steam. Nenhum caminho precisa ser configurado manualmente.

---

## Estrutura do projeto

```
orion_bot/
├── main.py                  # Ponto de entrada (async, PTB v21)
├── pyproject.toml           # Dependências (uv/hatchling)
├── handlers/
│   ├── start.py             # /start e /ajuda
│   ├── jogos.py             # /jogos e /jogo
│   ├── midia.py             # /youtube, /netflix, /spotify
│   ├── volume.py            # /vol_up, /vol_down, /mute
│   ├── sistema.py           # /desligar, /reiniciar, /cancelar
│   └── voice.py             # Handler de áudio e texto livre
└── utils/
    ├── steam_scanner.py     # Descoberta automática de jogos Steam
    ├── transcriber.py       # Transcrição de áudio via Whisper (local)
    ├── intent_parser.py     # Parser de linguagem natural PT-BR
    ├── executor.py          # Executa ações (compartilhado por Telegram e mic)
    └── mic_listener.py      # Listener de microfone em background
```

---

## Dependências principais

| Pacote | Uso |
|---|---|
| `python-telegram-bot` | Interface com a API do Telegram |
| `faster-whisper` | Transcrição de voz local (sem API externa) |
| `sounddevice` | Captura de microfone no Windows |
| `pycaw` | Controle de volume via Windows Audio API |
| `numpy` | Processamento de áudio |
