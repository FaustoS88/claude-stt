import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { spawn } from "node:child_process";
import { unlink, mkdtemp, access, rmdir } from "node:fs/promises";
import { tmpdir, homedir } from "node:os";
import { join } from "node:path";
import { constants } from "node:fs";

// ─── Constants ───────────────────────────────────────────────────────────────

const DEFAULT_MODEL_PATH = join(
  homedir(),
  ".claude",
  "mcp-servers",
  "claude-stt",
  "models",
  "ggml-base.en.bin"
);
const DEFAULT_MAX_DURATION = 30;    // seconds
const DEFAULT_SILENCE_DURATION = 2; // seconds
const SILENCE_THRESHOLD = "1.0%";   // sox amplitude threshold for silence detection


// ─── MCP Server ──────────────────────────────────────────────────────────────

const server = new McpServer({
  name: "claude-stt",
  version: "1.0.0",
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

// Resolve binary path, searching standard Homebrew locations in addition to PATH
// This ensures the server works even when Claude Code spawns it with a minimal PATH
const SEARCH_PATHS = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"];

async function resolveBinary(name) {
  // First try `which` with the extended search paths
  return new Promise((resolve) => {
    const env = { ...process.env, PATH: SEARCH_PATHS.join(":") };
    const proc = spawn("which", [name], { env });
    let out = "";
    proc.stdout.on("data", (d) => (out += d.toString()));
    proc.on("close", (code) => resolve(code === 0 ? out.trim() : null));
  });
}

function recordAudio(recBin, outputPath, { maxDuration, silenceDuration }) {
  return new Promise((resolve, reject) => {
    // rec is the sox recording alias: records from the default macOS audio device
    // Audio format: 16kHz mono 16-bit — exactly what whisper-cpp requires
    // silence effect:
    //   1 0.1 <threshold>              — skip leading silence (start only after sound detected)
    //   1 <silenceDuration> <threshold> — auto-stop after N seconds below threshold
    // trim 0 <maxDuration>             — hard cap on total recording length
    const args = [
      "-r", "16000",
      "-c", "1",
      "-b", "16",
      outputPath,
      "silence",
      "1", "0.1", SILENCE_THRESHOLD,
      "1", String(silenceDuration), SILENCE_THRESHOLD,
      "trim", "0", String(maxDuration),
    ];

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
      reject(new Error(`Failed to start rec (${recBin}): ${err.message}. Is sox installed? Run: brew install sox`));
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
        const text = stdout
          .split("\n")
          .map((l) => l.trim())
          .filter((l) => l.length > 0)
          .join(" ")
          .trim();
        resolve(text);
      } else {
        reject(new Error(`whisper-cpp exited with code ${code}: ${stderr.trim()}`));
      }
    });

    proc.on("error", (err) => {
      reject(new Error(
        `Failed to start whisper-cli (${whisperBin}): ${err.message}. Is it installed? Run: brew install whisper-cpp`
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
      "Record speech from the macOS microphone and transcribe it to text using local whisper-cpp. " +
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
    // Preflight checks — resolve full binary paths to avoid PATH issues
    const recBin = await resolveBinary("rec");
    if (!recBin) {
      return errorResult("'rec' (sox) not found. Install with: brew install sox");
    }
    const whisperBin = await resolveBinary("whisper-cli");
    if (!whisperBin) {
      return errorResult("'whisper-cli' not found. Install with: brew install whisper-cpp");
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
