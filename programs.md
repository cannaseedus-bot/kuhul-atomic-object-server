# Micronaut Programs and BSON Runtime

This guide describes how Micronaut metadata, Python microprograms, GGUF support, and `micronaut.bson` fit together in this repository.

## The key distinction

BSON is a data container. It stores source bytes and metadata; it does not execute Python. The host Python interpreter executes a bundled script after the Micronaut adapter verifies and stages it.

```text
micronaut.bson
  ├─ metadata: registries, manifests, schemas, model/runtime declarations
  ├─ microprograms: Python, K'UHUL, XAIML, shader and related source
  └─ resources: GGUF support package, UI assets, schemas, documentation

Micronaut adapter
  ├─ decodes BSON
  ├─ verifies package inventory and each embedded file hash
  ├─ stages files in a temporary directory
  └─ optionally launches one selected Python program with host Python
```

The bundle is marked `DATA_ONLY`. Listing, reading, decoding, or building it does not execute any embedded program.

## MML agents, GGUF metadata, and host tools

`mu-factory.py` parses the supported declarative MML subset and writes a candidate under `micronaut/generated/candidates/agents/<id>/`. The candidate contains the original MML, normalized `micronaut.mml.json`, a daemon `agent.json`, and a pattern-only `agent.xaiml`. Candidate directories are not loaded by the daemon. `mu-factory.py admit` copies a reviewed candidate into `micronaut/agents/`; admission still leaves execution, verification, commit, and tool grants disabled.

`micronaut.bat` first closes an older WPF menu and stops the prior Node orchestrator recorded in `.kuhul-data/writer.lock`, then opens the native WPF command surface in `micronaut/micronaut-command-menu-wpf.ps1`. It sends the matching orchestrator a termination signal, waits for its lock to clear, and removes a leftover lock only after confirming its owner exited and the loopback API stopped responding. If ownership cannot be verified or shutdown doesn’t complete, it refuses to launch another menu/server. Clickable entries come from `bus/Micronaut.CommandBus.psm1`; WPF uses native controls and does not depend on HTA/SVG rendering. Run `micronaut.bat bundle` to rebuild `micronaut.bson`, or `micronaut.bat kso` to package `neighborhood.jsonl` with the `neighborhood.attention.jsonl` sidecar into `field.kso`. The attention sidecar receives typed address annotations as part of that package operation. If WPF cannot start, the batch file offers a keyboard menu with the build actions.

The WPF **Daemon chat (embedded)** command starts the local orchestrator and opens `micronaut/daemon-chat-wpf` as a native WPF window. Its WebView2 control loads the existing `chat.html` UI from `127.0.0.1:61683`; the React runtime and compiled chat frame are served from local repository assets, so the chat does not depend on an external browser or CDN. The WebView navigation policy is limited to that loopback host and port. `micronaut/daemon-chat-wpf/DaemonChatWpf.csproj` builds the host when its executable is missing. Fresh XAIML session state is merged with the daemon's default session shape, including an empty `predicates` map, before evaluating `<condition>` templates.

The chat track picker reads the verified 71-entry semantic track registry from `vendor/key-grammar-kit/data/tracks`. `GET /api/daemon/tracks` returns its data-only catalog; model replies can select a track explicitly or use automatic routing. Selected track descriptions and fold labels are added as prompt context. The registry is index-only and marked `@no-eval`; listed capabilities remain descriptive and are not grants or executable calls. The BSON builder includes the track sources and registry.

`bus/rpc-api.json` is the editable capability map. Its logical ports separate callers from providers: `model-api` maps to fixed REST JSON routes and reads its base URL from `MICRONAUT_MODEL_API`; `graphics-compute` documents the existing OpenCL AdamW route through `NumpyTrain`; `static-site` dispatches to the loopback-only static host. `RPCList` can read the JSON source or the verified `rpcApi` BSON projection. `RPCCall` invokes only declared REST routes, permits HTTPS or loopback HTTP, and reads an optional bearer token from the named environment variable. Non-REST ports stay host-dispatched and do not become arbitrary RPC execution.

The `model-api` port also declares POST routes `forward` (`/v1/forward/`) and `backward` (`/v1/backward/`); these are called using the same host-configured endpoint and JSON-body rules as `chat-completions`.

Example:

