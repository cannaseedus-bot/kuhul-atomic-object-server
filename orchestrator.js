/**
 * K'uhul Model Orchestrator
 *
 * Node.js service that bridges K'uhul XJSON requests to Ollama.
 * Implements the lam.o model runner protocol.
 *
 * Usage:
 *   npm install express axios cors
 *   node orchestrator.js
 *
 * Endpoints:
 *   POST /api/infer     - Run model inference
 *   GET  /api/health    - Health check
 *   GET  /api/models    - List available models
 *   GET  /api/caps      - Runner capabilities
 */

const express = require("express");
const axios = require("axios");
const cors = require("cors");
const crypto = require("crypto");

const path = require("node:path");
const fs = require("node:fs");
const manifest = require("./manifest.json");
const { mountObjectAPI } = require("./lib/object-api.cjs");
const app = express();
// The local API accepts same-origin browser clients.
app.use(express.json({ limit: '2mb' }));
const objectStore = mountObjectAPI(app, manifest, __dirname);

// Configuration
const CONFIG = {
  port: process.env.PORT || 61683,
  ollamaUrl: process.env.OLLAMA_URL || "http://localhost:11434",
  defaultModel: process.env.DEFAULT_MODEL || "llama3",
  timeout: parseInt(process.env.TIMEOUT) || 120000,
  scxq2Version: "SCXQ2-v1"
};

// Runner capabilities
const RUNNER_CAPS = {
  "lam.o": {
    models: ["deepseek-r1", "llama3", "qwen2.5", "janus"],
    modes: ["chat", "reasoning", "analysis", "code"],
    max_tokens: 8192,
    streaming: false,
    protocol: "ollama_http_v1"
  }
};

/**
 * Generate SCXQ2 fingerprint
 */
function generateSCXQ2(request, response) {
  const infer = request["@infer"] || {};
  const completion = response["@completion"] || {};

  const payload = {
    runner: infer["@runner"] || "lam.o",
    model: infer["@model"] || "unknown",
    mode: infer["@mode"] || null,
    params: infer["@params"] || {},
    prompt_shape: {
      length: (infer["@prompt"] || "").length,
      has_context: !!(infer["@context"] && infer["@context"].length)
    },
    metrics: completion["@metrics"] || {},
    tokens: completion["@tokens"] || {},
    timestamp_bucket: Math.floor(Date.now() / 60000)
  };

  const payloadString = JSON.stringify(payload);
  const hash = crypto.createHash("sha256").update(payloadString).digest("hex");

  return `${CONFIG.scxq2Version}:${hash.substring(0, 32)}`;
}

/**
 * Normalize request to XJSON format
 */
function normalizeRequest(body) {
  // Already in XJSON format
  if (body && body["@infer"]) {
    return body;
  }

  body = body || {};
  // Convert from simple format
  return {
    "@infer": {
      "@runner": "lam.o",
      "@model": body.model || CONFIG.defaultModel,
      "@prompt": body.prompt || "",
      "@params": {
        temperature: body.temperature ?? body.options?.temperature ?? 0.7,
        top_p: body.top_p ?? body.options?.top_p ?? 0.9,
        ...body.options
      },
      "@context": body.context || [],
      "@mode": body.mode || "chat"
    }
  };
}

/**
 * Convert XJSON to Ollama request
 */
function toOllamaRequest(xjson) {
  const infer = xjson["@infer"] || {};
  const params = infer["@params"] || {};

  return {
    model: infer["@model"] || CONFIG.defaultModel,
    prompt: infer["@prompt"] || "",
    stream: false,
    options: {
      temperature: params.temperature,
      top_p: params.top_p,
      num_predict: params.max_tokens
    }
  };
}

/**
 * Build XJSON completion response
 */
