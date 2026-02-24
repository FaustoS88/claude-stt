import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { spawn } from "node:child_process";
import { unlink, mkdtemp, access, rmdir, readFile } from "node:fs/promises";
import { tmpdir, homedir, platform } from "node:os";
import { join, delimiter } from "node:path";
import { constants } from "node:fs";
import { execSync } from "node:child_process";

// ─── Constants ───────────────────────────────────────────────────────────────

const SESSION_FILE = join(homedir(), ".claude", "mcp-servers", "claude-stt", "session.txt");

const DEFAULT_MODEL_PATH = join(
  homedir(),
  ".claude",
  "mcp-servers",
  "claude-stt",
  "models",
  "ggml-base.en.bin"
);
const DEFAULT_MAX_DURATION = 30;    // seconds
const DEFAULT_SILENCE_DURATION = 3; // seconds
const SILENCE_THRESHOLD = "0.1%";   // sox amplitude threshold for silence detection

const IS_WIN = platform() === "win32";
const IS_MAC = platform() === "darwin";

// ─── MCP Server ──────────────────────────────────────────────────────────────

const server = new McpServer({
  name: "claude-stt",
  version: "1.1.0",
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

// Extend PATH with common install locations (macOS Homebrew, Linux local bin)
function extendPath() {
  const extras = IS_MAC
    ? ["/opt/homebrew/bin", "/usr/local/bin"]
    : IS_WIN
    ? []
    : ["/usr/local/bin", join(homedir(), ".local", "bin")];
  const current = process.env.PATH || "";
  for (const d of extras) {
    if (!current.includes(d)) {
      process.env.PATH = d + delimiter + process.env.PATH;
    }
  }
}

// Cross-platform binary resolution using `which` (Unix) or `where` (Windows)
async function resolveBinary(name) {
  return new Promise((resolve) => {
    const cmd = IS_WIN ? "where" : "which";
    const proc = spawn(cmd, [name], { env: process.env });
    let out = "";
    proc.stdout.on("data", (d) => (out += d.toString()));
    proc.on("close", (code) => resolve(code === 0 ? out.trim().split(/\r?\n/)[0] : null));
    proc.on("error", () => resolve(null));
  });
}

// Try multiple candidate names for a binary
async function resolveAnyBinary(names) {
  for (const name of names) {
    const path = await resolveBinary(name);
    if (path) return path;
  }
  return null;
}

function soxInstallHint() {
  if (IS_MAC) return "brew install sox";
  if (IS_WIN) return "choco install sox  OR  download from https://sox.sourceforge.net/";
  return "sudo apt install sox  OR  your distro's package manager";
}

function whisperInstallHint() {
  if (IS_MAC) return "brew install whisper-cpp";
  if (IS_WIN) return "Download from: https://github.com/ggml-org/whisper.cpp/releases";
  return "Build from source: https://github.com/ggml-org/whisper.cpp";
}

// Sox recording binary is `rec` on macOS/Linux, `sox` with `-d` flag on Windows
function recordAudio(recBin, outputPath, { maxDuration, silenceDuration }) {
  return new Promise((resolve, reject) => {
    let args;
    if (IS_WIN) {
      // On Windows, sox uses `-d` (default device) instead of the `rec` alias
      args = [
        "-d",
        "-r", "16000", "-c", "1", "-b", "16",
        outputPath,
        "silence",
        "1", "0.1", SILENCE_THRESHOLD,
        "1", String(silenceDuration), SILENCE_THRESHOLD,
        "trim", "0", String(maxDuration),
      ];
    } else {
      args = [
        "-r", "16000", "-c", "1", "-b", "16",
        outputPath,
        "silence",
        "1", "0.1", SILENCE_THRESHOLD,
        "1", String(silenceDuration), SILENCE_THRESHOLD,
        "trim", "0", String(maxDuration),
      ];
    }

    const proc = spawn(recBin, args, { stdio: ["ignore", "ignore", "pipe"] });

    let stderr = "";
    proc.stderr.on("data", (d) => (stderr += d.toString()));

    const timeout = setTimeout(() => {
      proc.kill("SIGTERM");
      reject(new Error(`Recording timed out after ${maxDuration + 5}s`));
    }, (maxDuration + 5) * 1000);

    proc.on("close", (code) => {
      clearTimeout(timeout);
      if (code === 0) resolve();
      else reject(new Error(`rec exited with code ${code}: ${stderr.trim()}`));
    });

    proc.on("error", (err) => {
      clearTimeout(timeout);
      reject(new Error(
        `Failed to start recording (${recBin}): ${err.message}. ` +
        `Is sox installed? ${soxInstallHint()}`
      ));
    });
  });
}

function transcribeAudio(whisperBin, wavPath, modelPath) {
  return new Promise((resolve, reject) => {
    const args = [
      "-m", modelPath,
      "-f", wavPath,
      "--no-timestamps",
      "-l", "en",
    ];

    const proc = spawn(whisperBin, args, { stdio: ["ignore", "pipe", "pipe"] });

    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.stderr.on("data", (d) => (stderr += d.toString()));

    const timeout = setTimeout(() => {
      proc.kill("SIGTERM");
      reject(new Error("Transcription timed out after 60s"));
    }, 60_000);

    proc.on("close", (code) => {
      clearTimeout(timeout);
      if (code === 0) {
        // Filter out whisper hallucination tokens (emitted on silence/noise)
        const WHISPER_ARTIFACTS = /^\[.*\]$|^\(.*\)$/;
        const text = stdout
          .split("\n")
          .map((l) => l.trim())
          .filter((l) => l.length > 0 && !WHISPER_ARTIFACTS.test(l))
          .join(" ")
          .trim();
        resolve(text);
      } else {
        reject(new Error(`whisper-cpp exited with code ${code}: ${stderr.trim()}`));
      }
    });

    proc.on("error", (err) => {
      reject(new Error(
        `Failed to start whisper-cli (${whisperBin}): ${err.message}. ` +
        `Is it installed? ${whisperInstallHint()}`
      ));
    });
  });
}

function errorResult(message) {
  return { content: [{ type: "text", text: `ERROR: ${message}` }], isError: true };
}

// ─── Tool: dictate ───────────────────────────────────────────────────────────

server.registerTool(
  "dictate",
  {
    title: "Dictate",
    description:
      "Record speech from the microphone and transcribe it to text using local whisper-cpp. " +
      "Recording starts immediately and auto-stops after a silence period. " +
      "Fully local — no audio data leaves the device.",
    inputSchema: {
      max_duration: z
        .number()
        .min(5)
        .max(120)
        .default(DEFAULT_MAX_DURATION)
        .describe("Maximum recording length in seconds (default: 30)"),
      silence_duration: z
        .number()
        .min(1)
        .max(10)
        .default(DEFAULT_SILENCE_DURATION)
        .describe("Seconds of silence that triggers auto-stop (default: 2)"),
      model_path: z
        .string()
        .default(DEFAULT_MODEL_PATH)
        .describe("Path to a whisper-cpp GGML model file"),
    },
  },
  async ({ max_duration, silence_duration, model_path }) => {
    extendPath();

    // On Windows, sox is both the recorder and player; on Unix, `rec` is the recording alias
    const recCandidates = IS_WIN ? ["sox"] : ["rec"];
    const recBin = await resolveAnyBinary(recCandidates);
    if (!recBin) {
      return errorResult(`'${recCandidates[0]}' (sox) not found. Install with: ${soxInstallHint()}`);
    }
    const whisperBin = await resolveAnyBinary(["whisper-cli", "whisper-cpp", "whisper", "main"]);
    if (!whisperBin) {
      return errorResult(`whisper-cpp not found. Install with: ${whisperInstallHint()}`);
    }
    try {
      await access(model_path, constants.R_OK);
    } catch {
      return errorResult(
        `Model not found at ${model_path}.\n` +
        `Download with:\n` +
        `  mkdir -p "$(dirname "${model_path}")"\n` +
        `  curl -L -o "${model_path}" \\\n` +
        `    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"`
      );
    }

    // Create temp workspace
    let tempDir, wavPath;
    try {
      tempDir = await mkdtemp(join(tmpdir(), "claude-stt-"));
      wavPath = join(tempDir, "recording.wav");
    } catch (err) {
      return errorResult(`Could not create temp directory: ${err.message}`);
    }

    try {
      console.error(`[claude-stt] Recording (max ${max_duration}s, silence stop: ${silence_duration}s)...`);
      await recordAudio(recBin, wavPath, { maxDuration: max_duration, silenceDuration: silence_duration });
      console.error("[claude-stt] Transcribing...");

      const transcript = await transcribeAudio(whisperBin, wavPath, model_path);
      console.error(`[claude-stt] Done — ${transcript.length} chars`);

      return {
        content: [{ type: "text", text: transcript || "(no speech detected)" }],
      };
    } catch (err) {
      return errorResult(err.message);
    } finally {
      try { await unlink(wavPath); } catch { /* ignore */ }
      try { await rmdir(tempDir); } catch { /* ignore */ }
    }
  }
);

// ─── Tool: get_session ───────────────────────────────────────────────────────

server.registerTool(
  "get_session",
  {
    title: "Get PTT Session",
    description:
      "Read the accumulated push-to-talk dictation session recorded by the PTT daemon (ptt.py). " +
      "Returns all text spoken since the last clear. By default clears the session after reading.",
    inputSchema: {
      clear: z
        .boolean()
        .default(true)
        .describe("Clear the session after reading (default: true)"),
    },
  },
  async ({ clear }) => {
    let text;
    try {
      text = (await readFile(SESSION_FILE, "utf8")).trim();
    } catch (err) {
      if (err.code === "ENOENT") {
        return { content: [{ type: "text", text: "Session is empty." }] };
      }
      return errorResult(`Could not read session file: ${err.message}`);
    }

    if (!text) {
      return { content: [{ type: "text", text: "Session is empty." }] };
    }

    if (clear) {
      try {
        await unlink(SESSION_FILE);
      } catch { /* ignore — file may have already been removed */ }
    }

    return { content: [{ type: "text", text }] };
  }
);

// ─── Tool: clear_session ─────────────────────────────────────────────────────

server.registerTool(
  "clear_session",
  {
    title: "Clear PTT Session",
    description: "Delete the accumulated push-to-talk dictation session (session.txt). Use this to reset after reading.",
    inputSchema: {},
  },
  async () => {
    try {
      await unlink(SESSION_FILE);
      return { content: [{ type: "text", text: "Session cleared." }] };
    } catch (err) {
      if (err.code === "ENOENT") {
        return { content: [{ type: "text", text: "Session was already empty." }] };
      }
      return errorResult(`Could not clear session: ${err.message}`);
    }
  }
);

// ─── Start ───────────────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[claude-stt] MCP server running");
}

main().catch((err) => {
  console.error("[claude-stt] Fatal:", err);
  process.exit(1);
});