```powershell
.\Micronaut.ps1 RPCList
$env:MICRONAUT_MODEL_API = 'http://127.0.0.1:8000'
.\Micronaut.ps1 RPCCall -RpcPort model-api -Entry models
.\Micronaut.ps1 StaticHost -InputPath .\site -Port 8080
.\Micronaut.ps1 StopService -ServiceName static-site
```

MML `<tool ref="..." permission="..."/>` entries are **requests**. `micronaut/tool_bridge.py` exposes an explicit registry API. Host code registers the actual Python callables and supplies a `HostGrant` issued by host policy. The bridge validates the registered JSON argument schema, checks the host grant, and dispatches the existing callable. The manifest cannot register a function, elevate its requested permission, create a grant, or send arbitrary Python/shell text to the dispatcher. The built-in reference registry contains only deterministic `graph.traverse` and `vector.score`; network search, replay memory, model inference, and program execution need explicit adapters and host grants before they become available.

`mu-factory.py list-tools` discovers the local registry. `gguf-py/gguf/micronaut.py` defines custom `micronaut.*` metadata names and `read_micronaut_manifest()` reads `micronaut.manifest` or `micronaut.mml` from a GGUF file for inspection. These keys are not standard GGUF keys; other readers may ignore them. Reading metadata does not activate the Micronaut. The host still validates MML, resolves references, checks tool schemas and grants, and passes any admitted operation through XCFE. GGUF remains tensors/tokenizer plus declarative metadata; it does not execute MML or embedded scripts.

## Micronaut FieldGraph

The fleet fold topology is authored in [micronaut_fieldgraph.gml](vendor/key-grammar-kit/data/micronaut_fieldgraph.gml). The paired `MicronautFieldGraph.mml` defines resident binding, Fibonacci node weights, gravity ranking, and W-C-R projection. GML is the canonical topology and MML is the projection contract; runtime state remains in the project's GML/MML ecosystem. No `.pt` artifact is used or emitted.

The System node is an entry node outside the six-phase cycle, with only a System→Pop edge. Its initial query is cold-started from its own feature/input; there is no implicit Xul→System edge. Gravity (`confidence × node_weight`) ranks residents separately and does not add a second multiplier to the W-C-R attention score.

`micronaut/glyph_buffer_engine.py` loads the stack-local native ABI at `micronaut/runtime/glyph_assets/native/native_glyph_engine.dll`; the engine does not resolve shader assets from another checkout. WGSL, HLSL, KLSL, and TSSL shader assets are copied beside it under `micronaut/runtime/glyph_assets/shaders/`, with byte counts and SHA-256 hashes in `assets.manifest.json`. Its GPT-2 HLSL catalog can load source and compile registered entry points to in-memory DXBC through Windows `D3DCompiler_47.dll`. When `MICRONAUT_DXC` points to a compatible `dxc.exe`, it also compiles those entry points to in-memory DXIL (`cs_6_0` by default). For example, set `MICRONAUT_DXC` to the host's DXC executable, then run `python micronaut/test_glyph_buffer_engine.py` to check the shaders with both compilers. The compiler and bytecode outputs are host dependencies and temporary data; they are not packed into the BSON. Compilation does not dispatch a shader. HLSL variants have distinct resource bindings, so execution still requires a D3D11/D3D12 host path that binds each kernel's buffers and constants. The native CPU glyph and matrix lanes are exposed by the copied DLL. This runtime uses no PyTorch `.pt` graph file.

Example flow:

```powershell
python mu-factory.py list-tools
python mu-factory.py create .\examples\research.mml.xml
# Review the generated candidate and its requested capabilities.
python mu-factory.py admit .\micronaut\generated\candidates\agents\research
python mu-factory.py inspect-gguf C:\models\model.gguf
python tools\build_micronaut_bson.py
```

The factory's MML schema is currently an explicit project subset, not a general MML standard. `program.entry` and phase actions are references only; the factory does not compile or execute K'uhul source.

## What is packaged

`tools/build_micronaut_bson.py` collects the runtime sources into one BSON document:

