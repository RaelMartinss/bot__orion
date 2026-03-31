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

# WhatsApp server (Node.js — run separately, first time only needs QR scan)
cd whatsapp_server && node server.js
```

Dependencies are managed with `uv` and declared in `pyproject.toml`. Requires Python 3.11+.
WhatsApp server requires Node.js and dependencies in `whatsapp_server/package.json`.

## Architecture

**Orion** is a Telegram bot for remote Windows PC control via voice/text, with AI-powered dynamic command learning, smart notifications, browser automation, and WhatsApp integration.

### Entry Point

`main.py` initializes the Telegram bot (polling mode), registers all handlers, starts the microphone listener as a daemon thread, and launches background alert tasks.

### Layer Breakdown

| Layer | Location | Responsibility |
|---|---|---|
| Telegram handlers | `handlers/` | One file per feature (voice, jogos, midia, volume, controle, sistema, auto_learn) |
| AI-generated handlers | `handlers/custom/` | Auto-generated at runtime by Claude, loaded dynamically |
| Core utilities | `utils/` | Claude client, intent parser, executor, mic listener, transcriber, memory, TTS, presence, alerts |
| ML classification | `ml/` | scikit-learn intent classifier + training data (`treino.json`) |
| Plugins | `plugins/` | Independent feature modules (futebol, gmail, agenda, files, alarme_agua) |
| User memory | `memoria/` | Per-user JSON files + Google token + presence config |
| WhatsApp server | `whatsapp_server/` | Node.js + whatsapp-web.js REST server on port 3131 |

### Intent Pipeline

All inputs (Telegram text, Telegram audio, PC microphone) converge to the **same** pipeline:

```
Input
  → extract_orion_command()       # strip wake word if present
  → resolver_contexto()           # resolve pronoun/redirect context
  → parse_intent()                # regex patterns (primary)
  → interpretar_comando()         # scikit-learn ML (fallback, skipped for browser cmds)
  → extrair_intent_estruturado()  # Claude fast extraction (fallback, skipped for browser cmds)
  → try_local_route()             # plugin system
  → run_orchestrator()            # Claude agent with full tool suite
