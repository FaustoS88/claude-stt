# claude-stt

Local, privacy-focused speech-to-text for [Claude Code](https://claude.ai/code).

Speak into your microphone — your words appear directly in Claude Code. No copy-pasting, no cloud APIs, no audio ever leaving your device.

Two modes:
- **`/dictate`** — silence-detection, one continuous burst, auto-stops on pause
- **PTT** — hold ⌥ to record, release to transcribe, repeat as many times as needed

## How it works

- Records audio from your macOS microphone using [sox](https://sox.sourceforge.net/)
- Transcribes locally using [whisper-cpp](https://github.com/ggml-org/whisper.cpp) with the `base.en` model
- Returns transcripts to Claude Code via a [Model Context Protocol](https://modelcontextprotocol.io/) server

## Requirements

- macOS (Ventura 13+ recommended)
- [Homebrew](https://brew.sh)
- Node.js ≥ 18
- Python 3 (for PTT mode)
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
2. Install `pynput` via pip3 (for PTT mode)
3. Download the `ggml-base.en.bin` whisper model (~142MB)
4. Register the MCP server with Claude Code
5. Install the `/dictate` skill

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

Best for composing longer messages where you need to think between sentences. Hold ⌥ to record, release to transcribe, repeat as many times as you need. All segments accumulate into one session. When done, tell Claude to read your dictation.

### One-time macOS setup

PTT uses a global key listener, which requires two permissions:

1. **System Settings → Privacy & Security → Accessibility** → add your terminal app (iTerm2, Terminal, etc.)
2. **System Settings → Privacy & Security → Input Monitoring** → add your terminal app

Restart your terminal after granting both permissions.

### Start the PTT daemon

In a **separate terminal window**:

```bash
python3 ~/.claude/mcp-servers/claude-stt/ptt.py
```

### Usage

```
Hold ⌥ (Right Option) → speak → release → transcript appended to session
Repeat as many times as needed
Ctrl+C → exit daemon (session is preserved)
```

Terminal output:

```
claude-stt PTT — Hold ⌥ (Right Option) to record, release to transcribe
Ctrl+C to exit | 'read my dictation' in Claude → calls get_session

Session: (empty)

● RECORDING...
✓ "hello how are you doing today"

Session: hello how are you doing today

● RECORDING...
✓ "I wanted to ask about the new feature"

Session: hello how are you doing today I wanted to ask about the new feature
```

### Reading the session in Claude Code

When you're done recording segments, tell Claude:

> "Read my dictation"

Claude will call `get_session`, which returns the accumulated text and clears the session file.

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
