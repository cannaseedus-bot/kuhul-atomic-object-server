#!/usr/bin/env python3
"""Validate KSO1 framing and structural references; never authorizes execution."""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

try:
    from bson import BSON
except ImportError as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("PyMongo is required: python -m pip install pymongo") from exc

MAGIC = b"KSO1"
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
CRITICAL_KEYS = {"magic", "version", "entry", "semantic", "lanes", "xcfe", "kernels", "compression", "attention"}


class KSOError(ValueError):
    pass


def _resolve_json(base: Path, uri: str) -> Any:
    if "://" in uri or uri.startswith("file:"):
        raise KSOError(f"unsupported external reference URI: {uri}")
    path = (base / uri).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as exc:
        raise KSOError(f"external reference escapes package directory: {uri}") from exc
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KSOError(f"missing external definition: {path}") from exc
    except json.JSONDecodeError as exc:
        raise KSOError(f"invalid external JSON {path}: {exc}") from exc


def _resolve_external_path(base: Path, uri: str, label: str) -> Path:
    if not isinstance(uri, str) or not uri or "://" in uri or uri.startswith("file:"):
        raise KSOError(f"{label}.externalUri must be a local relative path")
    path = (base / uri).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as exc:
        raise KSOError(f"{label}.externalUri escapes package directory: {uri}") from exc
    if not path.is_file():
        raise KSOError(f"missing external {label} payload: {path}")
    return path


def _check_duplicate_critical_keys(data: bytes) -> None:
    """Scan BSON element boundaries so duplicate root contract keys aren't lost by dict decoding."""
    if len(data) < 5:
        raise KSOError("BSON document is too short")
    declared = struct.unpack_from("<i", data, 0)[0]
    if declared != len(data) or data[-1] != 0:
        raise KSOError("invalid BSON document boundary")
    offset = 4
    seen: set[str] = set()

    def cstring(pos: int) -> tuple[str, int]:
        end = data.find(b"\0", pos)
        if end < 0:
            raise KSOError("unterminated BSON cstring")
        try:
            return data[pos:end].decode("utf-8"), end + 1
        except UnicodeDecodeError as exc:
            raise KSOError("invalid UTF-8 BSON key") from exc

    while offset < len(data) - 1:
        kind = data[offset]
        offset += 1
        key, offset = cstring(offset)
        if key in CRITICAL_KEYS:
            if key in seen:
                raise KSOError(f"duplicate critical BSON key: {key}")
            seen.add(key)
        if kind == 0x01: offset += 8
        elif kind in (0x02, 0x0D, 0x0E):
            n = struct.unpack_from("<i", data, offset)[0]; offset += 4 + n
        elif kind in (0x03, 0x04):
            n = struct.unpack_from("<i", data, offset)[0]; offset += n
        elif kind == 0x05:
            n = struct.unpack_from("<i", data, offset)[0]; offset += 5 + n
        elif kind in (0x06, 0x0A, 0x7F, 0xFF): pass
        elif kind == 0x07: offset += 12
        elif kind == 0x08: offset += 1
        elif kind in (0x09, 0x11, 0x12): offset += 8
        elif kind == 0x0B:
            _, offset = cstring(offset); _, offset = cstring(offset)
        elif kind == 0x0C:
            n = struct.unpack_from("<i", data, offset)[0]; offset += 4 + n + 12
        elif kind == 0x0F:
            n = struct.unpack_from("<i", data, offset)[0]; offset += n
        elif kind == 0x10: offset += 4
        elif kind == 0x13: offset += 16
        else: raise KSOError(f"unsupported or invalid BSON element type: 0x{kind:02x}")
        if offset > len(data) - 1:
            raise KSOError("BSON element extends past document boundary")
    if offset != len(data) - 1:
        raise KSOError("invalid BSON element termination")


def _load_definition(base: Path, record: dict[str, Any], label: str) -> dict[str, Any]:
    mode = record.get("definition")
    if mode == "embedded":
        payload = record.get("data")
        if not isinstance(payload, dict):
            raise KSOError(f"{label}.data must be a document for embedded definitions")
    elif mode == "external":
        uri = record.get("externalUri")
        if not isinstance(uri, str) or not uri:
            raise KSOError(f"{label}.externalUri is required for external definitions")
        payload = _resolve_json(base, uri)
    else:
        raise KSOError(f"{label}.definition must be 'embedded' or 'external'")
    if not isinstance(payload, dict):
        raise KSOError(f"{label} definition must resolve to a JSON object")
    return payload


