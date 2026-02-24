# claude-stt

Local, privacy-focused speech-to-text for [Claude Code](https://claude.ai/code).

Speak into your microphone — your words appear directly in Claude Code. No copy-pasting, no cloud APIs, no audio ever leaving your device.

Two modes:
- **`/dictate`** — silence-detection, one continuous burst, auto-stops on pause. Best for quick messages.
- **PTT** — press Enter to record, Enter to stop, read the transcript, think, record again. All segments accumulate into one message. Send everything to Claude when you're ready.

## How it works

- Records audio from your macOS microphone using [sox](https://sox.sourceforge.net/)
- Transcribes locally using [whisper-cpp](https://github.com/ggml-org/whisper.cpp) with the `base.en` model
- Returns transcripts to Claude Code via a [Model Context Protocol](https://modelcontextprotocol.io/) server

## Requirements

- **macOS only** (uses `sox`, `whisper-cpp`, and `pbcopy` — Homebrew/macOS primitives)
- [Homebrew](https://brew.sh)
- Node.js ≥ 18
- Python 3 (stdlib only — no extra packages needed)
- [Claude Code CLI](https://claude.ai/code)

## Install

```bash
git clone https://github.com/FaustoS88/claude-stt.git
cd claude-stt
chmod +x install.sh
./install.sh
```

The installer will:
1. Install `sox` and `whisper-cpp` via Homebrew (if not already present)
2. Download the `ggml-base.en.bin` whisper model (~142MB)
3. Register the MCP server with Claude Code
4. Install the `/dictate` skill

> **First use:** macOS will prompt for microphone access for your terminal app. Grant it once and it persists.

---

## Mode 1 — `/dictate` (silence-detection)

Best for short, single-burst messages. Say something, pause, done.

In any Claude Code session:

```
/dictate
```

Or tell Claude: *"Listen to what I say"* — it will call the `dictate` tool directly.

Recording starts immediately and auto-stops after ~2 seconds of silence (configurable).

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `max_duration` | `30` | Max recording length in seconds (5–120) |
| `silence_duration` | `2` | Seconds of silence before auto-stop (1–10) |
| `model_path` | `~/.claude/mcp-servers/claude-stt/models/ggml-base.en.bin` | Path to GGML model |

---

## Mode 2 — PTT (Push-to-Talk)

PTT is a **message staging area**. The idea:

1. Speak a thought → it's transcribed, shown in the terminal, and **copied to your clipboard**
2. Read it, decide it's good
3. Think of more to add → record again → new segment appended, clipboard updated
4. Repeat as many times as you need — no pressure to speak in one go
5. When the full message is ready → **Cmd+V** in Claude Code's input field → send

No extra packages, no macOS permissions, no wasted API calls. PTT is a standalone clipboard tool — it works with Claude Code, any browser, any text field.

### Start the PTT daemon

In a **separate terminal window**:

```bash
python3 ~/.claude/mcp-servers/claude-stt/ptt.py
```

### Usage

```
Press ENTER → recording starts
Press ENTER → recording stops, transcribed, appended to session
Repeat as many times as needed
Ctrl+C → exit daemon (session is preserved)
```

Terminal output:

```
claude-stt PTT — press ENTER to start recording, ENTER again to stop
Ctrl+C to exit

Session: (empty)

Press ENTER to record...
● RECORDING — press ENTER to stop
✓ "hello, I wanted to ask about the new feature"

Session (copied to clipboard): hello, I wanted to ask about the new feature

Press ENTER to record...
● RECORDING — press ENTER to stop
✓ "specifically the authentication flow"

Session (copied to clipboard): hello, I wanted to ask about the new feature specifically the authentication flow
```

### Sending to Claude

Switch to Claude Code, **Cmd+V** in the input field, hit Enter. Done — no extra API call, no extra step.

### New MCP tools (PTT)

| Tool | Description |
|---|---|
| `get_session` | Read accumulated session. `clear: true` (default) deletes after reading. |
| `clear_session` | Discard the session without reading. |

**Shared state:** `~/.claude/mcp-servers/claude-stt/session.txt` — plain text, one space between segments.

---

## Changing the whisper model

Swap models by editing `DEFAULT_MODEL_PATH` in `~/.claude/mcp-servers/claude-stt/index.js`:

| Model | Size | Speed | Best for |
|---|---|---|---|
| `ggml-tiny.en.bin` | 75MB | Fastest | Quick commands |
| `ggml-base.en.bin` | 142MB | Fast | General dictation *(default)* |
| `ggml-small.en.bin` | 466MB | Medium | Better accuracy / accents |

Download additional models from [Hugging Face](https://huggingface.co/ggerganov/whisper.cpp).

## Noisy environment

If `/dictate` never auto-stops (loud fan, AC, etc.), increase the silence threshold in `~/.claude/mcp-servers/claude-stt/index.js`:

```js
const SILENCE_THRESHOLD = "3.0%"; // default: "1.0%"
```

## Uninstall

```bash
claude mcp remove claude-stt --scope user
rm -rf ~/.claude/mcp-servers/claude-stt
rm -rf ~/.claude/skills/dictate
```

## Privacy

- Audio is captured, transcribed, and discarded entirely on your machine
- No network requests are made by the MCP server or PTT daemon
- Temp WAV files are deleted immediately after transcription
- The session file (`session.txt`) is cleared automatically when Claude reads it
- The whisper model runs fully offline via whisper-cpp

## License

MIT
