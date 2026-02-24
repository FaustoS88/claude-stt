#!/usr/bin/env python3
"""
claude-stt PTT daemon — Push-to-Talk mode.

Hold Right Option (⌥) to record, release to stop and transcribe.
Each segment is appended to session.txt and copied to the clipboard.
Paste (Cmd+V) directly into Claude Code.

Commands (type in terminal):
    c / clear   — clear session and clipboard, start fresh
    q / quit    — exit
    Ctrl+C      — exit

Usage:
    python3 ~/.claude/mcp-servers/claude-stt/ptt.py

Requirements:
    brew install sox whisper-cpp
    pip3 install pynput
    Terminal must have Accessibility permission (System Settings > Privacy > Accessibility)
"""

import os
import sys
import subprocess
import tempfile
import threading
from pathlib import Path

from pynput import keyboard

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
        pass

def clear_clipboard():
    """Clear the system clipboard."""
    try:
        subprocess.run(["pbcopy"], input=b"", check=True)
    except Exception:
        pass

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

def clear_session():
    """Clear session file, clipboard, and print confirmation."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    clear_clipboard()
    print("\n✓ Session cleared — clipboard emptied. Ready for a fresh start.\n")
    print("Session: (empty)\n")

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
    # Always start fresh
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

    print("claude-stt PTT — hold Right Option (⌥) to record, release to stop")
    print("Type 'c' to clear session  |  Ctrl+C to exit")
    print("Transcript auto-copied to clipboard → Cmd+V to paste\n")
    print("Session: (empty)\n")

    # Shared state protected by a lock
    lock = threading.Lock()
    state = {"recording": False, "proc": None, "wav_path": None}

    def start_recording():
        fd, wav = tempfile.mkstemp(suffix=".wav", prefix="claude-stt-ptt-")
        os.close(fd)
        state["wav_path"] = wav
        state["proc"] = record_audio(rec_bin, wav)
        state["recording"] = True
        print("● RECORDING — release Right Option (⌥) to stop", flush=True)

    def stop_and_transcribe():
        proc = state["proc"]
        wav = state["wav_path"]
        state["proc"] = None
        state["wav_path"] = None
        state["recording"] = False

        # Stop recording
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        # Transcribe
        print("  Transcribing...", end="", flush=True)
        try:
            text = transcribe_audio(whisper_bin, wav)
        except Exception as e:
            print(f"\r✗ Transcription error: {e}   ")
            text = None
        finally:
            try:
                os.unlink(wav)
            except OSError:
                pass

        if text:
            session = append_session(text)
            copy_to_clipboard(session)
            print(f'\r✓ "{text}"   ')
            print(f"\nSession (copied to clipboard): {session}\n")
        else:
            print("\r✗ (no speech detected)   \n")

    def on_press(key):
        try:
            with lock:
                if key == keyboard.Key.alt_r and not state["recording"]:
                    start_recording()
        except Exception as e:
            print(f"\n✗ Key handler error: {e}", flush=True)

    def on_release(key):
        try:
            with lock:
                if key == keyboard.Key.alt_r and state["recording"]:
                    stop_and_transcribe()
        except Exception as e:
            print(f"\n✗ Key handler error: {e}", flush=True)

    # Start global key listener in daemon thread
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()

    # Main thread: read stdin for commands
    try:
        while True:
            try:
                cmd = input().strip().lower()
            except EOFError:
                break
            if cmd in ("c", "clear"):
                with lock:
                    if state["recording"]:
                        print("  (finish recording first)")
                        continue
                clear_session()
            elif cmd in ("q", "quit", "exit"):
                break
            elif cmd:
                print(f"  Unknown command: '{cmd}' — type 'c' to clear, 'q' to quit")
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup if interrupted mid-recording
        with lock:
            if state["proc"] is not None:
                state["proc"].terminate()
                try:
                    state["proc"].wait(timeout=3)
                except subprocess.TimeoutExpired:
                    state["proc"].kill()
            if state["wav_path"] and Path(state["wav_path"]).exists():
                try:
                    os.unlink(state["wav_path"])
                except OSError:
                    pass
        listener.stop()
        print("\nExiting. Session preserved in session.txt.")

# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rec_bin = check_binary("rec")
    whisper_bin = check_binary("whisper-cli")
    check_model()
    run(rec_bin, whisper_bin)