def _validate_lanes(package: dict[str, Any], lane_doc: dict[str, Any]) -> None:
    lanes_record = package["lanes"]
    if lanes_record.get("representation") != "recursive-vector-graph":
        raise KSOError("lanes.representation must be recursive-vector-graph")
    registry = lane_doc.get("lanes")
    if not isinstance(registry, dict) or not registry:
        raise KSOError("lane definition must contain a non-empty lanes registry")
    entry = package["entry"]
    if entry not in registry:
        raise KSOError(f"entry lane is absent from lane registry: {entry}")

    # References point to canonical registry definitions. Shared targets are retained once.
    for name, lane in registry.items():
        if not isinstance(lane, dict):
            raise KSOError(f"lane {name} must be an object")
        if lane.get("lane") != name:
            raise KSOError(f"lane registry key/value mismatch for {name}")
        fields = lane.get("fields", {})
        if not isinstance(fields, dict):
            raise KSOError(f"lane {name}.fields must be an object")
        for field_name, field in fields.items():
            target = field.get("lane") if isinstance(field, dict) else None
            if target not in registry:
                raise KSOError(f"lane {name} field {field_name} references missing lane {target}")

    # Reject active-path cycles, but permit revisiting a completed shared node.
    active: set[str] = set()
    complete: set[str] = set()

    def visit(name: str, depth: int = 0) -> None:
        if depth > 4096:
            raise KSOError("lane graph exceeds maximum validation depth (4096)")
        if name in active:
            raise KSOError(f"active-path cycle detected at {name}")
        if name in complete:
            return
        active.add(name)
        for field in registry[name].get("fields", {}).values():
            visit(field["lane"], depth + 1)
        active.remove(name)
        complete.add(name)

    visit(entry)


def load_kso(path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    if max_bytes < 9:
        raise KSOError("maximum package size must be at least 9 bytes")
    size = path.stat().st_size
    if size > max_bytes:
        raise KSOError(f"package exceeds configured size limit ({size} > {max_bytes})")
    if size < 9:
        raise KSOError("package is shorter than the KSO1 header and minimum BSON document")
    with path.open("rb") as stream:
        header = stream.read(4)
        if header != MAGIC:
            raise KSOError("invalid KSO1 file header")
        length_bytes = stream.read(4)
        if len(length_bytes) != 4:
            raise KSOError("truncated BSON length field")
        doc_length = struct.unpack("<i", length_bytes)[0]
        if doc_length < 5:
            raise KSOError(f"invalid BSON document length: {doc_length}")
        if doc_length > max_bytes - 4:
            raise KSOError(f"BSON document exceeds configured size limit ({doc_length} > {max_bytes - 4})")
        if doc_length + 4 != size:
            raise KSOError("BSON length does not end exactly at EOF (truncated data or trailing bytes)")
        bson_bytes = length_bytes + stream.read(doc_length - 4)
        if len(bson_bytes) != doc_length:
            raise KSOError("truncated BSON document")
        if stream.read(1):
            raise KSOError("unexpected trailing bytes after BSON document")
    _check_duplicate_critical_keys(bson_bytes)
    try:
        package = BSON(bson_bytes).decode()
    except Exception as exc:
        raise KSOError(f"malformed BSON document: {exc}") from exc
    if not isinstance(package, dict):
        raise KSOError("BSON root must be a document")
    if package.get("magic") != "KSO1":
        raise KSOError("BSON envelope magic must be KSO1")
    if package.get("version") != 1 or isinstance(package.get("version"), bool):
        raise KSOError(f"unsupported KSO version: {package.get('version')!r}")
    for key in ("entry", "semantic", "lanes", "xcfe", "kernels", "compression"):
        if key not in package:
            raise KSOError(f"missing required package field: {key}")
    if package["xcfe"].get("admission") != "explicit":
        raise KSOError("XCFE admission must remain explicit")

    base = path.resolve().parent
    semantic_doc = _load_definition(base, package["semantic"], "semantic")
    lane_doc = _load_definition(base, package["lanes"], "lanes")
    _validate_lanes(package, lane_doc)
    attention = package.get("attention")
    if attention is not None:
        if not isinstance(attention, dict) or attention.get("schema") != "kuhul.neighborhood.attention.v1":
            raise KSOError("attention.schema must be kuhul.neighborhood.attention.v1")
        if attention.get("definition") != "external" or attention.get("status") != "candidate_relevance_only":
            raise KSOError("attention must remain an external candidate-only payload")
        _resolve_external_path(base, attention.get("externalUri"), "attention")
    return {
        "status": "DATA_ONLY",
        "package": package,
        "resolved": {"semantic": semantic_doc, "lanes": lane_doc},
        "execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="KSO1 file to validate")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    try:
        loaded = load_kso(args.package, args.max_bytes)
    except (OSError, KSOError) as exc:
        print(f"KSO1 invalid: {exc}", file=sys.stderr)
        return 1
    entry = loaded["package"]["entry"].encode("ascii", "backslashreplace").decode("ascii")
    print(f"KSO1 valid: {entry} (DATA_ONLY; execution not authorized)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
