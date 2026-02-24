# claude-stt

Local, privacy-focused speech-to-text for [Claude Code](https://claude.ai/code).

Speak into your microphone — your words appear directly in Claude Code. No copy-pasting, no cloud APIs, no audio ever leaving your device.

## How it works

- Records audio from your macOS microphone using [sox](https://sox.sourceforge.net/)
- Auto-stops when you stop talking (silence detection)
- Transcribes locally using [whisper-cpp](https://github.com/ggml-org/whisper.cpp) with the `base.en` model
- Returns the transcript to Claude Code via a [Model Context Protocol](https://modelcontextprotocol.io/) server

## Requirements

- macOS (Ventura 13+ recommended)
- [Homebrew](https://brew.sh)
- Node.js ≥ 18
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

## Usage

In any Claude Code session:

```
/dictate
```

Speak naturally. Recording auto-stops after ~2 seconds of silence. Claude receives the transcript and asks how you'd like to use it.

Or just tell Claude: *"Listen to what I say"* — it will call the `dictate` tool directly.

## Configuration

The `dictate` tool accepts optional parameters:

| Parameter | Default | Description |
|---|---|---|
| `max_duration` | `30` | Max recording length in seconds (5–120) |
| `silence_duration` | `2` | Seconds of silence before auto-stop (1–10) |
| `model_path` | `~/.claude/mcp-servers/claude-stt/models/ggml-base.en.bin` | Path to GGML model |

### Changing the whisper model

Swap models by editing `DEFAULT_MODEL_PATH` in `~/.claude/mcp-servers/claude-stt/index.js`:

| Model | Size | Speed | Best for |
|---|---|---|---|
| `ggml-tiny.en.bin` | 75MB | Fastest | Quick commands |
| `ggml-base.en.bin` | 142MB | Fast | General dictation *(default)* |
| `ggml-small.en.bin` | 466MB | Medium | Better accuracy / accents |

Download additional models from [Hugging Face](https://huggingface.co/ggerganov/whisper.cpp).

### Noisy environment

If recording never auto-stops (background fan, AC), increase the silence threshold in `~/.claude/mcp-servers/claude-stt/index.js`:

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
- No network requests are made by the MCP server
- Temp WAV files are deleted immediately after transcription
- The whisper model runs fully offline via whisper-cpp

## License

MIT