| Source | Contents |
| --- | --- |
| `micronaut/` | Micronaut runtime, XAIML, agent registry, folds, replay, shaders, docs, and candidate factory area |
| `field/` | π field kernel, types, constraints, hashes, specifications, and composition |
| `mu-py/` | Python adapters, bridges, GGUF metadata utilities, demos, and program tools |
| `micronaut/numpy_gpt_adam.py` | Character-tokenized next-character training with RoPE, SwiGLU, Grouped-Query Attention, preallocated KV-cached generation, CPU/OpenCL AdamW, and Safetensors checkpoints |
| `micronaut/opencl_adam.py` and `micronaut/runtime/kernels/adamw.cl` | OpenCL C-API AdamW dispatcher and device kernel; moment buffers persist on the selected OpenCL device |
| `micronaut/examples/numpy_gpt_training.txt` | Small raw-text corpus used by the default `NumpyTrain` command |
| `bus/` | PowerShell command catalog and fixed-ID dispatch used by the SVG command menu |
| `gguf-py/gguf/` | GGUF reader/writer and supporting Python package |
| `vendor/key-grammar-kit/data/manifest/` | K'UHUL, GML, AIML, CSS, and related key declarations |
| `vendor/key-grammar-kit/data/micronauts/` | Declarative Micronaut, model adapter, pipeline, tensor, and market-agent definitions; listed and inspected by `Micronaut.ps1` |
| root `manifest.json` and `Micronaut.ps1` | Project routing metadata and command host |
| root `mu-factory.py` and `micronaut.bat` | MML candidate factory and SVG command-menu launcher |
| tools and Daemon Bot app declarations | Distillation, attention, KSO packaging/validation, app and knowledge definitions |

`Micronaut.ps1 MicronautList` catalogs these local definitions, and `Micronaut.ps1 MicronautInspect -EntryPath <file>` displays one definition. The actions read JSON as metadata and show source files as text; they do not execute the contents. The BSON bundle includes this directory as data alongside the runtime sources.

`Micronaut.ps1 Distill -Word <word>` writes candidate neighborhood data only. Embedding is a separate operation; use `-WithAttention` to score only the distilled word, or run `Micronaut.ps1 Attention` explicitly to process the selected input file.

The NumPy transformer uses rotary position embeddings on attention queries and keys, SwiGLU feed-forward blocks, and Grouped-Query Attention with fewer cached K/V heads than query heads. The K/V cache stays at the smaller KV-head width; grouped attention aggregates shared-head gradients during training without repeating cache tensors. Cached keys are stored after RoPE is applied at their absolute position, avoiding repeated rotation as the cache grows. The configured maximum sequence length remains a runtime context limit. `NumpyTrain` and `NumpyGenerate` accept `-QueryHeads` and `-KVHeads` (defaults 4 and 2). It exposes `Micronaut.ps1 NumpyGenerate -PromptText <text>` for character-level tokenization and `-PromptTokens <ids>` for direct numeric IDs. Generation demonstrates context-window truncation and greedy or top-k token sampling. It currently uses freshly initialized demo weights; it is not backed by a pretrained model checkpoint.

`NumpyTrain -CheckpointPath <file.safetensors>` saves model tensors, GQA configuration, and the character-tokenizer vocabulary in a Safetensors container. `NumpyGenerate -CheckpointPath <file.safetensors>` validates and loads that checkpoint before generation. Checkpoint loading is strict about tensor names, dimensions, dtypes, and finite values; model weights are data and are never executed as code. The `safetensors` package is declared in `requirements.txt`.

`NumpyTrain -OptimizerBackend opencl` dispatches AdamW element updates through the OpenCL ICD selected from the installed driver. `-OpenCLDevice <name>` can select a device by platform/device name; `-WeightDecay <value>` controls decoupled AdamW decay. OpenCL moment buffers persist on the device, while NumPy forward/backward calculations and parameter transfers remain CPU-side. This is an optimizer compute path, not an all-GPU training path. The implementation uses `ctypes` against the OpenCL C API and does not depend on PyOpenCL.

The bundled `gpt2_adam.hlsl` kernel carries the same decoupled AdamW update and compiles to DXBC through `GlyphBufferEngine`; `NumpyTrain` currently dispatches the OpenCL kernel instead.

The resulting bundle contains a canonical Micronaut agent registry, a microprogram path catalog, and GGUF adapter path metadata. GGUF model weights are not included. They remain separate model artifacts referenced by model metadata.

Each file entry contains:

