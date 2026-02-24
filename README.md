# claude-stt

Local, privacy-focused speech-to-text for [Claude Code](https://claude.ai/code).

Speak into your microphone — your words appear directly in Claude Code. No copy-pasting, no cloud APIs, no audio ever leaving your device.

**Cross-platform:** macOS, Windows, Linux.

Two modes:
- **`/dictate`** — silence-detection, one continuous burst, auto-stops on pause. Best for quick messages.
- **PTT** — hold Right Option (macOS) / Right Alt (Windows/Linux) to record, release to stop. All segments accumulate into one message. Send everything to Claude when you're ready.

## How it works

- Records audio from your microphone using [PyAudio](https://people.csail.mit.edu/hubert/pyaudio/) (PTT) or [sox](https://sox.sourceforge.net/) (`/dictate`)
- Transcribes locally using [whisper-cpp](https://github.com/ggml-org/whisper.cpp) with the `base.en` model
- Returns transcripts to Claude Code via a [Model Context Protocol](https://modelcontextprotocol.io/) server

## Requirements

- Node.js >= 18
- Python 3
- [Claude Code CLI](https://claude.ai/code)
- whisper-cpp on PATH

### macOS

```bash
brew install sox whisper-cpp
pip3 install pynput pyaudio pyperclip
```

### Linux (Debian/Ubuntu)

```bash
sudo apt install sox portaudio19-dev python3-pyaudio
pip3 install pynput pyperclip
# Build whisper-cpp from source: https://github.com/ggml-org/whisper.cpp
```

### Windows

```powershell
choco install sox
pip install pynput pyaudio pyperclip
# Download whisper-cpp from: https://github.com/ggml-org/whisper.cpp/releases
# Add the whisper binary to your PATH
```

## Install

### macOS / Linux

```bash
git clone https://github.com/FaustoS88/claude-stt.git
cd claude-stt
chmod +x install.sh
./install.sh
```

### Windows

```powershell
git clone https://github.com/FaustoS88/claude-stt.git
cd claude-stt
.\install.ps1
```

The installer will:
1. Check system dependencies (sox, whisper-cpp, Python packages)
2. Download the `ggml-base.en.bin` whisper model (~142MB)
3. Register the MCP server with Claude Code
4. Install the `/dictate` skill

> **First use:** your OS may prompt for microphone access. Grant it once and it persists.
>
> **macOS PTT:** Terminal needs Accessibility permission (System Settings > Privacy & Security > Accessibility) for global key capture.

---

## Mode 1 — `/dictate` (silence-detection)

Best for short, single-burst messages. Say something, pause, done.

In any Claude Code session:

```
/dictate
```

Or tell Claude: *"Listen to what I say"* — it will call the `dictate` tool directly.

Recording starts immediately and auto-stops after ~3 seconds of silence (configurable).

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `max_duration` | `30` | Max recording length in seconds (5–120) |
| `silence_duration` | `3` | Seconds of silence before auto-stop (1–10) |
| `model_path` | `~/.claude/mcp-servers/claude-stt/models/ggml-base.en.bin` | Path to GGML model |

---

## Mode 2 — PTT (Push-to-Talk)

PTT is a **message staging area**. The idea:

1. Hold **Right Option** (macOS) or **Right Alt** (Windows/Linux) → recording starts
2. Release → recording stops, transcribed, shown in terminal, **copied to clipboard**
3. Read it, decide it's good
4. Record again → new segment appended, clipboard updated
5. When the full message is ready → **Cmd+V** (macOS) / **Ctrl+V** (Windows/Linux) in Claude Code → send

No wasted API calls. PTT is a standalone clipboard tool — it works with Claude Code, any browser, any text field.

### Start the PTT daemon

In a **separate terminal window**:

```bash
python3 ~/.claude/mcp-servers/claude-stt/ptt.py
```

### Usage

```
Hold Right Option/Alt  → recording starts
Release                → stops, transcribes, copies to clipboard
Type 'c' + Enter       → clear session and clipboard (start fresh)
Type 'q' + Enter       → quit
Ctrl+C                 → quit
```

Terminal output:

```
claude-stt PTT — hold Right Option (⌥) to record, release to stop
Type 'c' to clear session  |  Ctrl+C to exit
Transcript auto-copied to clipboard → Cmd+V to paste

Session: (empty)

● RECORDING — release Right Option (⌥) to stop
✓ "hello, I wanted to ask about the new feature"

Session (copied to clipboard): hello, I wanted to ask about the new feature

● RECORDING — release Right Option (⌥) to stop
✓ "specifically the authentication flow"

Session (copied to clipboard): hello, I wanted to ask about the new feature specifically the authentication flow
```

### Sending to Claude

Switch to Claude Code, paste in the input field, hit Enter. Done.

### MCP tools (PTT)

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
const SILENCE_THRESHOLD = "3.0%"; // default: "0.1%"
```

## Platform notes

### macOS
- PTT requires Terminal to have **Accessibility** permission (System Settings > Privacy & Security > Accessibility)
- Microphone access is granted per-app on first use

### Windows
- No special permissions needed for PTT key capture
- Install sox via `choco install sox` or download from [sox.sourceforge.net](https://sox.sourceforge.net/)
- whisper-cpp: download pre-built binaries from [GitHub releases](https://github.com/ggml-org/whisper.cpp/releases) and add to PATH

### Linux
- PTT requires X11 (Wayland support for pynput is limited)
- Install PortAudio: `sudo apt install portaudio19-dev`
- For clipboard: `xclip` or `xsel` must be installed (`sudo apt install xclip`)

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
