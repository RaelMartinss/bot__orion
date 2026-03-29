# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run the bot
uv run python main.py

# Alternative desktop launcher
uv run python orion_desktop.py
```

Dependencies are managed with `uv` and declared in `pyproject.toml`. Requires Python 3.11+.

## Architecture

**Orion** is a Telegram bot for remote Windows PC control via voice/text, with AI-powered dynamic command learning.

### Entry Point

`main.py` initializes the Telegram bot (polling mode), registers all handlers, and starts the microphone listener as a daemon thread.

### Layer Breakdown

| Layer | Location | Responsibility |
|---|---|---|
| Telegram handlers | `handlers/` | One file per feature (voice, jogos, midia, volume, controle, sistema, auto_learn) |
| AI-generated handlers | `handlers/custom/` | Auto-generated at runtime by Claude, loaded dynamically |
| Core utilities | `utils/` | Claude client, intent parser, executor, mic listener, transcriber, memory, TTS |
| ML classification | `ml/` | scikit-learn intent classifier + training data (`treino.json`) |
| Plugins | `plugins/` | Independent feature modules (futebol, gmail, proximo_jogo, ultimo_jogo) |
| User memory | `memoria/` | Per-user JSON files (`curto_prazo_<id>.json`, `longo_prazo_<id>.json`) |

### Intent Pipeline

All inputs (Telegram text, Telegram audio, PC microphone) converge to the same pipeline:

```
Input → Normalize PT-BR text → intent_parser.parse_intent() → executor.executar_intent() → response
```

`parse_intent()` uses regex patterns (primary) + scikit-learn classifier (secondary) and returns `{action, query, delay, confidence}`.

### Dynamic Handler Generation (Auto-Learn)

When a user sends an unknown command, `handlers/auto_learn.py` triggers a ConversationHandler that:
1. Asks the user to describe the intent
2. Sends the description to Claude (`claude-sonnet-4-6`) via `utils/claude_client.py`
3. Validates the generated Python code with AST checks (`utils/code_validator.py`)
4. Saves to `handlers/custom/<name>.py` and registers it at runtime (`utils/handler_registry.py`)
5. Updates the Telegram command menu — no restart needed

### Voice / Microphone

- **Telegram audio**: `handlers/voice.py` downloads the OGG file → `utils/transcriber.py` (Faster Whisper, model `small`) → intent pipeline
- **PC microphone**: `utils/mic_listener.py` runs as a daemon thread, uses sounddevice + WebRTC VAD, triggers on wake word "orion" detected in transcribed text, then notifies via Telegram

### AI Integration

- `utils/claude_client.py`: Direct HTTPS to Anthropic API, model `claude-sonnet-4-6`, used for code generation and natural language understanding
- `utils/prompt_builder.py`: Builds structured prompts for handler generation
- `utils/openai_client.py`: Optional secondary AI (OpenAI)

### Memory

`utils/memoria.py` manages per-user JSON files in `memoria/`:
- `curto_prazo_<chat_id>.json` — session context
- `longo_prazo_<chat_id>.json` — persistent preferences and learned commands

### Windows Automation

| Feature | API Used |
|---|---|
| Volume | `pycaw` (ISimpleAudioVolume) |
| Media controls | `pyautogui` SendInput (play/pause/next/prev) |
| Games | `steam_scanner.py` → AppID → `os.startfile()` |
| Shutdown/restart | `subprocess` → `shutdown.exe` |
| Open apps/URLs | `os.startfile()`, `webbrowser` |

### Concurrency Model

- **Telegram**: `asyncio` event loop (polling)
- **Microphone**: `threading.Thread(daemon=True)` — thread-safe state shared via module-level globals in `mic_listener.py` (`chat_id`, `bot`, `loop`)

## Configuration

Required `.env` variables:
```
TOKEN_TELEGRAM=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=   # optional
```

## Bot Personality

ORION behaves like a Jarvis-style assistant (see `ORION_PERSONALIDADE.md`): elegant, technical, confident, subtly sarcastic. Natural Portuguese flow — never robotic, never lists steps.
