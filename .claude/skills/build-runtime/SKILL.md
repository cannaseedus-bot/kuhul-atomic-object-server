---
name: build-runtime
description: Build the K'UHUL C++ phase runtime (kuhul_phase_runtime.exe) using MSVC 2022 and CMake. Use when the C++ source has changed or the binary is missing.
disable-model-invocation: false
---

Build `kuhul_phase_runtime.exe` from `bin/src/`.

## Steps

1. Verify the required tools are present:
   - Visual Studio 2022 BuildTools: `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`
   - CMake: `C:\Program Files\CMake\bin\cmake.exe`

   If either path is missing, tell the user and stop — `build.bat` will fail silently.

2. Run the build script from the project root:

```batch
cd C:\public_html\kuhul
build.bat
```

3. Confirm the output exists:

```batch
dir kuhul\build\Release\kuhul_phase_runtime.exe
```

## If the build fails

- **CMake not found / wrong path:** The hardcoded paths in `build.bat` may need updating for this machine. Check `build.bat` lines that set `%CMAKE%` and `%VSPATH%`.
- **Compiler errors:** Show the first error from the MSVC output. The source is C++17 strict (`/permissive-`); common issues are missing includes or non-standard extensions.
- **CTest failures post-build:** `build.bat` runs `kuhul_xpath_conformance` and `kuhul_feed_serializer_conformance` after build. A failure here means the runtime compiled but its core conformance tests broke — report the specific test name and output.

## Paired micronaut: Build-Runtime-µ

This skill has a paired micronaut agent at `micronaut/agents/build-runtime/` (after admission).

**Skill → Agent:** Hand off a build request to the agent for phase-gated execution:
```
POST /api/daemon/agents/build-runtime/reply
{ "input": "build kuhul_phase_runtime" }
```
The agent runs through its phases — `bind_tool_paths → execute_build_gate → verify_artifacts` — and returns structured build status.

**Agent → Skill:** The agent can invoke this skill from a phase action via the orchestrator when it needs Claude-side reasoning (e.g., diagnosing a compiler error it can't resolve through pattern matching alone).

**Agent → Agent:** `Build-Runtime-µ` can route to other admitted agents (e.g., a test runner agent) via `/api/daemon/agents/<name>/reply` after a successful build.

MML spec: `examples/build-runtime.mml.xml`
Candidate: `micronaut/generated/candidates/agents/build-runtime/` — review and run `python mu-factory.py admit micronaut/generated/candidates/agents/build-runtime` to promote to live registry.
