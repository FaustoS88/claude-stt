# ─── claude-stt installer (Windows) ──────────────────────────────────────────
# Installs the claude-stt MCP server and /dictate skill into Claude Code.
# Requirements: Node.js >= 18, Python 3, Claude Code CLI
# Run: .\install.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$McpTarget = Join-Path $env:USERPROFILE ".claude\mcp-servers\claude-stt"
$SkillTarget = Join-Path $env:USERPROFILE ".claude\skills\dictate"
$ModelUrl = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
$ModelPath = Join-Path $McpTarget "models\ggml-base.en.bin"

Write-Host ""
Write-Host "+==============================================+"
Write-Host "|   claude-stt -- local STT for Claude Code    |"
Write-Host "+==============================================+"
Write-Host ""

# ── Step 1: Check system dependencies ────────────────────────────────────────
Write-Host "> Checking system dependencies..."

# sox
if (Get-Command sox -ErrorAction SilentlyContinue) {
    Write-Host "  sox OK"
} else {
    Write-Host "  sox not found."
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Host "  Installing sox via Chocolatey..."
        choco install sox -y
    } elseif (Get-Command scoop -ErrorAction SilentlyContinue) {
        Write-Host "  Installing sox via Scoop..."
        scoop install sox
    } else {
        Write-Host "  WARNING: sox not found. Install manually:"
        Write-Host "    choco install sox  OR  download from https://sox.sourceforge.net/"
        Write-Host "  Continuing install -- you can add sox later."
    }
}

# whisper-cpp
$whisperFound = $false
foreach ($name in @("whisper-cli", "whisper-cpp", "whisper", "main")) {
    if (Get-Command $name -ErrorAction SilentlyContinue) {
        Write-Host "  whisper-cpp ($name) OK"
        $whisperFound = $true
        break
    }
}
if (-not $whisperFound) {
    Write-Host "  WARNING: whisper-cpp not found on PATH."
    Write-Host "    Download from: https://github.com/ggml-org/whisper.cpp/releases"
    Write-Host "    Add the binary directory to your PATH."
    Write-Host "  Continuing install -- you can add whisper-cpp later."
}

# Node.js
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Node.js not found. Install from https://nodejs.org and re-run."
    exit 1
}

# Claude Code CLI
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Claude Code CLI not found. Install from https://claude.ai/code and re-run."
    exit 1
}

# Python packages
Write-Host ""
Write-Host "> Installing Python packages..."
try {
    pip install --quiet pynput pyaudio pyperclip 2>$null
    Write-Host "  Python packages OK"
} catch {
    Write-Host "  WARNING: Could not install Python packages. Run: pip install pynput pyaudio pyperclip"
}

# ── Step 2: Copy server files ────────────────────────────────────────────────
Write-Host ""
Write-Host "> Installing MCP server..."
New-Item -ItemType Directory -Path (Join-Path $McpTarget "models") -Force | Out-Null
Copy-Item (Join-Path $ScriptDir "src\index.js") (Join-Path $McpTarget "index.js") -Force
Copy-Item (Join-Path $ScriptDir "src\ptt.py") (Join-Path $McpTarget "ptt.py") -Force
Copy-Item (Join-Path $ScriptDir "package.json") (Join-Path $McpTarget "package.json") -Force

Write-Host "  Installing npm dependencies..."
npm install --prefix $McpTarget --silent

# ── Step 3: Download whisper model ───────────────────────────────────────────
Write-Host ""
Write-Host "> Checking whisper model..."
if (Test-Path $ModelPath) {
    Write-Host "  Model already present OK"
} else {
    Write-Host "  Downloading ggml-base.en.bin (~142MB)..."
    Invoke-WebRequest -Uri $ModelUrl -OutFile $ModelPath
    Write-Host "  Model downloaded OK"
}

# ── Step 4: Install skill ───────────────────────────────────────────────────
Write-Host ""
Write-Host "> Installing /dictate skill..."
New-Item -ItemType Directory -Path $SkillTarget -Force | Out-Null
Copy-Item (Join-Path $ScriptDir "skills\dictate\SKILL.md") (Join-Path $SkillTarget "SKILL.md") -Force
Write-Host "  Skill installed OK"

# ── Step 5: Register MCP server ─────────────────────────────────────────────
Write-Host ""
Write-Host "> Registering claude-stt MCP server..."
claude mcp remove claude-stt --scope user 2>$null
claude mcp add --transport stdio -s user claude-stt -- node (Join-Path $McpTarget "index.js")
Write-Host "  MCP server registered OK"

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Installation complete!"
Write-Host ""
Write-Host "Usage -- silence-detection mode:"
Write-Host "  1. In any Claude Code session, type: /dictate"
Write-Host "  2. Speak -- recording stops automatically after silence."
Write-Host ""
Write-Host "Usage -- PTT (push-to-talk) mode:"
Write-Host "  1. Open a second terminal and run:"
Write-Host "       python $McpTarget\ptt.py"
Write-Host "  2. Hold Right Alt to record, release to stop. Repeat as needed."
Write-Host "  3. Ctrl+V to paste into Claude Code."
Write-Host "  4. Type 'c' to clear session and start fresh."
Write-Host ""
