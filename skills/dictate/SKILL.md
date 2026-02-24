---
name: dictate
description: Record speech from the microphone and transcribe it to text locally using whisper-cpp. Use when the user wants to dictate, speak, or use voice input.
---

Use the `dictate` MCP tool to record from the default macOS microphone and transcribe speech to text.

Steps:
1. Call the `dictate` tool with default parameters
2. Wait for it to finish (recording auto-stops on silence)
3. Show the user the transcript clearly
4. Ask how they'd like to use it — as a message, a task description, code comment, etc.

Only adjust parameters if the user asks:
- `max_duration`: increase for longer dictations (default: 30s, max: 120s)
- `silence_duration`: increase if the user pauses often while speaking (default: 2s)

## PTT (Push-to-Talk) mode

For longer dictations where the user wants to compose in multiple bursts, the user runs the PTT daemon in a separate terminal:

```
python3 ~/.claude/mcp-servers/claude-stt/ptt.py
```

The daemon records each segment while Right Option (⌥) is held, transcribes on release, and appends to a shared session file. The user may repeat as many times as needed.

When the user says "read my dictation" or similar:
1. Call `get_session` — returns the full accumulated text (clears session by default)
2. Show the transcript and ask how they'd like to use it

To discard without reading: call `clear_session`.
