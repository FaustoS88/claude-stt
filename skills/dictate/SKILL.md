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
