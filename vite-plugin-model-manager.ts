/**
 * Vite Plugin: Local Model Manager
 * =================================
 * Adds API endpoints to the Vite dev server for managing ComfyUI models:
 *  - GET  /local-api/models           → list installed checkpoints
 *  - POST /local-api/models/download  → start model download
 *  - GET  /local-api/models/downloads → active download progress
 *  - POST /local-api/models/cancel    → cancel a download
 *  - DELETE /local-api/models/:file   → delete a model file
 *  - GET  /local-api/civitai/search   → search CivitAI
 *  - GET  /local-api/civitai/model/:id → get model details
 *  - GET  /local-api/comfyui/status   → check ComfyUI + models dir status
 *
 * Dev-only — never shipped to production.
 */

import type { Plugin, ViteDevServer } from "vite";
import fs from "node:fs";
import path from "node:path";
import https from "node:https";
import http from "node:http";
import { pipeline } from "node:stream/promises";
import { createWriteStream, existsSync, statSync, readdirSync, unlinkSync } from "node:fs";
import { spawn, type ChildProcess } from "node:child_process";

// ─── Types ───────────────────────────────────────────────────────────────────

interface DownloadTask {
  id: string;
  filename: string;
  url: string;
  totalBytes: number;
  downloadedBytes: number;
  status: "downloading" | "complete" | "error" | "cancelled";
  error?: string;
  startedAt: number;
  abortController?: AbortController;
}

// ─── State ───────────────────────────────────────────────────────────────────

const activeDownloads = new Map<string, DownloadTask>();
let downloadIdCounter = 0;
let comfyProcess: ChildProcess | null = null;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function findComfyUIPath(): string | null {
  // Check env var first
  const envPath = process.env.COMFYUI_PATH;
  if (envPath && existsSync(envPath)) return envPath;

  // Check common locations relative to this project
  const candidates = [
    path.resolve(process.cwd(), "../ComfyUI"),
    path.resolve(process.cwd(), "../../ComfyUI"),
    path.resolve(process.env.USERPROFILE || "", "ComfyUI"),
    path.resolve(process.env.USERPROFILE || "", "Desktop/ComfyUI"),
    path.resolve(process.env.USERPROFILE || "", "Documents/ComfyUI"),
    "C:/ComfyUI",
    "D:/ComfyUI",
  ];

  for (const candidate of candidates) {
    if (existsSync(path.join(candidate, "main.py"))) {
      return candidate;
    }
  }
  return null;
}

function getCheckpointsDir(): string | null {
  const comfyPath = findComfyUIPath();
  if (!comfyPath) return null;
  const dir = path.join(comfyPath, "models", "checkpoints");
  if (!existsSync(dir)) {
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch {
      return null;
    }
  }
  return dir;
}

function listCheckpoints(): Array<{
  filename: string;
  sizeBytes: number;
  sizeFormatted: string;
  modifiedAt: string;
}> {
  const dir = getCheckpointsDir();
  if (!dir) return [];

  try {
    return readdirSync(dir)
      .filter((f) => f.endsWith(".safetensors") || f.endsWith(".ckpt") || f.endsWith(".pt"))
      .map((f) => {
        const stat = statSync(path.join(dir, f));
        return {
          filename: f,
          sizeBytes: stat.size,
          sizeFormatted: formatBytes(stat.size),
          modifiedAt: stat.mtime.toISOString(),
        };
      })
      .sort((a, b) => b.modifiedAt.localeCompare(a.modifiedAt));
  } catch {
    return [];
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + units[i];
}

function downloadFile(url: string, destPath: string, taskId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const task = activeDownloads.get(taskId);
    if (!task) return reject(new Error("Task not found"));

    const protocol = url.startsWith("https") ? https : http;
    const ac = new AbortController();
    task.abortController = ac;

    const request = protocol.get(url, { signal: ac.signal as any }, (response) => {
      // Handle redirects
      if (response.statusCode && response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        downloadFile(response.headers.location, destPath, taskId).then(resolve).catch(reject);
        return;
      }

      if (response.statusCode !== 200) {
        reject(new Error(`Download failed: HTTP ${response.statusCode}`));
        return;
      }

      const totalBytes = parseInt(response.headers["content-length"] || "0", 10);
      task.totalBytes = totalBytes;
      let downloaded = 0;

      const fileStream = createWriteStream(destPath);
      response.on("data", (chunk: Buffer) => {
        downloaded += chunk.length;
        task.downloadedBytes = downloaded;
      });

      response.pipe(fileStream);

      fileStream.on("finish", () => {
        task.status = "complete";
        task.downloadedBytes = task.totalBytes || downloaded;
        resolve();
      });

      fileStream.on("error", (err) => {
        task.status = "error";
        task.error = err.message;
        // Cleanup partial file
        try { unlinkSync(destPath); } catch {}
        reject(err);
      });
    });

    request.on("error", (err: any) => {
      if (err.name === "AbortError" || task.status === "cancelled") {
        // Cleanup partial file
        try { unlinkSync(destPath); } catch {}
        resolve();
        return;
      }
      task.status = "error";
      task.error = err.message;
      try { unlinkSync(destPath); } catch {}
      reject(err);
    });
  });
}

