"""Install the ELIZA-µ semantic bindings into the question-engine KGF copies.

Atomic and structurally idempotent:

  * the existing file is parsed, not string-matched
  * only missing declarations are added; nothing is duplicated
  * `classifies_as` is renamed to `suggests_gap`, because an AIML match must not
    decide the user's knowledge gap
  * the result is validated before the original file is replaced
  * writing goes through a temporary file and os.replace, so a failure cannot
    leave a half-written KGF behind

Re-running makes no changes and reports that the bindings are already installed.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KGF_FILES = [
    ROOT / "vendor/key-grammar-kit/data/grammar/kuhul-question-engine.kgf",
    ROOT / "vendor/key-grammar-kit/kuhul-question-engine.kgf",
]

QNAME = r"[A-Za-z][A-Za-z0-9_-]*:[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*"
IDENT = r"[A-Za-z][A-Za-z0-9_-]*"

_KEY = re.compile(
    rf"^key\s+(?P<name>{QNAME})\s+kind\s+(?P<kind>{IDENT})"
    r'(?:\s+value\s+(?:"(?P<quoted>[^"]*)"|(?P<bare>[^;]+)))?\s*;$'
)
_EDGE = re.compile(
    rf"^edge\s+({QNAME})\s*->\s*({QNAME})\s+type\s+({IDENT})"
    r"(?:\s+order\s+\d+)?(?:\s+weight\s+-?\d+(?:\.\d+)?)?;$"
)
_NAMESPACE = re.compile(rf"^namespace\s+({IDENT}):{IDENT}\s+domain\s+{IDENT};$")
_COMMENT = re.compile(r"\(\*.*?\*\)", re.S)

EXPECTED_NAMESPACES = ["eliza", "aiml", "srai", "cfpc", "fact"]
EXPECTED_KEYS = [
    ("eliza:MEMORY_FAILURE", "semantic_key", "the model keeps forgetting"),
    ("aiml:FORGETTING_PATTERN", "pattern", "MY MODEL KEEPS FORGETTING *"),
    ("srai:DIAGNOSE_MEMORY", "canonical_intent", "diagnose memory"),
    ("cfpc:KNOWLEDGE_GAP", "gap_family", "missing_information"),
    ("cfpc:MEMORY_FAILURE_MECHANISM", "gap", "KNOWLEDGE_GAP_NO_VALUES"),
    ("cfpc:RETENTION_SCOPE", "gap", "KNOWLEDGE_GAP_NO_KEYS"),
    ("question:STORAGE_OR_RETRIEVAL", "question",
     "Is the information lost from storage, or is retrieval failing?"),
    ("question:WHICH_SESSION", "question",
     "Does it fail across sessions, or only within one?"),
    # Temporal facts: the identity stays, the observation changes.
    ("fact:SATURN_MOONS", "semantic_key", "confirmed_saturnian_satellites"),
    ("fact:SATURN_2025_03", "observation_candidate", "274|effective=2025-03|source=NASA|verified=false"),
    ("fact:SATURN_2026_06", "observation_candidate", "293|effective=2026-06|source=WIKIPEDIA|verified=false"),
]
EXPECTED_EDGES = [
    ("eliza:MEMORY_FAILURE", "matched_by", "aiml:FORGETTING_PATTERN"),
    ("aiml:FORGETTING_PATTERN", "redirects_to", "srai:DIAGNOSE_MEMORY"),
    ("srai:DIAGNOSE_MEMORY", "suggests_gap", "cfpc:MEMORY_FAILURE_MECHANISM"),
    ("srai:DIAGNOSE_MEMORY", "suggests_gap", "cfpc:RETENTION_SCOPE"),
    ("cfpc:MEMORY_FAILURE_MECHANISM", "specializes", "cfpc:KNOWLEDGE_GAP"),
    ("cfpc:RETENTION_SCOPE", "specializes", "cfpc:KNOWLEDGE_GAP"),
    ("cfpc:MEMORY_FAILURE_MECHANISM", "proposes", "question:STORAGE_OR_RETRIEVAL"),
    ("cfpc:RETENTION_SCOPE", "proposes", "question:WHICH_SESSION"),
    ("fact:SATURN_MOONS", "candidate_historical_observation", "fact:SATURN_2025_03"),
    ("fact:SATURN_MOONS", "candidate_historical_observation", "fact:SATURN_2026_06"),
    ("fact:SATURN_2026_06", "candidate_supersedes", "fact:SATURN_2025_03"),
]
RENAMED_RELATION = {"classifies_as": "suggests_gap"}
RENAME_SOURCES = {"srai:DIAGNOSE_MEMORY"}


def parse(text):
    """Keys, edges, namespaces, and the edge line numbers, from KGF text."""
    clean = _COMMENT.sub("", text)
    keys, edges, namespaces, lines = {}, {}, set(), {}
    for number, raw in enumerate(clean.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        match = _NAMESPACE.match(line)
        if match:
            namespaces.add(match.group(1))
            continue
        match = _KEY.match(line)
        if match:
            value = match.group("quoted")
            if value is None:
                value = (match.group("bare") or "").strip()
            keys[match.group("name")] = (match.group("kind"), value)
            continue
        match = _EDGE.match(line)
        if match:
            edges[(match.group(1), match.group(3), match.group(2))] = True
            lines[number] = line
    return keys, edges, namespaces, lines


def apply_renames(text):
    """Rewrite renamed relations on the affected edges only."""
    out, changed = [], 0
    for raw in text.splitlines():
        line = raw.strip()
        match = _EDGE.match(line)
        if match and match.group(3) in RENAMED_RELATION and match.group(1) in RENAME_SOURCES:
            raw = raw.replace(match.group(3), RENAMED_RELATION[match.group(3)], 1)
            changed += 1
        out.append(raw)
    return "\n".join(out) + "\n", changed


def apply_temporal_candidate_contract(text):
    """Keep unverified temporal values and relations explicitly provisional."""
    obsolete_keys = {"fact:SATURN_2026_03", "fact:SATURN_2026_08"}
    expected_keys = {name: (kind, value) for name, kind, value in EXPECTED_KEYS
                     if name.startswith("fact:SATURN_") and name != "fact:SATURN_MOONS"}
    expected_edges = {(source, target): relation for source, relation, target in EXPECTED_EDGES
                      if source.startswith("fact:SATURN_") and target.startswith("fact:SATURN_")}
    out, changed = [], 0
    for raw in text.splitlines():
        line = raw.strip()
        key_match = _KEY.match(line)
        if key_match and key_match.group("name") in obsolete_keys:
            changed += 1
            continue
        if key_match and key_match.group("name") in expected_keys:
            name = key_match.group("name")
            kind, value = expected_keys[name]
            current = key_match.group("quoted")
            if current is None:
                current = (key_match.group("bare") or "").strip()
            if (key_match.group("kind"), current) != (kind, value):
                raw = f'key {name} kind {kind} value "{value}";'
                changed += 1
        edge_match = _EDGE.match(raw.strip())
        if edge_match and (edge_match.group(1) in obsolete_keys or edge_match.group(2) in obsolete_keys):
            changed += 1
            continue
        if edge_match and (edge_match.group(1), edge_match.group(2)) in expected_edges:
            source, target = edge_match.group(1), edge_match.group(2)
            relation = expected_edges[(source, target)]
            if edge_match.group(3) != relation:
                raw = f"edge {source} -> {target} type {relation};"
                changed += 1
        out.append(raw)
    return "\n".join(out) + "\n", changed


def validate(text):
    """Structural checks that must pass before the file is replaced."""
    keys, edges, namespaces, _ = parse(text)
    errors = []
    for name in keys:
        prefix = name.split(":", 1)[0]
        if prefix not in namespaces:
            errors.append(f"undeclared namespace {prefix} for {name}")
    for source, relation, target in edges:
        for name, role in ((source, "source"), (target, "target")):
            if name not in keys:
                errors.append(f"undeclared {role} {name} on {relation}")
        if relation == "proposes" and keys.get(source, ("", ""))[0] != "gap":
            errors.append(f"proposes must originate from a gap key, not {source}")
    return errors


def render_additions(missing_keys, missing_edges):
    lines = ["", "(* ELIZA-µ semantic bindings, installed by tools/install_question_bindings.py.",
             "   Keys are identities; edges carry the typed relationships. A gap key holds",
             "   its concrete identity and its CFPC gap type separately, and only a specific",
             "   gap may propose a question. *)"]
    for prefix in EXPECTED_NAMESPACES:
        lines.append(f"namespace {prefix}:core domain custom;")
    for name, kind, value in missing_keys:
        lines.append(f'key {name} kind {kind} value "{value}";')
    for source, relation, target in missing_edges:
        lines.append(f"edge {source} -> {target} type {relation};")
    return "\n".join(lines) + "\n"


def install(path):
    original = path.read_text(encoding="utf-8")
    keys, edges, namespaces, _ = parse(original)

    text, renamed = apply_renames(original)
    text, temporal_updated = apply_temporal_candidate_contract(text)
    keys, edges, namespaces, _ = parse(text)

    missing_namespaces = [p for p in EXPECTED_NAMESPACES if p not in namespaces]
    missing_keys = [row for row in EXPECTED_KEYS if row[0] not in keys]
    missing_edges = [row for row in EXPECTED_EDGES if row not in edges]

    if missing_namespaces or missing_keys or missing_edges:
        # Namespace lines are emitted with the block only when something else is missing.
        text = text.rstrip("\n") + "\n" + render_additions(missing_keys, missing_edges)

    errors = validate(text)
    if errors:
        raise SystemExit(f"{path.name}: refusing to write: {errors}")

    if text == original:
        return path.name, 0, 0, 0, False

    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".kgf.tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return path.name, renamed + temporal_updated, len(missing_keys), len(missing_edges), True


def main() -> int:
    for path in KGF_FILES:
        name, updated, added_keys, added_edges, changed = install(path)
        where = path.parent.name
        if changed:
            print(f"{name} ({where}): {updated} declarations updated, "
                  f"{added_keys} key(s) added, {added_edges} edge(s) added")
        else:
            print(f"{name} ({where}): already installed, no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