function buildCompletion(ollamaResponse, xjsonRequest, latencyMs) {
  const infer = xjsonRequest["@infer"] || {};

  return {
    "@completion": {
      "@model": infer["@model"] || ollamaResponse.model || "unknown",
      "@runner": "lam.o",
      "@text": ollamaResponse.response || "",
      "@tokens": {
        input: ollamaResponse.prompt_eval_count || 0,
        output: ollamaResponse.eval_count || 0
      },
      "@metrics": {
        latency_ms: latencyMs,
        backend: "ollama",
        total_duration: ollamaResponse.total_duration
          ? ollamaResponse.total_duration / 1e6
          : 0,
        load_duration: ollamaResponse.load_duration
          ? ollamaResponse.load_duration / 1e6
          : 0,
        eval_duration: ollamaResponse.eval_duration
          ? ollamaResponse.eval_duration / 1e6
          : 0,
        tokens_per_second: ollamaResponse.eval_count && ollamaResponse.eval_duration
          ? ollamaResponse.eval_count / (ollamaResponse.eval_duration / 1e9)
          : 0
      }
    }
  };
}

/**
 * Build XJSON error response
 */
function buildError(message, code = 500) {
  return {
    "@error": {
      "@runner": "lam.o",
      "@message": message,
      "@code": code
    }
  };
}

// ============================================
// API Endpoints
// ============================================

/**
 * POST /api/infer - Run model inference
 *
 * Accepts:
 *   - XJSON format: { "@infer": { "@model": "...", "@prompt": "..." } }
 *   - Simple format: { "model": "...", "prompt": "..." }
 *
 * Returns:
 *   - XJSON completion: { "@completion": { ... } }
 *   - XJSON error: { "@error": { ... } }
 */
app.post("/api/infer", async (req, res) => {
  const startTime = performance.now();

  try {
    // Normalize to XJSON format
    const xjsonRequest = normalizeRequest(req.body);

    // Validate request
    const infer = xjsonRequest["@infer"];
    if (typeof infer["@prompt"] !== "string" || !infer["@prompt"].trim()) {
      return res.status(400).json(buildError("Prompt is required", 400));
    }

    // Convert to Ollama request
    const ollamaRequest = toOllamaRequest(xjsonRequest);

    // Call Ollama
    const ollamaResponse = await axios.post(
      `${CONFIG.ollamaUrl}/api/generate`,
      ollamaRequest,
      { timeout: CONFIG.timeout }
    );

    const endTime = performance.now();
    const latencyMs = endTime - startTime;

    // Build XJSON response
    const xjsonResponse = buildCompletion(ollamaResponse.data, xjsonRequest, latencyMs);

    // Attach SCXQ2 fingerprint
    xjsonResponse["@completion"]["@scxq2"] = generateSCXQ2(xjsonRequest, xjsonResponse);

    // Log inference
    console.log(`[lam.o] Inference: model=${infer["@model"]}, latency=${latencyMs.toFixed(0)}ms, scxq2=${xjsonResponse["@completion"]["@scxq2"].substring(0, 24)}...`);

    res.json(xjsonResponse);

  } catch (error) {
    console.error("[lam.o] Inference error:", error.message);

    const code = error.response?.status || 500;
    const message = error.response?.data?.error || error.message;

    res.status(code).json(buildError(message, code));
  }
});

/**
 * GET /api/health - Health check
 */