```

`parse_intent()` returns `{action, query, delay, ...}`. Browser-related commands skip ML and Claude structured extraction to avoid misclassification as games.

### Actions registered in intent_parser

| Category | Actions |
|---|---|
| Media | `spotify`, `youtube`, `netflix`, `pausar`, `proxima`, `anterior`, `reiniciar_video` |
| Volume | `vol_up`, `vol_down`, `vol_set`, `mute` |
| System | `desligar`, `reiniciar`, `bloquear_pc`, `fechar_app`, `cancelar` |
| Browser | `browser_abrir`, `browser_fechar` + web patterns → orchestrator |
| Games | `jogo` |
| Files | `file_search`, `file_open_file`, `file_open_folder`, `file_organize`, `file_reindex` |
| Agenda | `agenda_hoje`, `agenda_semana`, `agenda_proximo`, `agenda_criar` |
| Email | `email_inbox`, `email_ler`, `email_buscar`, `email_nao_lidos`, `email_enviar` |
| WhatsApp | `whatsapp_enviar`, `whatsapp_status`, `whatsapp_qr` |
| Vision | `vision_on`, `vision_off`, `vision_analyze` |
| Projects | `open_project`, `open_app`, `run_project`, `create_project` |
| Presence | `configurar_pendrive` |
| Misc | `saudacao`, `date_time`, `set_alarm`, `set_favorite_team` |

### Dynamic Handler Generation (Auto-Learn)

When a user sends an unknown command, `handlers/auto_learn.py` triggers a ConversationHandler that:
1. Asks the user to describe the intent
2. Sends the description to Claude (`claude-sonnet-4-6`) via `utils/claude_client.py`
3. Validates the generated Python code with AST checks (`utils/code_validator.py`)
4. Saves to `handlers/custom/<name>.py` and registers it at runtime (`utils/handler_registry.py`)
5. Updates the Telegram command menu — no restart needed

### Voice / Microphone

- **Telegram audio**: `handlers/voice.py` downloads the OGG file → `utils/transcriber.py` (Faster Whisper, model `small`, CPU int8) → intent pipeline
- **PC microphone**: `utils/mic_listener.py` runs as a daemon thread, uses `sounddevice` + **Silero VAD** (PyTorch, fallback to RMS threshold), triggers on wake word "orion" with fuzzy matching (cutoff 0.72). Pipeline is identical to Telegram pipeline including ML and Claude structured extraction fallbacks.

### AI Integration

- `utils/claude_client.py`: Direct HTTPS to Anthropic API, model `claude-sonnet-4-6`, used for code generation, structured intent extraction, and orchestration
- `utils/orchestrator.py`: Full Claude agent loop with tool calling. Handles complex tasks, browser automation, web search. Has offline fallback via Ollama (prefers `qwen2.5:3b` for tool support, falls back to text-only with hallucination guard)
- `utils/prompt_builder.py`: Builds structured prompts for handler generation
- `utils/openai_client.py`: Secondary AI fallback (OpenAI GPT-4o-mini)

### Offline Fallback (Ollama)

When the Anthropic API is unreachable, `orchestrator.py` falls back to local Ollama:
1. Prefers models with tool calling support: `qwen2.5:3b` > `llama3.2:3b` > `mistral` > others
2. If selected model doesn't support tools (e.g. `gemma3:4b`): downloads `qwen2.5:3b` in background, switches to text-only mode with explicit anti-hallucination prompt
3. Tool error codes: `[AUTO_REPAIR]`, `[ERRO_REDE]`, `[ERRO_TIMEOUT]`, `[ERRO_REPARAVEL]` — Claude interprets these and responds gracefully without showing raw errors

### Browser Automation

`utils/browser_manager.py` wraps Playwright (Chromium, headless=False — visible window):
- Auto-installs Chromium if missing (`playwright install chromium`)
- Singleton pattern with async lock
- Methods: `goto(url)`, `read_page()`, `click(selector)`, `fill(selector, text)`, `close()`
- Exposed to Claude as tools: `browser_goto`, `browser_read`, `browser_click`, `browser_fill`, `browser_close`

### Memory

`utils/memoria.py` manages per-user JSON files in `memoria/`:
- `curto_prazo_<chat_id>.json` — session context (last N messages)
- `longo_prazo_<chat_id>.json` — persistent preferences, learned commands, facts
- `presenca_config.json` — USB presence token config
- `google_token.json` — Google Calendar OAuth token

### Presence Detection

`utils/presence.py` determines if user is physically at the PC (voice response) or away (Telegram message):
- **Primary**: USB pendrive as physical token — plugged in = present, removed = away
- **Fallback**: `GetLastInputInfo` (keyboard/mouse idle time, threshold 5 min)
- Configure with: *"configura meu pendrive como presença"*

### Smart Notifications

`utils/smart_alerts.py` runs background monitors (started in `main.py`):

| Monitor | Interval | Trigger |
|---|---|---|
| 📥 Downloads | 30s | New completed file in `~/Downloads` |
| 📅 Agenda | 2 min | Google Calendar event starting in ≤15 min |
| 📧 Email | 5 min | New unread Gmail message |

Delivery: Telegram + voice if present, queued for when user returns if absent.

### Daily Alerts

`utils/daily_alerts.py` fires at 08:00 daily: checks if favorite football team plays today via TheSportsDB API, notifies via Telegram + voice.

### WhatsApp Integration

`whatsapp_server/server.js` — Node.js REST server (port 3131):
- Uses `whatsapp-web.js` + `LocalAuth` (session persisted in `whatsapp_server/sessao_wpp/`)
- First run: scan QR Code via WhatsApp → Linked Devices
- Endpoints: `GET /status`, `GET /qr`, `POST /send`, `GET /contatos`

`utils/whatsapp_client.py` — Python wrapper:
- Auto-starts Node server if offline
- Resolves contact names to phone numbers
- Voice commands: *"manda mensagem pro João que já finalizei"*

### Windows Automation

| Feature | API Used |
|---|---|
| Volume | `pycaw` (ISimpleAudioVolume) |
| Media controls | `pyautogui` (play/pause/next/prev/restart) + `pygetwindow` (YouTube focus) |
| Games | `steam_scanner.py` → AppID → `os.startfile()` |
| Shutdown/restart/lock | `subprocess` → `shutdown.exe` / `rundll32` |
| Open apps/URLs | `os.startfile()`, `webbrowser` |
| Browser automation | Playwright Chromium (headed) |
| File management | `plugins/files/` (index, search, organize, open) |

### Concurrency Model

- **Telegram**: `asyncio` event loop (polling)
- **Microphone**: `threading.Thread(daemon=True)` — communicates with asyncio loop via `run_coroutine_threadsafe`
- **Background tasks**: `asyncio.create_task()` for smart_alerts, daily_alerts, vision
- **Browser**: async Playwright with `asyncio.Lock()` singleton

## Configuration

Required `.env` variables:
```
TOKEN_TELEGRAM=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=   # optional fallback
```

Optional setup:
- Google Calendar: `uv run python plugins/agenda.py --setup` (OAuth flow, saves `memoria/google_token.json`)
- WhatsApp: `cd whatsapp_server && node server.js` then scan QR Code once
- USB Presence: say *"configura meu pendrive como presença"* with pendrive plugged in

## Bot Personality

ORION behaves like a Jarvis-style assistant (see `ORION_PERSONALIDADE.md`): elegant, technical, confident, subtly sarcastic. Natural Portuguese flow — never robotic, never lists steps. Never shows raw error messages to the user.
