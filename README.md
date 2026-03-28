# Orion Bot

Bot Telegram inteligente para controle remoto de PC Windows via voz, texto e microfone integrado. Combina automação nativa com IA generativa para criar uma experiência natural de comando por voz.

## 🎯 Propósito Principal

- **Controle remoto**: Executar ações no PC (volume, mídia, jogos, sistema) via Telegram
- **Interface multimodal**: Aceita comandos por **voz** (Telegram/mic), **texto livre** e **comandos fixos**
- **Auto-aprendizado**: IA (Claude) gera novos comandos dinamicamente sem reiniciar o bot

## 🔧 Stack Tecnológico

- **Python 3.11+** com `asyncio` para concorrência
- **Telegram Bot API** (python-telegram-bot v21+)
- **Claude Sonnet 4.6** (Anthropic) para geração de código
- **Whisper** (offline) para transcrição de voz
- **Windows APIs** (pycaw, pyautogui) para automação

## 🏗️ Arquitetura Modular

- **`handlers/`**: Lógica de comandos (voz, jogos, mídia, volume, sistema)
- **`utils/`**: Núcleo IA (Claude client, intent parser, executor, mic listener)
- **`main.py`**: Inicialização e registro de handlers

## 🔄 Como Funciona

1. **Entradas**: Voz no Telegram, texto livre, ou microfone do PC (palavra-chave "orion")
2. **Processamento**: Whisper transcreve → NLP extrai intenção → executor roda ação
3. **IA Dinâmica**: Comandos desconhecidos geram handlers Python automaticamente
4. **Feedback**: Notificações instantâneas no Telegram

## 🎙️ Exemplos de Uso

- **Voz**: "aumenta volume" ou "toca Beatles no Spotify"
- **Texto**: `/volume 50` ou "abre Minecraft"
- **Sistema**: "desliga em 5 minutos" ou "reinicia"

## 💡 Diferencial

- **Offline-first**: Transcrição local (não envia áudio para APIs)
- **Inteligente**: Entende linguagem natural em português
- **Extensível**: IA adiciona funcionalidades em runtime
- **Thread-safe**: Microfone em background + Telegram assíncrono

## 📋 Resumo Completo do Projeto

### 🎯 **Propósito**
Bot Telegram para controle remoto de PC Windows via comandos por **voz**, **texto livre** e **microfone do PC**. Combina IA (Claude) para aprender novos comandos dinamicamente com controle nativo de sistema.

### 🔧 **Tecnologias Usadas**

| Componente | Tecnologia |
|---|---|
| **Framework Bot** | python-telegram-bot v21.0+ |
| **IA Generativa** | Claude Sonnet 4.6 (Anthropic API) |
| **Transcrição** | Faster Whisper (speech-to-text offline) |
| **Áudio** | sounddevice, pycaw (volume/controle) |
| **Automação** | pyautogui, comtypes |
| **Streaming** | yt-dlp (YouTube), spotify: URI scheme |
| **HTTP** | httpx (async) |
| **Config** | python-dotenv |
| **Python** | 3.11+ |

### 🏗️ **Arquitetura**

#### **Estrutura de Diretórios**
```
handlers/          # Lógica de comandos
├── voice.py       # Transcrição e execução (áudio Telegram)
├── start.py       # Comando /start
├── jogos.py       # Abrir games (Steam)
├── midia.py       # Spotify, Netflix, YouTube
├── controle.py    # Play/Pause/Próxima/Anterior
├── volume.py      # Controle de volume
├── sistema.py     # Desligar/Reiniciar
├── auto_learn.py  # IA: gerar handlers e registrar dinamicamente
└── custom/        # Handlers auto-gerados

utils/             # Núcleo da IA e execução
├── claude_client.py      # Wrapper API Anthropic
├── intent_parser.py      # NLP: extrair ação + query do texto
├── executor.py           # Executar intents (ativo/inativo Telegram)
├── prompt_builder.py     # Construir prompts para Claude
├── code_validator.py     # Validar código Python gerado
├── handler_registry.py   # Salvar, registrar, atualizar menu
├── mic_listener.py       # Ouvir microfone em background
├── transcriber.py        # Whisper (file + numpy)
└── steam_scanner.py      # Detect games no Steam

main.py            # Inicialização da aplicação
```

### 🔄 **Fluxo de Funcionamento**

#### **1️⃣ Entrada de Comandos (3 canais)**

```
┌─────────────────────────────────────────┐
│   Telegram (áudio/texto)                │
│   Microfone do PC                       │
└──────────────┬──────────────────────────┘
               ↓
        Normalizar Texto
               ↓
        Intent Parser (NLP + Regex)
               ↓
         Executor (ação)
```

