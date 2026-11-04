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
