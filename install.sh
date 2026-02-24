#!/usr/bin/env bash
set -euo pipefail

# ─── claude-stt installer ────────────────────────────────────────────────────
# Installs the claude-stt MCP server and /dictate skill into Claude Code.
# Supports macOS and Linux.
# Requirements: Node.js >= 18, Python 3, Claude Code CLI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_TARGET="$HOME/.claude/mcp-servers/claude-stt"
SKILL_TARGET="$HOME/.claude/skills/dictate"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
MODEL_PATH="$MCP_TARGET/models/ggml-base.en.bin"

OS="$(uname -s)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   claude-stt — local STT for Claude  ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Step 1: System dependencies ───────────────────────────────────────────────
echo "▶ Checking system dependencies..."

if [ "$OS" = "Darwin" ]; then
  # macOS — use Homebrew
  if ! command -v brew &>/dev/null; then
    echo "✗ Homebrew not found. Install from https://brew.sh and re-run."
    exit 1
  fi

  if ! command -v sox &>/dev/null; then
    echo "  Installing sox..."
    brew install sox
  else
    echo "  sox ✓"
  fi

  if ! command -v whisper-cli &>/dev/null; then
    echo "  Installing whisper-cpp..."
    brew install whisper-cpp
  else
    echo "  whisper-cli ✓"
  fi
elif [ "$OS" = "Linux" ]; then
  # Linux — detect package manager
  if command -v apt &>/dev/null; then
    PKG_MGR="apt"
  elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
  elif command -v pacman &>/dev/null; then
    PKG_MGR="pacman"
  else
    PKG_MGR=""
  fi

  if ! command -v sox &>/dev/null; then
    echo "  sox not found."
    if [ "$PKG_MGR" = "apt" ]; then
      echo "  Installing sox..."
      sudo apt install -y sox
    elif [ "$PKG_MGR" = "dnf" ]; then
      echo "  Installing sox..."
      sudo dnf install -y sox
    elif [ "$PKG_MGR" = "pacman" ]; then
      echo "  Installing sox..."
      sudo pacman -S --noconfirm sox
    else
      echo "  ✗ Please install sox manually and re-run."
      exit 1
    fi
  else
    echo "  sox ✓"
  fi

  # Check for PortAudio (needed by PyAudio)
  if [ "$PKG_MGR" = "apt" ]; then
    if ! dpkg -s portaudio19-dev &>/dev/null 2>&1; then
      echo "  Installing portaudio19-dev..."
      sudo apt install -y portaudio19-dev
    fi
    # xclip for pyperclip
    if ! command -v xclip &>/dev/null; then
      echo "  Installing xclip..."
      sudo apt install -y xclip
    fi
  fi

  # whisper-cpp — check for common binary names
  WHISPER_FOUND=false
  for name in whisper-cli whisper-cpp whisper main; do
    if command -v "$name" &>/dev/null; then
      echo "  whisper-cpp ($name) ✓"
      WHISPER_FOUND=true
      break
    fi
  done
  if [ "$WHISPER_FOUND" = "false" ]; then
    echo "  ⚠ whisper-cpp not found on PATH."
    echo "    Build from source: https://github.com/ggml-org/whisper.cpp"
    echo "    After building, ensure the binary is on your PATH."
    echo "    Continuing install — you can add whisper-cpp later."
  fi
else
  echo "✗ Unsupported OS: $OS. Use install.ps1 for Windows."
  exit 1
fi

# Python packages
echo ""
echo "▶ Checking Python packages..."
pip3 install --quiet pynput pyaudio pyperclip 2>/dev/null || \
  pip install --quiet pynput pyaudio pyperclip 2>/dev/null || \
  echo "  ⚠ Could not install Python packages. Run: pip3 install pynput pyaudio pyperclip"

if ! command -v node &>/dev/null; then
  echo "✗ Node.js not found. Install from https://nodejs.org and re-run."
  exit 1
fi

if ! command -v claude &>/dev/null; then
  echo "✗ Claude Code CLI not found. Install from https://claude.ai/code and re-run."
  exit 1
fi

# ── Step 2: Copy server files ─────────────────────────────────────────────────
echo ""
echo "▶ Installing MCP server..."
mkdir -p "$MCP_TARGET/models"
cp "$SCRIPT_DIR/src/index.js" "$MCP_TARGET/index.js"
cp "$SCRIPT_DIR/src/ptt.py"   "$MCP_TARGET/ptt.py"
cp "$SCRIPT_DIR/package.json" "$MCP_TARGET/package.json"
chmod +x "$MCP_TARGET/ptt.py"

echo "  Installing npm dependencies..."
npm install --prefix "$MCP_TARGET" --silent


# ── Step 3: Download whisper model ────────────────────────────────────────────
echo ""
echo "▶ Checking whisper model..."
if [ -f "$MODEL_PATH" ]; then
  echo "  Model already present ✓"
else
  echo "  Downloading ggml-base.en.bin (~142MB)..."
  curl -L --progress-bar -o "$MODEL_PATH" "$MODEL_URL"
  echo "  Model downloaded ✓"
fi

# ── Step 4: Install skill ─────────────────────────────────────────────────────
echo ""
echo "▶ Installing /dictate skill..."
mkdir -p "$SKILL_TARGET"
cp "$SCRIPT_DIR/skills/dictate/SKILL.md" "$SKILL_TARGET/SKILL.md"
echo "  Skill installed ✓"

# ── Step 5: Register MCP server ───────────────────────────────────────────────
echo ""
echo "▶ Registering claude-stt MCP server..."

# Remove existing registration if present (idempotent install)
claude mcp remove claude-stt --scope user 2>/dev/null || true

claude mcp add \
  --transport stdio \
  -s user \
  claude-stt \
  -- node "$MCP_TARGET/index.js"

echo "  MCP server registered ✓"

# ── Done ───────────────────────────────────────────────────────────────────────
PASTE_KEY="Cmd+V"
PTT_KEY="Right Option (⌥)"
if [ "$OS" = "Linux" ]; then
  PASTE_KEY="Ctrl+V"
  PTT_KEY="Right Alt"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Usage — silence-detection mode:"
echo "  1. Grant microphone access to your terminal app if prompted on first use."
echo "  2. In any Claude Code session, type: /dictate"
echo "  3. Speak — recording stops automatically after silence."
echo ""
echo "Usage — PTT (push-to-talk) mode:"
echo "  1. Open a second terminal and run:"
echo "       python3 $MCP_TARGET/ptt.py"
echo "  2. Hold $PTT_KEY to record, release to stop. Repeat as needed."
echo "  3. $PASTE_KEY to paste into Claude Code."
echo "  4. Type 'c' to clear session and start fresh."
echo ""
if [ "$OS" = "Darwin" ]; then
  echo "⚠  PTT requires Terminal to have Accessibility permission:"
  echo "   System Settings > Privacy & Security > Accessibility > enable Terminal"
  echo ""
fi
echo "Need a different model? Edit DEFAULT_MODEL_PATH in ~/.claude/mcp-servers/claude-stt/index.js"
echo "Model options: ggml-tiny.en.bin (75MB), ggml-small.en.bin (466MB)"
echo ""
