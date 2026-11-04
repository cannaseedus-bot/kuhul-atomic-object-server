#!/usr/bin/env python3
"""Package one neighborhood.jsonl field as a framed KSO1 data-only object."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

try:
    from bson import BSON
except ImportError as exc:
    raise SystemExit("PyMongo is required: python -m pip install -r requirements.txt") from exc

MAGIC = b"KSO1"


def lane_graph(glyph: str, field: dict) -> dict:
    pending = {glyph: {"lane": glyph, "level": 0, "vector": {"ref": "vector." + glyph[1:].lower(), "view": "semantic"}, "fields": {},
                       "fold": {"phase": "Pop", "state": "pending", "bindings": {}, "evidence": [], "result": None}}}
    role_fields = field.get("fields", {})
    for role, item in role_fields.items():
        target = item.get("symbol")
        if not isinstance(target, str) or not target.startswith("⟁"):
            raise ValueError(f"field {role} has invalid lane symbol")
        # A field whose target is its owner is identity metadata, not a traversal edge.
        if target == glyph:
            continue
        pending[glyph]["fields"][role] = {"lane": target, "fold": {"phase": "Pop", "state": "pending", "bindings": {}, "evidence": [], "result": None}}

    for key, level in field.get("levels", {}).items():
        target = level.get("symbol") if isinstance(level, dict) else None
        if not isinstance(target, str) or not target.startswith("⟁"):
            raise ValueError(f"level {key} has invalid glyph symbol")
        pending.setdefault(target, {"lane": target, "level": int(key), "vector": {"ref": "vector." + target[1:].lower(), "view": "semantic"},
                                    "fields": {}, "fold": {"phase": "Pop", "state": "pending", "bindings": {}, "evidence": [], "result": None}})

    return {
        "entry": glyph,
        "laneContract": {"lane": "glyph_reference", "vector": {"ref": "semantic_vector_reference", "view": "semantic"}, "fields": {}, "fold": {"phase": "Pop", "state": "pending", "result": None}},
        "lanes": pending,
        "runtime": {"traversal": "recursive", "referenceMode": "shared_lane_registry", "cyclePolicy": "detect_active_path",
                    "revisitPolicy": "allow_after_return", "verification": "field_scoped", "commit": "child_before_parent",
                    "maxDepth": 64, "maxVisits": 4096, "execution": "explicit_admission_only"},
    }


def compile_record(record: dict) -> bytes:
    glyph = record.get("glyph")
    field = record.get("field")
    if not isinstance(glyph, str) or not re.fullmatch(r"⟁[A-Z0-9_]+", glyph):
        raise ValueError("record glyph is not canonical")
    if not isinstance(field, dict) or field.get("root") != glyph:
        raise ValueError("record field.root must match record glyph")
    semantic = {glyph: field}
    lanes = lane_graph(glyph, field)
    package = {
        "magic": "KSO1", "format": "kuhul.symbolic-object", "version": 1, "entry": glyph,
        "semantic": {"ref": f"semantic:{glyph}", "preserve": "lossless", "definition": "embedded", "levels": 10, "data": semantic},
        "lanes": {"ref": f"lanes:{glyph}", "preserve": "lossless", "definition": "embedded",
                   "representation": "recursive-vector-graph", "sharedReferences": True, "data": lanes},
        "xcfe": {"admission": "explicit", "verification": "field_scoped", "commit": "child_before_parent", "authority": "host"},
        "kernels": [], "compression": {"codec": "SCXQ2", "scope": "field_graph_chunks"},
    }
    doc = BSON.encode(package)
    return MAGIC + doc


def compile_neighborhood(records: list[dict], attention_ref: str) -> bytes:
    """Package the full JSONL source and link its potentially large vector sidecar."""
    if not records:
        raise ValueError("neighborhood contains no records")
    by_glyph: dict[str, list[dict]] = {}
    for index, record in enumerate(records, 1):
        glyph = record.get("glyph")
        if not isinstance(glyph, str) or not re.fullmatch(r"⟁[A-Z0-9_]+", glyph):
            raise ValueError(f"record {index} has a non-canonical glyph")
        field = record.get("field")
        if not isinstance(field, dict) or field.get("root") != glyph:
            raise ValueError(f"record {index} field.root must match {glyph}")
        by_glyph.setdefault(glyph, []).append(record)

    root = "⟁NEIGHBORHOOD"
    registry = {
        root: {"lane": root, "level": 0, "vector": {"ref": "vector.neighborhood", "view": "semantic"},
              "fields": {}, "fold": {"phase": "Pop", "state": "pending", "bindings": {}, "evidence": [], "result": None}}
    }
    for glyph in sorted(by_glyph):
        registry[root]["fields"][glyph[1:].lower()] = {
            "lane": glyph, "fold": {"phase": "Pop", "state": "pending", "bindings": {}, "evidence": [], "result": None}
        }
        registry[glyph] = {"lane": glyph, "level": 1, "vector": {"ref": "vector." + glyph[1:].lower(), "view": "semantic"},
                           "fields": {}, "fold": {"phase": "Pop", "state": "pending", "bindings": {}, "evidence": [], "result": None}}

    record_indexes: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        record_indexes.setdefault(record["glyph"], []).append(index)
    package = {
        "magic": "KSO1", "format": "kuhul.symbolic-object", "version": 1, "entry": root,
        "semantic": {"ref": "semantic:neighborhood", "preserve": "lossless", "definition": "embedded",
                     "levels": 10, "data": {"records": records, "byGlyph": record_indexes,
                                               "byGlyphIndexSemantics": "zero-based indices into records; preserves repeated candidate snapshots"}},
        "lanes": {"ref": "lanes:neighborhood", "preserve": "lossless", "definition": "embedded",
                  "representation": "recursive-vector-graph", "sharedReferences": True,
                  "data": {"entry": root, "laneContract": {"lane": "glyph_reference", "fold": {"phase": "Pop", "state": "pending"}},
                           "lanes": registry, "runtime": {"traversal": "recursive", "referenceMode": "shared_lane_registry",
                           "cyclePolicy": "detect_active_path", "revisitPolicy": "allow_after_return", "execution": "explicit_admission_only"}}},
        "attention": {"schema": "kuhul.neighborhood.attention.v1", "provider": "ollama", "model": "embeddinggemma:latest",
                      "definition": "external", "externalUri": attention_ref,
                      "status": "candidate_relevance_only", "note": "Vectors and per-question rankings are stored in the JSONL sidecar."},
        "xcfe": {"admission": "explicit", "verification": "field_scoped", "commit": "child_before_parent", "authority": "host"},
        "kernels": [], "compression": {"codec": "SCXQ2", "scope": "field_graph_chunks"},
    }
    document = BSON.encode(package)
    return MAGIC + document


def type_attention_pool(path: Path) -> None:
    """Attach K'UHUL-π typed addresses to generated query and relation vectors."""
    if not path.is_file():
        raise ValueError(f"attention pool not found: {path}; run neighborhood_attention.py first")
    temporary = path.with_suffix(path.suffix + ".typed.tmp")
    with path.open("r", encoding="utf-8") as source, temporary.open("w", encoding="utf-8", newline="\n") as output:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            glyph = str(row.get("glyph") or "UNKNOWN")
            row["sourceRecordIndex"] = line_no - 1
            row["vectorStorage"] = {"dtype": "float64_json", "decimalPlaces": 6,
                                     "note": "attention scores were computed from full-precision Ollama vectors before storage rounding"}
            snapshot = str(row["sourceRecordIndex"])
            row.setdefault("foldKey", {"type": "fold_key", "key": f"FOLD:FIELD:{glyph}:R{snapshot}", "family": "field_attention"})
            for question_index, question in enumerate(row.get("questions", [])):
                question_id = str(question.get("id") or "question")
                question.setdefault("queryKey", {"type": "query_key", "key": f"QUERY:{glyph}:R{snapshot}:Q{question_index}:{question_id}"})
                question.setdefault("thoughtKey", {"type": "thought_key", "key": f"THOUGHT:{glyph}:R{snapshot}:Q{question_index}:{question_id}"})
                for candidate in question.get("candidates", []):
                    target = str(candidate.get("glyph") or "UNKNOWN")
                    candidate.setdefault("key", {"type": "glyph_key", "key": target})
                    candidate.setdefault("relationKey", {"type": "relation_key", "key": f"RELATION:{glyph}:{target}:R{snapshot}"})
                if isinstance(question.get("queryEmbedding"), list):
                    question["queryEmbedding"] = [round(value, 6) for value in question["queryEmbedding"]]
                if isinstance(question.get("weightedValueContext"), list):
                    question["weightedValueContext"] = [round(value, 6) for value in question["weightedValueContext"]]
            for candidate in row.get("candidateEmbeddings", []):
                for name in ("keyEmbedding", "valueEmbedding"):
                    if isinstance(candidate.get(name), list):
                        candidate[name] = [round(value, 6) for value in candidate[name]]
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", type=Path, default=Path("neighborhood.jsonl"))
    cli.add_argument("--entry", help="glyph or word to package")
    cli.add_argument("--all", action="store_true", help="package every JSONL record as one neighborhood field")
    cli.add_argument("--attention", type=Path, default=Path("neighborhood.attention.jsonl"), help="external attention-vector JSONL referenced by --all")
    cli.add_argument("--output", type=Path, default=Path("field.kso"))
    args = cli.parse_args()
    if not args.all and not args.entry:
        cli.error("provide --entry or --all")
    requested = args.entry if args.entry and args.entry.startswith("⟁") else "⟁" + re.sub(r"[^A-Za-z0-9]+", "_", args.entry or "").strip("_").upper()
    try:
        selected = None
        records = []
        with args.input.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{args.input}:{line_no}: invalid JSONL: {exc}") from exc
                if row.get("glyph") == requested:
                    selected = row
                records.append(row)
        if args.all:
            if args.attention.resolve().parent != args.output.resolve().parent:
                raise ValueError("--attention must be stored beside --output so the KSO relative reference stays package-local")
            type_attention_pool(args.attention)
            attention_ref = args.attention.name
            binary = compile_neighborhood(records, attention_ref)
        elif selected is None:
            raise ValueError(f"neighborhood record not found: {requested}")
        else:
            binary = compile_record(selected)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(binary)
    except (OSError, ValueError) as exc:
        print(f"KSO1 build failed: {exc}", file=sys.stderr)
        return 1
    display_glyph = requested.encode("ascii", "backslashreplace").decode("ascii")
    label = f"{len(records)} neighborhood records" if args.all else display_glyph
    print(f"Wrote {args.output} ({len(binary)} bytes): {label}; DATA_ONLY, execution not authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
