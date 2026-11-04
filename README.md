<img src="12-node-brain.svg" />

# K'uhul Model Runner PWA (lam.o)

Progressive Web App for K'uhul Model Runner with Ollama integration and XJSON contract.

## Architecture

This PWA implements the K'uhul lam.o model runner specification:

```
Sek model_pipeline -> route -> infer -> compress -> log
```

### Components

| File | Purpose |
|------|---------|
| `index.html` | Symbolic DOM with K'uhul bindings |
| `sw.js` | Service Worker with XJSON handling |
| `manifest.json` | PWA manifest with K'uhul lam.o config |
| `orchestrator.js` | Node.js XJSON bridge to Ollama |
| `lib/scxq2.js` | SCXQ2 fingerprint generator |
| `lib/kuhul-xjson.js` | XJSON schema library |
| `lib/kuhul-client.js` | K'uhul client API |

## Quick Start

### 1. Start Ollama

```bash
ollama serve
ollama pull llama3
```

### 2. Start Orchestrator

```bash
cd pwa
npm install
npm start
```

### 3. Open PWA

Navigate to `http://localhost:61683` in your browser.

## XJSON Contract

### Request Format

```json
{
  "@infer": {
    "@runner": "lam.o",
    "@model": "deepseek-r1",
    "@prompt": "Explain symbolic compression.",
    "@params": {
      "temperature": 0.7,
      "top_p": 0.9
    },
    "@mode": "chat"
  }
}
```

### Response Format

```json
{
  "@completion": {
    "@model": "deepseek-r1",
    "@runner": "lam.o",
    "@text": "Symbolic compression is...",
    "@tokens": {
      "input": 42,
      "output": 128
    },
    "@metrics": {
      "latency_ms": 182,
      "backend": "ollama"
    },
    "@scxq2": "SCXQ2-v1:abc123..."
  }
}
```

## K'uhul Pack Definition

```kuhul
Pack pack_lam_o {
  id: "pack_lam_o",
  name: "Ollama Model Runner Pack",
  role: "model_runner_backend",
  fold: "AI",
  functions: [
    "lam.o.describe",
    "lam.o.infer",
    "lam.o.health"
  ]
}
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/infer` | POST | Run model inference |
| `/api/health` | GET | Health check |
| `/api/models` | GET | List available models |
| `/api/caps` | GET | Runner capabilities |

## SCXQ2 Fingerprinting

Every inference generates an SCXQ2 fingerprint:

```javascript
const scxq2 = await SCXQ2.fromInference(request, response);
// Returns: "SCXQ2-v1:a1b2c3d4..."
```

## Symbolic DOM

The UI uses K'uhul symbolic DOM with data attributes:

```html
<div data-kuhul-glyph="C"
     data-kuhul-semantic="MR,C1"
     data-kuhul-pop="run_inference"
     data-scxq2="">
</div>
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 61683 | Orchestrator port |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `DEFAULT_MODEL` | `llama3` | Default model |
| `TIMEOUT` | 120000 | Request timeout (ms) |

## PWA Features

- Offline support via Service Worker
- Install to home screen
- XJSON request caching
- Background sync
- Push notifications (future)

## License

MIT
