# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

K'UHUL Atomic Object Server (`lam.o`) — a formal compute system implementing the K'UHUL language runtime, deterministic fold-based learning lanes, and micronaut agent infrastructure. Windows-primary (MSVC, PowerShell, WPF).

Multi-language monorepo: C++17 (`bin/src/`), Python 3.10+ (`micronaut/`, `tools/`), Node.js (`lib/`, orchestrator), PowerShell (`Micronaut.ps1`), K'UHUL source (`.kuhul`, `.kgf`, `.gml`).

## Build

**C++ runtime** (`kuhul_phase_runtime.exe`):
```batch
build.bat
```
Requires Visual Studio 2022 BuildTools at `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools` and CMake at `C:\Program Files\CMake\bin\cmake.exe`. If those paths differ, edit `build.bat`. Output: `kuhul\build\Release\kuhul_phase_runtime.exe`.

**Node.js orchestrator:**
```bash
npm install
npm start       # starts on http://localhost:61683
```

**Python dependencies:**
```bash
pip install -r requirements.txt
pip install -e gguf-py/    # editable GGUF metadata package
```

## Linting

**JavaScript/Node.js:**
```bash
npm run lint          # ESLint across all .js/.cjs/.mjs files
```

**Python:**
```bash
ruff check micronaut/ tools/ flat/ field/    # check
ruff check --fix micronaut/ tools/ flat/ field/  # auto-fix safe issues
```

## Testing

Run all four suites; all must pass before a change is considered complete:

```batch
vendor\key-grammar-kit\test.bat
```
Expects 16 track tests / 7 PASS checks.

```bash
python -m unittest discover -s micronaut -t . -p "test_*.py" -q
```
Expects 111 unit tests.

```bash
python flat\test_learning_lane_durable.py
```
Expects 1 standalone pass.

```bash
npm test
```
Node native test harness.

One pre-existing glyph_buffer_engine import error appears in discovery output but passes when run directly — do not investigate it unless specifically tasked.

## Micronaut Control Surface

```batch
micronaut.bat                             # WPF menu (keyboard fallback if WPF unavailable)
micronaut.bat bundle                      # Rebuild micronaut.bson
micronaut.bat kso                         # Package neighborhood.jsonl → field.kso
```

```powershell
.\Micronaut.ps1 Health
.\Micronaut.ps1 Bot -Prompt "text" -Backend ollama
.\Micronaut.ps1 NumpyTrain -InputPath data.txt [-OptimizerBackend cpu|opencl]
.\Micronaut.ps1 Bundle
.\Micronaut.ps1 Package -InputPath neighborhood.jsonl -OutputPath field.kso -All
```

Full action reference (AgentCreate, Chat, Services, Worker, StartPhaseRuntimeApi, etc.): @Micronaut.ps1

## Skills

Project skills live in `.claude/skills/`. Invoke with `/skill-name` or let Claude trigger them automatically.

| Skill | Invocation | Purpose |
|---|---|---|
| `run-tests` | `/run-tests` | Run all 4 test suites in order with expected counts |
| `build-runtime` | `/build-runtime` | Build `kuhul_phase_runtime.exe`; has paired `Build-Runtime-µ` micronaut |
| `skill-creator` | `/skill-creator <name>` | Create a new skill + paired micronaut candidate via `mu-factory.py` |

**Adding a new skill:** Use `/skill-creator <name>`. It writes `.claude/skills/<name>/SKILL.md`, generates `examples/<name>.mml.xml`, and scaffolds the micronaut candidate with `mu-factory.py create`. Review the candidate, then `python mu-factory.py admit micronaut/generated/candidates/agents/<name>` to promote it to the live daemon registry.

**Skill ↔ Agent routing** (after admission): skills and their paired micronauts share an id and communicate through the orchestrator:
- Skill → Agent: `POST /api/daemon/agents/<name>/reply`
- Agent → Skill: phase action triggers skill invocation via orchestrator
- Agent → Agent: `POST /api/daemon/agents/<other-name>/reply`

Skills are formal first-class entities in the daemon: `@lanes.skills` (dict 1, bus=intent) in `daemon-bot.xjson` wires each skill to an expert via `@edges` at the Sek phase. When adding a skill through `/skill-creator`, also register it in that file to wire it into intent routing. Full daemon architecture: @daemon-bot.xjson

