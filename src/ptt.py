#!/usr/bin/env python3
"""
claude-stt PTT daemon — Push-to-Talk mode.

Hold Right Option/Alt to record, release to stop and transcribe.
Each segment is appended to session.txt and copied to the clipboard.
Paste (Cmd+V / Ctrl+V) directly into Claude Code.

Commands (type in terminal):
    c / clear   — clear session and clipboard, start fresh
    q / quit    — exit
    Ctrl+C      — exit

Usage:
    python3 ~/.claude/mcp-servers/claude-stt/ptt.py

Requirements:
    pip3 install pynput pyaudio pyperclip
    whisper-cpp must be on PATH
    macOS: Terminal needs Accessibility permission (System Settings > Privacy > Accessibility)

Cross-platform: macOS, Windows, Linux (X11)
"""

import os
import platform
import queue
import re
import shutil
import sys
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import pyaudio
import pyperclip
from pynput import keyboard

# ─── Platform detection ──────────────────────────────────────────────────────

SYSTEM = platform.system()  # "Darwin", "Windows", "Linux"

# ─── Paths ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
INSTALL_DIR = Path.home() / ".claude" / "mcp-servers" / "claude-stt"
# Check installed location first, fall back to script-relative
_model_installed = INSTALL_DIR / "models" / "ggml-base.en.bin"
_model_local = SCRIPT_DIR / "models" / "ggml-base.en.bin"
MODEL_PATH = _model_installed if _model_installed.exists() else _model_local
SESSION_FILE = Path.home() / ".claude" / "mcp-servers" / "claude-stt" / "session.txt"

# ─── Startup checks ──────────────────────────────────────────────────────────

def extend_path():
    """Ensure common install locations are on PATH."""
    if SYSTEM == "Darwin":
        extras = ["/opt/homebrew/bin", "/usr/local/bin"]
    elif SYSTEM == "Linux":
        extras = ["/usr/local/bin", str(Path.home() / ".local" / "bin")]
    else:
        extras = []
    current = os.environ.get("PATH", "")
    for d in extras:
        if d not in current:
            current = d + os.pathsep + current
    os.environ["PATH"] = current

def find_whisper_binary():
    """Find the whisper-cpp binary across platforms."""
    for name in ("whisper-cli", "whisper-cpp", "whisper", "main"):
        path = shutil.which(name)
        if path:
            return path
    return None

def whisper_install_hint():
    if SYSTEM == "Darwin":
        return "brew install whisper-cpp"
    elif SYSTEM == "Linux":
        return "Build from source: https://github.com/ggml-org/whisper.cpp"
    else:
        return "Download from: https://github.com/ggml-org/whisper.cpp/releases"

def check_whisper(whisper_bin):
    if not whisper_bin:
        print("ERROR: whisper-cpp not found on PATH.")
        print(f"  Fix: {whisper_install_hint()}")
        sys.exit(1)

def check_model():
    if not MODEL_PATH.exists():
        print(f"ERROR: Whisper model not found at {MODEL_PATH}")
        print(f"  Fix: curl -L -o '{MODEL_PATH}' \\")
        print(f"    'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin'")
        sys.exit(1)

def check_pyaudio():
    """Verify PyAudio can open an input stream (microphone available)."""
    pa = pyaudio.PyAudio()
    try:
        info = pa.get_default_input_device_info()
        if info is None:
            print("ERROR: No default input device (microphone) found.")
            sys.exit(1)
    except (IOError, OSError):
        print("ERROR: No input device (microphone) available.")
        if SYSTEM == "Linux":
            print("  Fix: sudo apt install portaudio19-dev python3-pyaudio")
        sys.exit(1)
    finally:
        pa.terminate()

# ─── Clipboard (cross-platform via pyperclip) ───────────────────────────────

def copy_to_clipboard(text):
    try:
        pyperclip.copy(text)
    except Exception:
        pass

def clear_clipboard():
    try:
        pyperclip.copy("")
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
    print("\n\u2713 Session cleared \u2014 clipboard emptied. Ready for a fresh start.\n")
    print("Session: (empty)\n")

# ─── Audio recording (cross-platform via PyAudio) ────────────────────────────

RATE = 16000
CHANNELS = 1
CHUNK = 1024
FORMAT = pyaudio.paInt16