async function searchCivitAI(query: string, limit = 20): Promise<any> {
  const url = `https://civitai.com/api/v1/models?query=${encodeURIComponent(query)}&limit=${limit}&types=Checkpoint&sort=Highest%20Rated`;

  return new Promise((resolve, reject) => {
    https.get(url, { headers: { "User-Agent": "GooniGooni/1.0" } }, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try {
          resolve(JSON.parse(data));
        } catch {
          reject(new Error("Failed to parse CivitAI response"));
        }
      });
    }).on("error", reject);
  });
}

async function getCivitAIModel(modelId: string): Promise<any> {
  const url = `https://civitai.com/api/v1/models/${modelId}`;

  return new Promise((resolve, reject) => {
    https.get(url, { headers: { "User-Agent": "GooniGooni/1.0" } }, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try {
          resolve(JSON.parse(data));
        } catch {
          reject(new Error("Failed to parse CivitAI response"));
        }
      });
    }).on("error", reject);
  });
}

// ─── Helpers for request body parsing ────────────────────────────────────────

function parseBody(req: http.IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch {
        reject(new Error("Invalid JSON"));
      }
    });
  });
}

function sendJson(res: http.ServerResponse, status: number, body: any) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

// ─── ComfyUI running check ──────────────────────────────────────────────────