- `path`: normalized project-relative path
- `entryType`: `metadata`, `micro_program`, or `runtime_resource`
- `entryStatus`: `source` or `candidate`
- `bytes`, `sha256`, and BSON `Binary` content

The builder excludes caches, generated Python bytecode, logs, temporary files, and `.asx_memory.json` chat replay logs. BSON is capped at 15 MiB by default to stay below the common 16 MiB document limit.

## Build and inspect the bundle

From the project root in PowerShell:

```powershell
.\Micronaut.ps1 Bundle
.\Micronaut.ps1 BundleList
.\Micronaut.ps1 BundleGet -EntryPath gguf-py/gguf/metadata.py
```

The equivalent Python builder is:

```powershell
python tools\build_micronaut_bson.py
```

The Python bundle reader checks the BSON format, lifecycle fields, entry paths, entry hashes, and canonical inventory hash:

```powershell
python micronaut\bson_bundle.py verify
python micronaut\bson_bundle.py list
python micronaut\bson_bundle.py get micronaut/docs/micronaut.registry.json
```

`BundleGet` and `get` display source data. They do not run it.

## Run a bundled Python program

`mu-py/micronaut_adapter.py` is the explicit bundle-to-host-Python bridge. List the available bundled programs:

```powershell
python mu-py\micronaut_adapter.py --micronaut.bson micronaut.bson --list-programs
```

To launch one program, name its exact bundle path and pass `--execute`:

```powershell
python mu-py\micronaut_adapter.py `
  --micronaut.bson micronaut.bson `
  --run-script mu-py\kuhul_agent_bridge.py `
  --execute
```

Programs that accept arguments receive them after `--`:

```powershell
python mu-py\micronaut_adapter.py `
  --micronaut.bson micronaut.bson `
  --run-script mu-py\add_micronaut_metadata.py `
  --execute -- model.gguf adapter.json --output model-with-metadata.gguf
```

The adapter only launches `.py` entries below `mu-py/`, requires `--execute`, and rejects entries marked `candidate`. It verifies the bundle before staging its files in a temporary directory. It adds the staged `gguf-py` package to `PYTHONPATH`, then invokes the selected script in a child Python process. The timeout defaults to 600 seconds and can be set with `--timeout` (maximum 3600 seconds).

`Micronaut.ps1` exposes the same route:

```powershell
.\Micronaut.ps1 BundleRun `
  -EntryPath mu-py\kuhul_agent_bridge.py `
  -Execute
```

Pass script arguments through `-ScriptArgs`, for example:

```powershell
.\Micronaut.ps1 BundleRun `
  -EntryPath mu-py\add_micronaut_metadata.py `
  -Execute `
  -ScriptArgs @('model.gguf', 'adapter.json', '--output', 'model-with-metadata.gguf')
