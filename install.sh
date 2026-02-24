#!/usr/bin/env bash
set -euo pipefail

# ─── claude-stt installer ────────────────────────────────────────────────────
# Installs the claude-stt MCP server and /dictate skill into Claude Code.
# Requirements: macOS, Homebrew, Node.js ≥ 18, Claude Code CLI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_TARGET="$HOME/.claude/mcp-servers/claude-stt"
SKILL_TARGET="$HOME/.claude/skills/dictate"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
MODEL_PATH="$MCP_TARGET/models/ggml-base.en.bin"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   claude-stt — local STT for Claude  ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Step 1: System dependencies ───────────────────────────────────────────────
echo "▶ Checking system dependencies..."

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

if ! command -v whisper-cpp &>/dev/null; then
  echo "  Installing whisper-cpp..."
  brew install whisper-cpp
else
  echo "  whisper-cpp ✓"
fi

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
cp "$SCRIPT_DIR/package.json" "$MCP_TARGET/package.json"

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
  --scope user \
  -e "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" \
  claude-stt \
  -- node "$MCP_TARGET/index.js"

echo "  MCP server registered ✓"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "✅ Installation complete!"
echo ""
echo "Usage:"
echo "  1. Grant microphone access to your terminal app if prompted on first use."
echo "  2. In any Claude Code session, type: /dictate"
echo "  3. Speak — recording stops automatically after silence."
echo ""
echo "Need a different model? Edit MODEL_PATH in ~/.claude/mcp-servers/claude-stt/index.js"
echo "Model options: ggml-tiny.en.bin (75MB), ggml-small.en.bin (466MB)"
echo ""
