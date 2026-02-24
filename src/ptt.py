#!/usr/bin/env python3
"""
claude-stt PTT daemon — Push-to-Talk mode.

Hold Right Option (⌥) to record, release to transcribe.
Each segment is appended to session.txt.
When done composing, tell Claude "read my dictation" → calls get_session MCP tool.

Usage:
    python3 ~/.claude/mcp-servers/claude-stt/ptt.py

Requirements:
    pip3 install pynput
    brew install sox whisper-cpp
    macOS: grant Accessibility + Input Monitoring to your terminal app
"""

import os
import sys
import queue
import signal
import subprocess
import tempfile
import threading
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
MODEL_PATH = SCRIPT_DIR / "models" / "ggml-base.en.bin"
SESSION_FILE = Path.home() / ".claude" / "mcp-servers" / "claude-stt" / "session.txt"

# ─── Startup checks ──────────────────────────────────────────────────────────

def check_pynput():
    try:
        import pynput  # noqa: F401
    except ImportError:
        print("ERROR: pynput not installed.")
        print("  Fix: pip3 install pynput")
        sys.exit(1)

def check_binary(name):
    """Return full path to binary or exit with a helpful message."""
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

def check_accessibility():
    """Check macOS Accessibility permission — required for global key listener."""
    try:
        import ctypes
        import ctypes.util
        lib = ctypes.util.find_library("ApplicationServices")
        if lib:
            ax = ctypes.cdll.LoadLibrary(lib)
            ax.AXIsProcessTrusted.restype = ctypes.c_bool
            if not ax.AXIsProcessTrusted():
                print("ERROR: Accessibility permission required for global key detection.")
                print("  System Settings → Privacy & Security → Accessibility")
                print("  → add your terminal app (iTerm2, Terminal, etc.)")
                print("  Then restart the terminal app and re-run this script.")
                sys.exit(1)
    except Exception:
        # If we can't check, continue and let pynput fail naturally
        pass

def check_model():
    if not MODEL_PATH.exists():
        print(f"ERROR: Whisper model not found at {MODEL_PATH}")
        print(f"  Fix: curl -L -o '{MODEL_PATH}' \\")
        print(f"    'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin'")
        sys.exit(1)

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
    """Spawn rec (sox) — raw recording, no silence detection, no trim."""
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

# ─── Worker thread ───────────────────────────────────────────────────────────

def worker(event_queue, rec_bin, whisper_bin, stop_event):
    proc = None
    wav_path = None

    while not stop_event.is_set():
        try:
            event = event_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        kind = event[0]

        if kind == "press":
            if proc is not None:
                # Already recording — ignore duplicate presses
                continue
            # Create temp wav file
            fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="claude-stt-ptt-")
            os.close(fd)
            print("\r● RECORDING...    ", end="", flush=True)
            proc = record_audio(rec_bin, wav_path)

        elif kind == "release":
            if proc is None:
                continue
            # Stop recording
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            proc = None

            # Transcribe
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
                print(f'\r✓ "{text}"   ')
                print(f"\nSession: {session}\n")
            else:
                print("\r✗ (no speech detected)   ")

        elif kind == "quit":
            # Kill any in-progress recording
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                if wav_path:
                    try:
                        os.unlink(wav_path)
                    except OSError:
                        pass
            break

# ─── Key listener ────────────────────────────────────────────────────────────

def run(rec_bin, whisper_bin):
    from pynput import keyboard

    eq = queue.Queue()
    stop_event = threading.Event()

    # Kick off worker thread
    t = threading.Thread(target=worker, args=(eq, rec_bin, whisper_bin, stop_event), daemon=True)
    t.start()

    session = read_session()
    print("claude-stt PTT — Hold ⌥ (Right Option) to record, release to transcribe")
    print("Ctrl+C to exit | 'read my dictation' in Claude → calls get_session\n")
    print(f"Session: {session or '(empty)'}\n")

    ptt_key = keyboard.Key.alt_r

    def on_press(key):
        if key == ptt_key:
            eq.put(("press", key))

    def on_release(key):
        if key == ptt_key:
            eq.put(("release", key))

    def handle_sigint(sig, frame):
        print("\n\nExiting PTT daemon. Session preserved in session.txt.")
        eq.put(("quit", None))
        stop_event.set()
        listener.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

    t.join(timeout=5)

# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    check_pynput()
    check_accessibility()
    rec_bin = check_binary("rec")
    whisper_bin = check_binary("whisper-cli")
    check_model()
    run(rec_bin, whisper_bin)
