#!/usr/bin/env python3
"""Merge the vendor 68-mode behavior registry into the runtime binding file.

The runtime file stays authoritative for routing bindings (micronauts/phases).
Vendor-only modes are added with empty routing bindings so /api/behavior/modes
exposes the full registry without inventing capabilities.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor/key-grammar-kit/data/grammar/daemon-behavior-modes.v1.json"
RUNTIME = ROOT / "micronaut/behavioral-modes.json"

def label(mid):
    return " ".join(part.capitalize() for part in mid.replace("-", " ").replace("_", " ").split())

def main():
    vendor = json.loads(VENDOR.read_text(encoding="utf-8"))
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    modes = dict(runtime.get("modes", {}))

    for vmode in vendor.get("modes", []):
        mid = vmode.get("id")
        if not mid:
            continue
        if mid in modes:
            existing = modes[mid]
            for extra in ("behavior", "default_questions", "bias_vector", "category", "memory_default"):
                if extra in vmode and extra not in existing:
                    existing[extra] = vmode[extra]
            continue
        modes[mid] = {
            "key": "\u2af3MODE:" + mid.upper(),
            "label": label(mid),
            "description": vmode.get("description", ""),
            "micronauts": [],
            "phases": {},
            "behavior": vmode.get("behavior"),
            "default_questions": vmode.get("default_questions", []),
            "bias_vector": vmode.get("bias_vector"),
            "category": vmode.get("category"),
            "memory_default": vmode.get("memory_default"),
        }

    runtime["modes"] = modes
    RUNTIME.write_text(json.dumps(runtime, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"behavioral-modes.json now has {len(modes)} modes (vendor {len(vendor.get('modes', []))})")

if __name__ == "__main__":
    main()
