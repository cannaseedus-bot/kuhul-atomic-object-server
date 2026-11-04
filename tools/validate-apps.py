#!/usr/bin/env python3
"""Validate ASX mini-app manifests and their @imports."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "vendor/key-grammar-kit/data/apps"

MINI_REQ = ["@id", "@key", "@mount", "@components", "@programs", "@events", "@permissions", "@lifecycle"]
KEYBASE_REQ = ["@authority", "keys"]
RUNTIME_REQ = ["@surface", "@endpoint", "keys"]

def main():
    failures = []
    checked = 0
    for p in sorted(APPS.iterdir()):
        if p.suffix != ".json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append((p.name, f"parse: {e}"))
            continue
        kind = data.get("@kind")
        if kind == "asx.mini-app.v1":
            checked += 1
            missing = [k for k in MINI_REQ if k not in data]
            if missing:
                failures.append((p.name, f"missing {missing}"))
            for imp in data.get("@imports", []):
                if not isinstance(imp, dict):
                    continue  # symbolic contract id, not a filesystem path
                ref = imp.get("@ref", "")
                base = ref.split("#")[0]
                if base and not (ROOT / base).exists():
                    failures.append((p.name, f"import missing: {base}"))
        elif kind == "asx.atomic.keybase.v1":
            checked += 1
            missing = [k for k in KEYBASE_REQ if k not in data]
            if missing:
                failures.append((p.name, f"missing {missing}"))
        elif kind == "asx.atomic.runtime.manifest.v1":
            checked += 1
            missing = [k for k in RUNTIME_REQ if k not in data]
            if missing:
                failures.append((p.name, f"missing {missing}"))
    print(f"apps checked: {checked}")
    for name, msg in failures:
        print(f"  FAIL {name}: {msg}")
    print("result:", "PASS" if not failures else "FAIL")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