**Model profiles** (backend, endpoint, temperature, context size) for all daemon actions are declared in `micronaut/models.toml` — including `[profiles.openai_compatible]` for OpenAI-compatible endpoints (LM Studio at `http://127.0.0.1:17889/v1`). Edit that file to change which model a skill or agent uses: @micronaut/models.toml

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `61683` | Orchestrator HTTP port |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `DEFAULT_MODEL` | `llama3` | Fallback inference model |
| `KUHUL_DATA_DIR` | `.kuhul-data/` | K'UHUL database directory |
| `KUHUL_MICRONAUT_ROOT` | (set by micronaut.bat) | Micronaut workspace root |
| `MICRONAUT_MODEL_API` | — | Override model endpoint (e.g., LM Studio) |
| `MICRONAUT_DXC` | — | Optional path to `dxc.exe` for DXIL shader compilation |

## K'UHUL Formal Rules (from RULES.md)

Violations here cause test failures or accumulator refusals — do not work around them.

**Scoring:**
- `S_base = W * C * R` — verified exactly to ±1e-9; never recompute, a mismatch is a caller bug
- `G` is always 0 or 1, never fractional
- `S_effective = S_base * G` — stored separately
- `C` is evidence-derived only; `R` is structural coverage or embedding similarity

**Learning:**
- `delta = eta * gradient` — `eta` comes from the `.kgf` declaration, never default
- `gradient = target - prediction` — both values must be in [0, 1]
- Updates bounded: `|delta| <= MAX_STEP`
- Corpus prior is immutable; feedback sources are never averaged

**Storage:**
- Key: `sha256([principal, workspace, proposal_id])` — replaying identical payload is idempotent
- Reusing a key with a different payload is refused, never merged

**Phase order** (canonical; `Chen` / `Ch_en` / `Ch'en` are synonyms):
```
Yax → Sek → Ch'en → Xul → [System/Pop]
```
Semantic step flips exactly one address bit; phase step advances one C6 step. `Xul → Pop` wrap requires `new_execution`.

**Grammar declarations:**
- Every `.kgf` must be declared in the manifest and pass `check_2d_key_graph_execution_field.py` before load
- Feature mapping for `ParameterMappingLane` must be declared; never inferred
- If you change `SCORE_RULE`, `LEARNING_RATE`, or `MAX_STEP`, update their consumer in the same commit

## Two-Lane Separation

`flat/` and `micronaut/` are **separate deployment lanes** — never mix code between them:

| Lane | Formula | Location |
|---|---|---|
| Flat | `delta = G` | `flat/` |
| Micronaut | `delta = eta * gradient` | `micronaut/` |

A deployment must declare which lane it uses.

## Gotchas

- **Lock files:** `.kuhul-data/writer.lock` can go stale after a force kill. `stop-before-launch.ps1` manages cleanup; run it before restarting if the service refuses to start.
- **SQLite:** All connections must close on every code path, including error paths. Long-running servers must manage connection lifecycle explicitly.
- **WPF chat:** Requires WebView2 runtime and `micronaut/runtime/glyph_assets/native/native_glyph_engine.dll`. Build from `micronaut/daemon-chat-wpf/DaemonChatWpf.csproj` if the DLL is missing.
- **K'UHUL phase names are strict:** Parser canonicalizes synonyms at load; near-misses fail silently until load time.
- **LM Studio:** Set `OLLAMA_URL` or `MICRONAUT_MODEL_API` to point at LM Studio's endpoint; the orchestrator defaults to Ollama.

## Directory Guide

```
bin/src/            C++ phase runtime (CMake project)
micronaut/          Python ML: learning lanes, gradient, fold orchestrator, tests
flat/               Alternate learning lane deployment (delta = G model)
field/              π-field kernel, constraints, composition
vendor/key-grammar-kit/  Grammar spec, stdlib, track registry, test.bat
lib/                Node.js bridges (SCXQ2, store, approval loop, XJSON)
tools/              Python build tools (validators, distillers, compilers)
tests/              Node test suites (api, daemon, store, cfpc)
examples/           Starter .kbnf / .kgf / .kl files
.micronaut/         Runtime state: checkpoints, logs, worker proposals
.kuhul-data/        SQLite stores, lock files
```
