#!/usr/bin/env python3
"""Local REST API for the K'UHUL phase runtime executable.

Run with: python bin/rest_api.py [--host 127.0.0.1] [--port 6170]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXECUTABLE = ROOT / "bin" / "kuhul_phase_runtime.exe"
ALLOWED_EXTENSIONS = {".kbnf", ".kgf", ".kl"}
MAX_REQUEST_BYTES = 1_048_576
MAX_FILE_BYTES = 262_144
MAX_FILES = 16
PHASE_NAMES = {"POP": "Pop", "WO": "Wo", "YAX": "Yax", "SEK": "Sek",
               "CHEN": "Ch'en", "CH'EN": "Ch'en", "XUL": "Xul"}


def runtime_report(executable: Path) -> dict:
    if not executable.is_file():
        raise FileNotFoundError(f"runtime executable not found: {executable}")
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, timeout=5, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"runtime exited with {result.returncode}")

    transitions = []
    authorization = {}
    for line in result.stdout.splitlines():
        transition = re.fullmatch(r"\s*(\w+)\s*->\s*(\w+)\s+legal=(yes|no)\s*", line)
        if transition:
            source, target, legal = transition.groups()
            transitions.append({
                "from": PHASE_NAMES.get(source.upper(), source),
                "to": PHASE_NAMES.get(target.upper(), target),
                "legal": legal == "yes",
            })
            continue
        auth = re.fullmatch(r"\s*(\w+)\s+(\w+)\s+authorized=(yes|no)\s*", line)
        if auth:
            phase, operation, allowed = auth.groups()
            authorization[f"{PHASE_NAMES.get(phase.upper(), phase)} {operation}"] = allowed == "yes"

    return {
        "status": "ok",
        "runtime": "kuhul_phase_runtime",
        "executable": str(executable),
        "transitions": transitions,
        "operation_authorization": authorization,
    }


def validate_files(executable: Path, payload: object) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ValueError("request JSON must contain a 'files' array")
    files = payload["files"]
    if not files:
        raise ValueError("files must not be empty")
    if len(files) > MAX_FILES:
        raise ValueError(f"at most {MAX_FILES} files may be validated per request")
    if not executable.is_file():
        raise FileNotFoundError(f"runtime executable not found: {executable}")

    normalized = []
    total_bytes = 0
    seen_names = set()
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise ValueError(f"files[{index}] must be an object")
        name, content = entry.get("name"), entry.get("content")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name)
                or Path(name).name != name):
            raise ValueError(f"files[{index}].name must be a plain filename")
        if name.casefold() in seen_names:
            raise ValueError(f"files[{index}].name duplicates another input filename")
        seen_names.add(name.casefold())
        if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValueError(f"files[{index}].name extension must be one of {sorted(ALLOWED_EXTENSIONS)}")
        if not isinstance(content, str):
            raise ValueError(f"files[{index}].content must be a string")
        data = content.encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"files[{index}] exceeds {MAX_FILE_BYTES} bytes")
        total_bytes += len(data)
        normalized.append((name, data))
    if total_bytes > MAX_REQUEST_BYTES:
        raise ValueError(f"combined file content exceeds {MAX_REQUEST_BYTES} bytes")

    results = []
    with tempfile.TemporaryDirectory(prefix="kuhul-runtime-api-") as tmp:
        temp_root = Path(tmp)
        for name, data in normalized:
            input_path = temp_root / name
            input_path.write_bytes(data)
            try:
                process = subprocess.run(
                    [str(executable), str(input_path)],
                    cwd=temp_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                results.append({"name": name, "valid": False, "error": "runtime validation timed out"})
                continue
            output = "\n".join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
            output = output.replace(str(input_path), name)
            results.append({"name": name, "valid": process.returncode == 0, "output": output})

    valid_count = sum(1 for item in results if item["valid"])
    return {
        "status": "valid" if valid_count == len(results) else "invalid",
        "valid_count": valid_count,
        "file_count": len(results),
        "files": results,
    }


def make_handler(executable: Path):
    class RuntimeHandler(BaseHTTPRequestHandler):
        server_version = "KuhulPhaseRuntimeAPI/1.0"

        def _json(self, status: int, value: dict):
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self._json(200, {
                    "service": "kuhul-phase-runtime-api",
                    "endpoints": {
                        "GET /health": "runtime availability",
                        "GET /phases": "phase transitions and operation authorization",
                        "POST /validate": "validate in-memory .kbnf, .kgf, or .kl files",
                    },
                })
            elif path == "/health":
                try:
                    report = runtime_report(executable)
                    self._json(200, {"status": "ok", "runtime": report["runtime"]})
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    self._json(503, {"status": "unavailable", "error": str(exc)})
            elif path == "/phases":
                try:
                    self._json(200, runtime_report(executable))
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    self._json(503, {"status": "unavailable", "error": str(exc)})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if urlsplit(self.path).path != "/validate":
                self._json(404, {"error": "not found"})
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._json(415, {"error": "Content-Type must be application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0:
                self._json(400, {"error": "valid Content-Length is required"})
                return
            if length > MAX_REQUEST_BYTES:
                self._json(413, {"error": f"request exceeds {MAX_REQUEST_BYTES} bytes"})
                return
            try:
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
                result = validate_files(executable, payload)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self._json(400, {"error": str(exc)})
                return
            except FileNotFoundError as exc:
                self._json(503, {"error": str(exc)})
                return
            except OSError as exc:
                self._json(500, {"error": str(exc)})
                return
            self._json(200, result)

        def log_message(self, format, *args):
            print("[runtime-api] " + format % args)

    return RuntimeHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: localhost only)")
    parser.add_argument("--port", type=int, default=6170)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXECUTABLE)
    args = parser.parse_args()
    executable = args.exe.resolve()
    if not executable.is_file():
        parser.error(f"runtime executable not found: {executable}")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(executable))
    print(f"K'UHUL runtime REST API listening at http://{args.host}:{args.port}")
    print(f"runtime executable: {executable}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