```

This is host-side Python execution, not execution “inside BSON.” Staging in a temporary directory is not an operating-system sandbox. A launched program inherits the host process’s file and network permissions and may have side effects. Only run programs you trust, and review their arguments and effects first. The explicit `--execute`/`-Execute` flag makes launch a deliberate host action; bundle hashes detect changed bytes but do not authenticate the bundle publisher.

## Callable daemon agents

There are two different agent systems in the repository. The live daemon agents below have callable conversation routes. The five `BUNDLE_TEMPLATES` are expert-routing bundle templates; creating one does not register a live agent or make its declared tools callable.

### Live XAIML and model agents

Create a user-owned daemon agent, then start it through the orchestrator:

```powershell
.\Micronaut.ps1 AgentCreate -AgentId garden-guide -AgentName "Garden Guide"
.\Micronaut.ps1 StartOrchestrator
.\Micronaut.ps1 AgentList
.\Micronaut.ps1 Chat -AgentId garden-guide
```

`AgentCreate` writes `micronaut/agents/<agent-id>/agent.json` and `agent.xaiml`. The JSON defines identity, system prompt, model profile, route references, and authority declarations. The XAIML bank supplies structured replies. Restart the orchestrator after editing the files so its registry reloads them.

The daemon CLI dispatches each user turn in this order:

1. Registered command handling, with one tool command allowed per turn.
2. XAIML pattern matching through that agent’s `replyRoute`.
3. Model inference through its declared `modelProfile` when no pattern matches.

The agent metadata exposes these per-agent routes:

| Route | Use |
| --- | --- |
| `POST /api/daemon/agents/{id}/reply` | Match XAIML patterns and return updated conversation state |
| `POST /api/daemon/agents/{id}/respond` | Send unmatched text to the configured model response path |
| `GET /api/daemon/agents/{id}/patterns` | Read the agent’s active pattern bank |
| `GET /api/daemon/agents` | List agents registered by the local runtime |

Example pattern request:

```json
{
  "text": "hello",
  "state": {},
  "mode": "buddy"
}
```

Example model response request:

```json
{
  "text": "Explain how a car tire loses pressure.",
  "history": [],
  "mode": "buddy"
}
```

The browser chat and `Micronaut.ps1 Chat` use the local orchestrator. Model profiles select a configured local backend and model. A declared endpoint or capability is routing metadata; it does not itself grant arbitrary tool execution.

### Expert-routing bundle templates

`mu-py/create_bundle.py` defines five metadata templates:

| Template | Intended routing domains |
| --- | --- |
| `CoderMicronaut` | Python, C/C++, JavaScript, debugging, general coding |
| `ChatMicronaut` | General questions, writing, reasoning, teaching |
| `DebugMicronaut` | Error analysis, Python debugging, testing |
| `MathMicronaut` | Mathematics, physics, statistics |
| `GeneralMicronaut` | General questions, research, planning |

List and generate these template bundles with:

```powershell
python mu-py\create_bundle.py --list
python mu-py\create_bundle.py `
  --name CoderMicronaut `
  --output .micronaut\agents\CoderMicronaut.adapter.bson `
  --model "C:\path\to\model.gguf"
```

These outputs use the legacy `micronaut.bundle` document shape. They are not the `micronaut.bson` source-package format and cannot be passed to the source-package script launcher. They contain a model path and hash metadata, not GGUF weights. Their `tools.enabled` and `tools.permissions` fields are declarations in the template; this repository does not enforce those permissions as operating-system controls.

`mu-py/micronaut_adapter.py` contains an expert `Router` that scores domains and selects experts for an input. The routing code is not a GGUF inference engine. The bundled `gguf-py` package reads and writes GGUF metadata and tensors; it does not run model inference. To make a template into a live conversational daemon agent, register an `agent.json`/XAIML pair with the local orchestrator and configure its supported model profile. That live daemon path is separate from the legacy expert-routing bundle format.

## GGUF and model metadata

The bundle includes two related parts:

- `gguf-py/gguf/metadata.py` reads model-card, model-configuration, generation, and override metadata and maps it to GGUF metadata keys.
- `gguf-py/gguf/micronaut.py` contains GGUF Micronaut adapter integration, alongside `gguf_reader.py`, `gguf_writer.py`, and `constants.py`.
- `mu-py/micronaut_adapter.py` loads Micronaut adapter configurations, provides expert-routing support, verifies the project bundle, and launches selected bundled Python programs.

`requirements.txt` installs the local GGUF package with `-e ./gguf-py`; its `pyproject.toml` declares NumPy, tqdm, PyYAML, and requests. BSON support is provided by PyMongo. None of these metadata tools places model tensors into `micronaut.bson` or changes a GGUF model unless a specifically launched program is given a model path and write operation.

## Runtime-factory updates

The runtime factory may write new or revised microprogram source and metadata under:

```text
micronaut/generated/candidates/
```

Rebuild the bundle after a factory update:

```powershell
.\Micronaut.ps1 Bundle
```

The builder labels files under that path `candidate`. Candidate entries are stored and inspectable, but `micronaut_adapter.py` will not launch them. They must be reviewed, validated, and promoted by the host before becoming source programs.

## Package contracts

- Bundle schema: `micronaut/docs/micronaut-bson.schema.json`
- Bundle format notes: `micronaut/docs/micronaut-bson-format.md`
- Agent registry: `micronaut/docs/micronaut.registry.json`
- Agent registry schema: `micronaut/docs/micronaut.agent.registry.schema.json`
- BSON builder: `tools/build_micronaut_bson.py`
- BSON reader: `micronaut/bson_bundle.py`
- Python adapter and launcher: `mu-py/micronaut_adapter.py`
- Host commands: `Micronaut.ps1`
