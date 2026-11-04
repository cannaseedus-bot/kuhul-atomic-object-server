"""
rebuild.py
Build kuhul_host.exe — generic ASX/KUHUL Win32 + WebView2 host.

Usage:
  python rebuild.py                    # builds into ./bin/kuhul_host.exe
  python rebuild.py --out path/to/app  # copy exe + server into an app folder

The resulting kuhul_host.exe reads manifest.json from its own directory.
Drop it into any ASX/KUHUL app folder with a manifest.json and run it.
"""

import os, sys, subprocess, urllib.request, zipfile, pathlib, shutil, argparse

# ── Args ──────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument('--out', default=None, help='Copy built files into this app folder')
args = parser.parse_args()

# ── Paths ─────────────────────────────────────────────────────────────────────

HERE    = pathlib.Path(__file__).parent.resolve()
SRC     = HERE / "src" / "kuhul_host.cpp"
OUT_DIR = HERE / "bin"
OUT_EXE = OUT_DIR / "kuhul_host.exe"
SDK_DIR = HERE / "webview2_sdk"
WV2_ZIP = HERE / "webview2_sdk.nupkg"

# WebView2 SDK — same version as cockpit_host for runtime compatibility
WV2_VER   = "1.0.2849.39"
WV2_NUGET = (
    f"https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2"
    f"/{WV2_VER}/microsoft.web.webview2.{WV2_VER}.nupkg"
)

def run(*cmd, **kw):
    print(">>", " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode != 0:
        print(f"[FAIL] exit {r.returncode}")
        sys.exit(r.returncode)
    return r

# ── 1. Download WebView2 SDK ──────────────────────────────────────────────────

if not any(SDK_DIR.rglob("WebView2.h")):
    print(f"[sdk] downloading WebView2 SDK {WV2_VER}...")
    ctx = __import__("ssl").create_default_context()
    ctx.check_hostname = False; ctx.verify_mode = 0
    with urllib.request.urlopen(WV2_NUGET, context=ctx) as resp, \
         open(WV2_ZIP, "wb") as f:
        shutil.copyfileobj(resp, f)
    SDK_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(WV2_ZIP) as z:
        z.extractall(SDK_DIR)
    WV2_ZIP.unlink(missing_ok=True)
    print("[sdk] done")
else:
    print("[sdk] already present")

# Locate lib + include
wv2_lib = next(
    (p for p in [
        SDK_DIR / "build" / "native" / "x86" / "WebView2LoaderStatic.lib",
        *SDK_DIR.rglob("WebView2LoaderStatic.lib"),
    ] if p.exists()),
    None
)
if not wv2_lib:
    print("[ERROR] WebView2LoaderStatic.lib not found"); sys.exit(1)

inc_dir = next(
    (p.parent for p in SDK_DIR.rglob("WebView2.h")),
    SDK_DIR / "build" / "native" / "include"
)
print(f"[sdk] lib={wv2_lib}")
print(f"[sdk] inc={inc_dir}")

# ── 2. Find MSVC ──────────────────────────────────────────────────────────────

import glob as _glob

vcvars = None
for pattern in [
    r"C:\Program Files*\Microsoft Visual Studio\**\vcvarsall.bat",
    r"C:\Program Files*\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvarsall.bat",
]:
    hits = _glob.glob(pattern, recursive=True)
    if hits: vcvars = hits[0]; break

if not vcvars:
    print("[ERROR] vcvarsall.bat not found"); sys.exit(1)
print(f"[vc] {vcvars}")

# ── 3. Compile (x86 to match WebView2 fixed runtime) ─────────────────────────

OUT_DIR.mkdir(parents=True, exist_ok=True)
bat = HERE / "_build.bat"
bat.write_text(
    f'@echo off\n'
    f'call "{vcvars}" x86\n'
    f'cl "{SRC}" /EHsc /std:c++17 /O2 '
    f'"/I{inc_dir}" '
    f'/Fe:"{OUT_EXE}" '
    f'"{wv2_lib}" '
    f'user32.lib ole32.lib shell32.lib shlwapi.lib advapi32.lib version.lib gdi32.lib '
    f'/link /SUBSYSTEM:WINDOWS\n'
)
r = subprocess.run(["cmd", "/c", str(bat)])
bat.unlink(missing_ok=True)
if r.returncode != 0:
    print(f"[FAIL] compile exit {r.returncode}"); sys.exit(r.returncode)

print(f"\n[ok] built: {OUT_EXE}")

# ── 4. Optionally copy into app folder ────────────────────────────────────────

if args.out:
    dest = pathlib.Path(args.out).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_EXE,              dest / "kuhul_host.exe")
    shutil.copy2(HERE / "kuhul_server.js", dest / "kuhul_server.js")
    print(f"[ok] deployed to: {dest}")
    print(f"[ok] run: {dest}\\kuhul_host.exe")
else:
    print(f"[ok] run: {OUT_EXE}")
    print(f"      or: python rebuild.py --out path/to/your/app")
