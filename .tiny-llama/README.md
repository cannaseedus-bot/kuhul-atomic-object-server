# tiny-llama.exe

Minimal OpenAI-compatible inference server. Loads a single GGUF model and exposes two routes. No streaming. Single-threaded inference with a generation mutex; one request runs at a time.

## Requirements

- Windows x64
- Visual C++ Redistributable 2022 (MSVC `/MD` runtime)
- A GGUF model file

## Usage

```
tiny-llama.exe --model <path\to\model.gguf> [options]
```

| Flag | Default | Description |
|---|---|---|
| `--model <path>` | **required** | Path to the GGUF model file |
| `--port <n>` | `8080` | Listen port |
| `--host <s>` | `0.0.0.0` | Bind address |
| `--threads <n>` | `4` | Generation threads |
| `--ctx-size <n>` | `4096` | Context window (tokens) |
| `--gpu-layers <n>` | `0` | Layers offloaded to GPU (0 = CPU-only) |
| `--temperature <f>` | `0.7` | Sampling temperature |
| `--top-p <f>` | `0.95` | Top-p nucleus sampling |
| `--max-tokens <n>` | `512` | Default output token limit |

The decode batch capacity follows `--ctx-size`. Requests whose tokenized prompt
exceeds that context are rejected with HTTP 400 instead of terminating the
server.

```
tiny-llama.exe --model E:\models\mistral-7b-q4.gguf --port 11434 --threads 8
```

## Routes

### `GET /v1/models`

Returns the loaded model as an OpenAI-format model list.

```json
{
  "object": "list",
  "data": [{ "id": "mistral-7b-q4", "object": "model", "created": 0, "owned_by": "local" }]
}
```

---

### `POST /v1/chat/completions`

OpenAI-compatible chat completion.

**Request**

```json
{
  "messages": [
    { "role": "system",  "content": "You are a helpful assistant." },
    { "role": "user",    "content": "What is 2 + 2?" }
  ],
  "temperature": 0.7,
  "top_p": 0.95,
  "max_tokens": 256
}
```

`temperature`, `top_p`, and `max_tokens` are optional and override the server defaults for this request only.

**Response**

```json
{
  "id": "chatcmpl-tiny",
  "object": "chat.completion",
  "created": 1728000000,
  "model": "mistral-7b-q4",
  "choices": [{
    "index": 0,
    "message": { "role": "assistant", "content": "4" },
    "finish_reason": "stop"
  }],
  "usage": { "prompt_tokens": -1, "completion_tokens": -1, "total_tokens": -1 }
}
```

`usage` counts are always `-1` (not tracked).

**Finish reasons**

| Value | Meaning |
|---|---|
| `stop` | Model emitted an end-of-generation token |
| `length` | `max_tokens` limit reached |
| `tool_calls` | Output is a tool call JSON object (see below) |

---

## Tool Calls

Pass a `tools` array in the request. The tools are injected as a JSON block into the system prompt; the model is instructed to respond with a JSON object when it needs to call a tool.

**Request**

```json
{
  "messages": [{ "role": "user", "content": "What is the weather in London?" }],
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get current weather for a city",
      "parameters": {
        "type": "object",
        "properties": { "city": { "type": "string" } }
      }
    }
  }]
}
```

**Response when tool is called**

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_0",
        "type": "function",
        "function": { "name": "get_weather", "arguments": "{\"city\":\"London\"}" }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

Tool call detection is pattern-based: if the trimmed model output is a JSON object containing `"name"` and `"arguments"` keys, `finish_reason` is set to `"tool_calls"`. The tool call `id` is always `call_0`; only one tool call per response is emitted.

---

## Behavior Notes

- **Stateless between requests.** The KV cache is cleared after every generation. Multi-turn conversation context must be re-sent in full with each request (standard OpenAI `messages` array).
- **Single-threaded inference.** Concurrent requests queue; they do not run in parallel.
- **Chat template.** The model's built-in chat template is applied via `llama_chat_apply_template`. Falls back to `<|role|>\ncontent\n` concatenation if the model has no template.
- **Sampler chain.** top_k(50) → top_p → temperature → dist (fixed seed).

---

## Build

Built with MSVC 2022, `/MD`, C++20, against llama-haswell (llama.cpp b9968 CPU+OpenCL build).

Project file: `C:\tmp\TINY_LLAMA.vcxproj`
Build script: `C:\tmp\build_tiny_llama.bat`
Source: `src\host\tiny-llama.cpp`
