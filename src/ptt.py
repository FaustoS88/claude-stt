#!/usr/bin/env python3
"""
claude-stt PTT daemon — Push-to-Talk mode.

Press ENTER to start recording, ENTER again to stop and transcribe.
Each segment is appended to session.txt.
When done composing, tell Claude "read my dictation" → calls get_session MCP tool.

Usage:
    python3 ~/.claude/mcp-servers/claude-stt/ptt.py

Requirements:
    brew install sox whisper-cpp
    (no special macOS permissions needed)
"""

import os
import sys
import signal
import subprocess
import tempfile
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
MODEL_PATH = SCRIPT_DIR / "models" / "ggml-base.en.bin"
SESSION_FILE = Path.home() / ".claude" / "mcp-servers" / "claude-stt" / "session.txt"

# ─── Startup checks ──────────────────────────────────────────────────────────

def check_binary(name):
    search = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    for d in search:
        p = Path(d) / name
        if p.exists():
            return str(p)
    print(f"ERROR: '{name}' not found.")
    if name == "rec":
        print("  Fix: brew install sox")
    elif name == "whisper-cli":
        print("  Fix: brew install whisper-cpp")
    sys.exit(1)

def check_model():
    if not MODEL_PATH.exists():
        print(f"ERROR: Whisper model not found at {MODEL_PATH}")
        print(f"  Fix: curl -L -o '{MODEL_PATH}' \\")
        print(f"    'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin'")
        sys.exit(1)

# ─── Clipboard ───────────────────────────────────────────────────────────────

def copy_to_clipboard(text):
    """Copy text to system clipboard (macOS pbcopy)."""
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    except Exception:
        pass  # clipboard is best-effort — don't break the flow

# ─── Session file helpers ─────────────────────────────────────────────────────

def read_session():
    try:
        return SESSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""

def append_session(text):
    current = read_session()
    combined = (current + " " + text).strip() if current else text
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(combined, encoding="utf-8")
    return combined

# ─── Audio pipeline ──────────────────────────────────────────────────────────

def record_audio(rec_bin, wav_path):
    """Spawn rec (sox) — raw recording, no silence detection."""
    args = [rec_bin, "-r", "16000", "-c", "1", "-b", "16", wav_path]
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def transcribe_audio(whisper_bin, wav_path):
    """Run whisper-cli, return stripped transcript text."""
    args = [whisper_bin, "-m", str(MODEL_PATH), "-f", wav_path, "--no-timestamps", "-l", "en"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"whisper-cli failed (code {result.returncode}): {result.stderr.strip()}")
    lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
    return " ".join(lines).strip()

# ─── Main loop ───────────────────────────────────────────────────────────────

def run(rec_bin, whisper_bin):
    # Always start fresh — clear any leftover session from a previous run
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

    print("claude-stt PTT — press ENTER to start recording, ENTER again to stop")
    print("Ctrl+C to exit  |  Cmd+V anywhere to paste accumulated text\n")
    print("Session: (empty)\n")

    proc = None
    wav_path = None

    def cleanup(sig=None, frame=None):
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        if wav_path and Path(wav_path).exists():
            try:
                os.unlink(wav_path)
            except OSError:
                pass
        print("\nExiting. Session preserved in session.txt.")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)

    while True:
        try:
            input("Press ENTER to record...")
        except EOFError:
            cleanup()

        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="claude-stt-ptt-")
        os.close(fd)

        proc = record_audio(rec_bin, wav_path)
        print("● RECORDING — press ENTER to stop")

        try:
            input()
        except EOFError:
            cleanup()

        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        proc = None

        print("  Transcribing...", end="", flush=True)
        try:
            text = transcribe_audio(whisper_bin, wav_path)
        except Exception as e:
            print(f"\r✗ Transcription error: {e}   ")
            text = None
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
            wav_path = None

        if text:
            session = append_session(text)
            copy_to_clipboard(session)
            print(f'\r✓ "{text}"   ')
            print(f"\nSession (copied to clipboard): {session}\n")
        else:
            print("\r✗ (no speech detected)   \n")

# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rec_bin = check_binary("rec")
    whisper_bin = check_binary("whisper-cli")
    check_model()
    run(rec_bin, whisper_bin)