class Recorder:
    """Records audio from the default input device using PyAudio.

    Call start() to begin recording, stop() to finish and write a valid WAV.
    """

    def __init__(self, wav_path):
        self.wav_path = wav_path
        self._frames = queue.Queue()
        self._pa = pyaudio.PyAudio()
        self._stream = None

    def start(self):
        self._stream = self._pa.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            stream_callback=self._callback,
        )
        self._stream.start_stream()

    def _callback(self, in_data, frame_count, time_info, status):
        self._frames.put(in_data)
        return (None, pyaudio.paContinue)

    def stop(self):
        """Stop recording and write accumulated audio to WAV file."""
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
        self._pa.terminate()
        chunks = []
        while not self._frames.empty():
            chunks.append(self._frames.get())
        if chunks:
            with wave.open(self.wav_path, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit = 2 bytes
                wf.setframerate(RATE)
                wf.writeframes(b"".join(chunks))

# ─── Transcription ───────────────────────────────────────────────────────────

WHISPER_ARTIFACT = re.compile(r"^\[.*\]$|^\(.*\)$")

def transcribe_audio(whisper_bin, wav_path):
    """Run whisper-cli, return stripped transcript text."""
    args = [whisper_bin, "-m", str(MODEL_PATH), "-f", wav_path, "--no-timestamps", "-l", "en"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"whisper-cli failed (code {result.returncode}): {result.stderr.strip()}")
    lines = [l.strip() for l in result.stdout.split("\n")
             if l.strip() and not WHISPER_ARTIFACT.match(l.strip())]
    return " ".join(lines).strip()

# ─── Platform-aware labels ───────────────────────────────────────────────────

def ptt_key_label():
    if SYSTEM == "Darwin":
        return "Right Option (\u2325)"
    return "Right Alt"

def paste_shortcut():
    if SYSTEM == "Darwin":
        return "Cmd+V"
    return "Ctrl+V"

# ─── Main loop ───────────────────────────────────────────────────────────────

def run(whisper_bin):
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

    key_label = ptt_key_label()
    paste_key = paste_shortcut()
    print(f"claude-stt PTT \u2014 hold {key_label} to record, release to stop")
    print(f"Type 'c' to clear session  |  Ctrl+C to exit")
    print(f"Transcript auto-copied to clipboard \u2192 {paste_key} to paste\n")
    print("Session: (empty)\n")

    lock = threading.Lock()
    state = {"recording": False, "recorder": None, "wav_path": None}

    def start_recording():
        fd, wav = tempfile.mkstemp(suffix=".wav", prefix="claude-stt-ptt-")
        os.close(fd)
        state["wav_path"] = wav
        recorder = Recorder(wav)
        recorder.start()
        state["recorder"] = recorder
        state["recording"] = True
        print(f"\u25cf RECORDING \u2014 release {key_label} to stop", flush=True)

    def stop_and_transcribe():
        recorder = state["recorder"]
        wav = state["wav_path"]
        state["recorder"] = None
        state["wav_path"] = None
        state["recording"] = False

        recorder.stop()

        print("  Transcribing...", end="", flush=True)
        try:
            text = transcribe_audio(whisper_bin, wav)
        except Exception as e:
            print(f"\r\u2717 Transcription error: {e}   ")
            text = None
        finally:
            try:
                os.unlink(wav)
            except OSError:
                pass

        if text:
            session = append_session(text)
            copy_to_clipboard(session)
            print(f'\r\u2713 "{text}"   ')
            print(f"\nSession (copied to clipboard): {session}\n")
        else:
            print("\r\u2717 (no speech detected)   \n")

    def on_press(key):
        try:
            with lock:
                if key == keyboard.Key.alt_r and not state["recording"]:
                    start_recording()
        except Exception as e:
            print(f"\n\u2717 Key handler error: {e}", flush=True)

    def on_release(key):
        try:
            with lock:
                if key == keyboard.Key.alt_r and state["recording"]:
                    stop_and_transcribe()
        except Exception as e:
            print(f"\n\u2717 Key handler error: {e}", flush=True)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()

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
                print(f"  Unknown command: '{cmd}' \u2014 type 'c' to clear, 'q' to quit")
    except KeyboardInterrupt:
        pass
    finally:
        with lock:
            if state["recorder"] is not None:
                try:
                    state["recorder"].stop()
                except Exception:
                    pass
            if state["wav_path"] and Path(state["wav_path"]).exists():
                try:
                    os.unlink(state["wav_path"])
                except OSError:
                    pass
        listener.stop()
        print("\nExiting. Session preserved in session.txt.")

# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    extend_path()
    whisper_bin = find_whisper_binary()
    check_whisper(whisper_bin)
    check_model()
    check_pyaudio()
    run(whisper_bin)