async function isComfyUIRunning(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get("http://127.0.0.1:8188/system_stats", (res) => {
      resolve(res.statusCode === 200);
      res.resume(); // Drain response
    });
    req.on("error", () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

// ─── Find python executable ─────────────────────────────────────────────────

function findPython(comfyPath: string): string {
  // Check for venv inside ComfyUI directory
  const venvPaths = [
    path.join(comfyPath, "venv", "Scripts", "python.exe"),       // Windows venv
    path.join(comfyPath, "venv", "bin", "python"),               // Unix venv
    path.join(comfyPath, ".venv", "Scripts", "python.exe"),      // Windows .venv
    path.join(comfyPath, ".venv", "bin", "python"),              // Unix .venv
    path.join(comfyPath, "python_embeded", "python.exe"),        // ComfyUI portable (Windows)
  ];

  for (const p of venvPaths) {
    if (existsSync(p)) return p;
  }

  // Fall back to system python
  return process.platform === "win32" ? "python" : "python3";
}

// ─── Plugin ──────────────────────────────────────────────────────────────────

export default function modelManagerPlugin(): Plugin {
  return {
    name: "vite-plugin-model-manager",
    apply: "serve", // Dev only

    configureServer(server: ViteDevServer) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url || "";

        if (!url.startsWith("/local-api/")) {
          return next();
        }

        // CORS for dev
        res.setHeader("Access-Control-Allow-Origin", "*");
        res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
        res.setHeader("Access-Control-Allow-Headers", "Content-Type");
        if (req.method === "OPTIONS") {
          res.writeHead(204);
          res.end();
          return;
        }

        try {
          // ── ComfyUI status ─────────────────────────────────────────────
          if (url === "/local-api/comfyui/status" && req.method === "GET") {
            const comfyPath = findComfyUIPath();
            const checkpointsDir = getCheckpointsDir();
            const running = await isComfyUIRunning();
            return sendJson(res, 200, {
              comfyuiFound: !!comfyPath,
              comfyuiPath: comfyPath,
              checkpointsDir,
              modelsCount: listCheckpoints().length,
              comfyuiRunning: running,
            });
          }

          // ── Launch ComfyUI ─────────────────────────────────────────────
          if (url === "/local-api/comfyui/launch" && req.method === "POST") {
            const running = await isComfyUIRunning();
            if (running) {
              return sendJson(res, 200, { status: "already_running" });
            }

            const comfyPath = findComfyUIPath();
            if (!comfyPath) {
              return sendJson(res, 500, {
                error: "ComfyUI не найден. Укажите COMFYUI_PATH в .env.local",
              });
            }

            try {
              const mainPy = path.join(comfyPath, "main.py");
              if (!existsSync(mainPy)) {
                return sendJson(res, 500, {
                  error: `Не найден файл main.py в ${comfyPath}`,
                });
              }

              // Detect python executable
              const pythonCmd = findPython(comfyPath);

              comfyProcess = spawn(pythonCmd, ["main.py", "--listen", "127.0.0.1", "--port", "8188"], {
                cwd: comfyPath,
                stdio: "pipe",
                detached: false,
                shell: process.platform === "win32",
              });

              comfyProcess.on("exit", () => {
                comfyProcess = null;
              });

              return sendJson(res, 200, {
                status: "launched",
                pid: comfyProcess.pid,
                command: `${pythonCmd} main.py --listen 127.0.0.1 --port 8188`,
              });
            } catch (err: any) {
              return sendJson(res, 500, { error: err.message });
            }
          }

          // ── List models ────────────────────────────────────────────────
          if (url === "/local-api/models" && req.method === "GET") {
            const models = listCheckpoints();
            const comfyPath = findComfyUIPath();
            return sendJson(res, 200, {
              models,
              checkpointsDir: getCheckpointsDir(),
              comfyuiPath: comfyPath,
            });
          }

          // ── Download model ─────────────────────────────────────────────
          if (url === "/local-api/models/download" && req.method === "POST") {
            const body = await parseBody(req);
            const { url: downloadUrl, filename } = body;

            if (!downloadUrl || !filename) {
              return sendJson(res, 400, { error: "url and filename required" });
            }

            const dir = getCheckpointsDir();
            if (!dir) {
              return sendJson(res, 500, {
                error: "ComfyUI not found. Set COMFYUI_PATH environment variable.",
              });
            }

            // Sanitize filename
            const safeFilename = filename.replace(/[^a-zA-Z0-9_\-\.]/g, "_");
            const destPath = path.join(dir, safeFilename);

            // Check if already exists
            if (existsSync(destPath)) {
              return sendJson(res, 409, { error: "File already exists", filename: safeFilename });
            }

            const id = String(++downloadIdCounter);
            const task: DownloadTask = {
              id,
              filename: safeFilename,
              url: downloadUrl,
              totalBytes: 0,
              downloadedBytes: 0,
              status: "downloading",
              startedAt: Date.now(),
            };
            activeDownloads.set(id, task);

            // Start download in background
            downloadFile(downloadUrl, destPath, id).catch((err) => {
              const t = activeDownloads.get(id);
              if (t && t.status !== "cancelled") {
                t.status = "error";
                t.error = err.message;
              }
            });

            return sendJson(res, 200, { id, filename: safeFilename, status: "downloading" });
          }

          // ── Download progress ──────────────────────────────────────────
          if (url === "/local-api/models/downloads" && req.method === "GET") {
            const downloads: any[] = [];
            for (const [, task] of activeDownloads) {
              downloads.push({
                id: task.id,
                filename: task.filename,
                totalBytes: task.totalBytes,
                downloadedBytes: task.downloadedBytes,
                status: task.status,
                error: task.error,
                percentage: task.totalBytes > 0
                  ? Math.round((task.downloadedBytes / task.totalBytes) * 100)
                  : 0,
                elapsed: Date.now() - task.startedAt,
              });
            }
            // Clean up completed/error tasks older than 30s
            for (const [id, task] of activeDownloads) {
              if (
                (task.status === "complete" || task.status === "error" || task.status === "cancelled") &&
                Date.now() - task.startedAt > 30000
              ) {
                activeDownloads.delete(id);
              }
            }
            return sendJson(res, 200, { downloads });
          }

          // ── Cancel download ────────────────────────────────────────────
          if (url === "/local-api/models/cancel" && req.method === "POST") {
            const body = await parseBody(req);
            const task = activeDownloads.get(body.id);
            if (!task) {
              return sendJson(res, 404, { error: "Download not found" });
            }
            task.status = "cancelled";
            task.abortController?.abort();
            return sendJson(res, 200, { status: "cancelled" });
          }

          // ── Delete model ───────────────────────────────────────────────
          if (url.startsWith("/local-api/models/") && req.method === "DELETE") {
            const filename = decodeURIComponent(url.slice("/local-api/models/".length));
            const dir = getCheckpointsDir();
            if (!dir) {
              return sendJson(res, 500, { error: "ComfyUI not found" });
            }
            const filePath = path.join(dir, filename);
            if (!existsSync(filePath)) {
              return sendJson(res, 404, { error: "File not found" });
            }
            unlinkSync(filePath);
            return sendJson(res, 200, { deleted: filename });
          }

          // ── CivitAI search ─────────────────────────────────────────────
          if (url.startsWith("/local-api/civitai/search") && req.method === "GET") {
            const params = new URL(url, "http://localhost").searchParams;
            const query = params.get("q") || "";
            if (!query) {
              return sendJson(res, 400, { error: "query parameter 'q' required" });
            }
            const results = await searchCivitAI(query);
            return sendJson(res, 200, results);
          }

          // ── CivitAI model details ──────────────────────────────────────
          if (url.startsWith("/local-api/civitai/model/") && req.method === "GET") {
            const modelId = url.slice("/local-api/civitai/model/".length).split("?")[0];
            const data = await getCivitAIModel(modelId);
            return sendJson(res, 200, data);
          }

          // Not our route
          next();
        } catch (err: any) {
          sendJson(res, 500, { error: err.message || "Internal server error" });
        }
      });
    },
  };
}
