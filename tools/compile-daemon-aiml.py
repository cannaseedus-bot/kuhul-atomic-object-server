#!/usr/bin/env python3
"""Single-source reconciliation for the 86-entry daemon FAQ.

Canonical source: vendor/key-grammar-kit/data/apps/daemon-bot-expanded.aiml
Mirrors:
  - manifest.json -> aimlDaemon.patterns (node templates)
  - daemon-bot-knowledge.json -> records (plain-text templates)
"""
import json, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AIML = ROOT / "vendor/key-grammar-kit/data/apps/daemon-bot-expanded.aiml"
MANIFEST = ROOT / "manifest.json"
KNOWLEDGE = ROOT / "vendor/key-grammar-kit/data/apps/daemon-bot-knowledge.json"

STAR = re.compile(r'(<star(?:\s+index\s*=\s*"\d+")?\s*/>)')

def compile_template(text):
    nodes = []
    for part in STAR.split(text):
        if not part:
            continue
        m = re.fullmatch(r'<star(?:\s+index\s*=\s*"(\d+)")?\s*/>', part)
        if m:
            node = {"tag": "star"}
            if m.group(1):
                node["index"] = int(m.group(1))
            nodes.append(node)
        else:
            nodes.append({"tag": "text", "value": part})
    return nodes

def uncompile(nodes):
    out = []
    for n in nodes:
        if isinstance(n, dict) and n.get("tag") == "star":
            out.append('<star index="%d"/>' % n["index"] if n.get("index") else "<star/>")
        elif isinstance(n, dict) and n.get("tag") == "text":
            out.append(n.get("value", ""))
        elif isinstance(n, str):
            out.append(n)
    return "".join(out)

def main():
    root = ET.parse(str(AIML)).getroot()
    compiled = {}
    for cat in root.findall("category"):
        pat = cat.find("pattern"); tpl = cat.find("template")
        if pat is None or tpl is None:
            continue
        compiled[(pat.text or "").strip()] = "".join(tpl.itertext())

    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    replaced = 0
    for p in m["aimlDaemon"]["patterns"]:
        if p.get("id", "").startswith("daemon.") and p.get("pattern") in compiled:
            p["template"] = compile_template(compiled[p["pattern"]])
            replaced += 1
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    k = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    changed = 0
    for rec in k.get("records", []):
        pat = rec.get("pattern")
        if pat in compiled and rec.get("template") != compiled[pat]:
            rec["template"] = compiled[pat]
            changed += 1
    k["category_count"] = len(k.get("records", []))
    KNOWLEDGE.write_text(json.dumps(k, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    man = {p["pattern"]: p["template"] for p in m["aimlDaemon"]["patterns"] if p.get("id", "").startswith("daemon.")}
    know = {r["pattern"]: r["template"] for r in k.get("records", [])}
    drift = []
    for pat in sorted(set(compiled) | set(man) | set(know)):
        a = compiled.get(pat)
        b = uncompile(man[pat]) if pat in man else None
        c = know.get(pat)
        if not (a == b == c):
            drift.append(pat)
    print(f"manifest templates replaced: {replaced}")
    print(f"knowledge records changed: {changed}")
    print(f"knowledge records: {len(k.get('records', []))} | category_count: {k['category_count']}")
    print(f"triple-source drift after sync: {drift if drift else 'none'}")
    return 1 if drift else 0

if __name__ == "__main__":
    raise SystemExit(main())