#### **2️⃣ Pipeline de Voz**
- **Telegram áudio** → `handle_voice()` → Whisper (offline) → `intent_parser` → `executor`
- **Microfone** → `mic_listener` (background) → Whisper → `intent_parser` → notificação Telegram

#### **3️⃣ Auto-aprendizado (IA)**
```
/comando_desconhecido
  ↓
[Bot pergunta a intenção]
  ↓
Claude gera handler Python
  ↓
Validar código (AST check)
  ↓
Salvar em handlers/custom/<comando>.py
  ↓
Registrar em runtime (sem restart)
  ↓
Atualizar menu Telegram (/command)
```

### 🎙️ **Parser de Intenção**

Reconhece naturalmente em PT-BR (sem palavra de ativação):

| Ação | Exemplos |
|---|---|
| **Spotify** | "toca menino da porteira", "coloca raul seixas" |
| **YouTube** | "youtube lofi hip hop", "assistir vídeo" |
| **Netflix** | "netflix breaking bad", "filme interestelar" |
| **Jogos** | "abre minecraft", "joga counter strike" |
| **Volume** | "aumenta volume", "baixa 20", "muta" |
| **Controle** | "pausa", "próxima", "anterior" |
| **Sistema** | "desliga", "desliga em 300", "reinicia" |

### 🔗 **Integrações Principais**

#### **Claude (Anthropic)**
- **Uso**: Gerar handlers Python para comandos novos
- **Model**: claude-sonnet-4-6
- **Flow**:
  - Sistema: prompt com restrições (segurança, estilo)
  - User: intenção descrita pelo usuário
  - Output: código validado + registrado em runtime

#### **Telegram (python-telegram-bot)**
- **Handlers**: CommandHandler, MessageHandler, ConversationHandler
- **Modo**: Polling (servidor remoto, não precisa port aberto)
- **Features**:
  - Notificações de voz do PC
  - Menu dinâmico (`/start`, custom commands)
  - Estados conversacionais (volume set, auto-learn)

#### **Whisper (Faster-Whisper)**
- **Função**: Transcrição offline (não envia áudio pra API)
- **Modelo**: `small` (~240 MB), carregado automaticamente
- **Entrada**: OGG (Telegram), MP3, ou NumPy array (microfone)

#### **Microfone (sounddevice + numpy)**
- **Detector**: VAD automático (silêncio ~1.3s para parar)
- **Palavra-chave**: "orion" (case-insensitive, detecta no texto transcrito)
- **Thread**: Daemon background, loop contínuo
- **Feedback**: Notificação instantânea no Telegram após execução

#### **Windows API (pycaw, comtypes, pyautogui)**
- Volume: ISimpleAudioVolume
- Reprodução: SendInput (play/pause/próxima/anterior)
- Jogos: Steam Scanner (AppID), ShellExecute
- Sistema: `shutdown.exe` cmd (delay configurável)

### 📊 **Context & State Management**

- **Telegram Update**: Chat ID, User ID, Message content
- **Session Data** (ConversationHandler): command name, intenção (auto_learn)
- **Global State** (mic_listener): chat_id, bot, event loop (thread-safe)
- **Logging**: Arquivo `orion.log` + console (INFO+)

### ⚡ **Fluxo Completo (Exemplo)**

**Usuário fala "Spotify Beatles" ao microfone:**

1. `mic_listener` detecta "orion" no Whisper
2. `parse_intent("spotify beatles")` → `{"action": "spotify", "query": "beatles"}`
3. `executar_intent()` → `.startfile("spotify:search:beatles")`
4. Spotify abre buscando Beatles
5. Bot manda → 🎵 Tocando no Spotify: *beatles*

**Usuário digita "/toca_som_5" (comando desconhecido):**

1. `auto_learn.handle_unknown_command()` detecta
2. Bot pergunta: "O que você quer que `/toca_som_5` faça?"
3. User responde: "aumenta o volume em 5%"
4. Claude gera handler (validado)
5. Salvo e registrado em runtime
6. Menu Telegram atualizado
7. Comando disponível imediatamente (sem restart)

### 🔐 **Configuração**

```bash
# .env (obrigatório)
TOKEN_TELEGRAM=seu_token_aqui
ANTHROPIC_API_KEY=sk-ant-...
```

**Instalação:**
```bash
uv sync          # instala deps
uv run python main.py
```

### 💡 **Pontos-Chave da Arquitetura**

✅ **Modular**: Handlers separados por feature
✅ **Dinâmico**: IA gera handlers em runtime
✅ **Assíncrono**: Telegram (asyncio) + mic (threading daemon)
✅ **Offline**: Transcrição Whisper sem enviar áudio
✅ **Inteligente**: NLP com regex + Claude para contexto
✅ **Notificações**: Feedback imediato no Telegram

**Stack resumido**: Python 3.11 → Telegram API → Claude → Whisper → Windows Automation