app.get("/api/health", async (req, res) => {
  try {
    // Check Ollama connectivity
    const ollamaHealth = await axios.get(`${CONFIG.ollamaUrl}/api/tags`, {
      timeout: 5000
    });

    res.json({
      status: "healthy",
      runner: "lam.o",
      ollama: {
        connected: true,
        models_available: ollamaHealth.data.models?.length || 0
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    res.status(503).json({
      status: "unhealthy",
      runner: "lam.o",
      ollama: {
        connected: false,
        error: error.message
      },
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /api/models - List available models
 */
app.get("/api/models", async (req, res) => {
  try {
    const response = await axios.get(`${CONFIG.ollamaUrl}/api/tags`, {
      timeout: 10000
    });

    const models = (response.data.models || []).map(m => ({
      name: m.name,
      modified_at: m.modified_at,
      size: m.size,
      digest: m.digest?.substring(0, 12)
    }));

    res.json({
      runner: "lam.o",
      models: models,
      count: models.length
    });

  } catch (error) {
    res.status(500).json(buildError("Failed to fetch models: " + error.message));
  }
});

/**
 * GET /api/caps - Runner capabilities
 */
app.get("/api/caps", (req, res) => {
  res.json({
    runner: "lam.o",
    capabilities: RUNNER_CAPS["lam.o"],
    config: {
      ollama_url: CONFIG.ollamaUrl,
      default_model: CONFIG.defaultModel,
      timeout_ms: CONFIG.timeout
    }
  });
});

/**
 * Serve static PWA files
 */
// Expose only declared public assets; database and server sources stay private.
app.use("/api", (req, res) => res.status(404).json({ error: "Unknown API route" }));
app.use((error, req, res, next) => {
  console.error(error.message);
  const status = error.status || 500;
  res.status(status).json({ error: status < 500 ? error.message : "Internal server error" });
});
const publicFiles = new Set(["index.html", "chat.html", "daemon.js", "atomic.css", "styles.css", "manifest.json", "stack-inventory.json",
  "KHANARY-ATOMIC-MASTER-GUIDE.html", "kuhul_atomic_horizontal_vertical_folds_guide.html", "asx-key-grammar.html", "sw.js",
  "lib/frame-projection.js", "micronaut/ui-frames.json", "micronaut/logo.svg",
  "micronaut/xaiml/chat-frame.js", "micronaut/xaiml/chat-frame.compiled.js",
  "micronaut/vendor/react/react.production.min.js", "micronaut/vendor/react/react-dom.production.min.js",
  "micronaut/xaiml/daemon-cli.xaiml", "micronaut/xaiml/model-runtime-frame.json",
  "micronaut/xaiml/greeting-intents.json", "vendor/key-grammar-kit/greeting-bank.key-grammar.jsonl",
  "vendor/key-grammar-kit/data/apps/daemon-bot.asx-app.json", "vendor/key-grammar-kit/data/apps/daemon-bot-knowledge.json",
  "vendor/key-grammar-kit/data/manifest/gml.manifest.json", "vendor/key-grammar-kit/data/manifest/kuhul.manifest.json",
  "vendor/key-grammar-kit/data/manifest/aiml.manifest.json", "vendor/key-grammar-kit/data/manifest/css.manifest.json",
  "capabilities.json", "capabilities.schema.json", "micronaut/docs/css_micronaut_control_system.html", "micronaut/docs/capability-registry.css", "micronaut/docs/capability-console.js", "micronaut/docs/db.css"]);
app.get("*", (req, res, next) => {
  const relative = req.path === "/" ? "index.html" : req.path.slice(1);
  const library = /^lib\/[a-zA-Z0-9._-]+\.(js|json)$/.test(relative);
  const icon = /^icons\/[a-zA-Z0-9._-]+\.(png|svg|ico)$/.test(relative);
  if (!publicFiles.has(relative) && !library && !icon) return res.status(404).send("Not found");
  if (relative === "sw.js") res.set("Cache-Control", "no-cache");
  res.sendFile(path.join(__dirname, relative));
});

/**
 * Fallback to index.html for SPA
 */
app.get("*", (req, res) => {
  res.sendFile(__dirname + "/index.html");
});

// ============================================
// Start Server
// ============================================

if (require.main === module) {
const server = app.listen(CONFIG.port, process.env.HOST || "127.0.0.1", () => {
  console.log(`
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   K'uhul Model Orchestrator (lam.o)                      ║
║   ─────────────────────────────────                      ║
║                                                           ║
║   Port:     ${CONFIG.port}                                        ║
║   Ollama:   ${CONFIG.ollamaUrl}                     ║
║   Model:    ${CONFIG.defaultModel}                                      ║
║                                                           ║
║   Endpoints:                                              ║
║     POST /api/infer   - Run inference                     ║
║     GET  /api/health  - Health check                      ║
║     GET  /api/models  - List models                       ║
║     GET  /api/caps    - Runner capabilities               ║
║                                                           ║
║   Ready for K'uhul XJSON requests!                       ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
  `);
});

process.once("exit", () => objectStore.close());
for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => server.close(() => { objectStore.close(); process.exit(0); }));
}
module.exports = app;
