"""Create and validate SQLite tables from kuhul.jrom.table-manifest.v1.

Reads jrom.tables.json to discover all table manifests, then generates DDL from
khanary.tables.v1 and kuhul.key-tables.v1 definitions.

Usage:
  python tools/sql-tables.py --ddl                 # print DDL to stdout
  python tools/sql-tables.py --create              # create tables in .kuhul-data/tables.kdb
  python tools/sql-tables.py --validate            # validate all referenced manifests
  python tools/sql-tables.py --create --db path    # use a specific SQLite file
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "vendor" / "key-grammar-kit" / "data" / "host" / "manifests" / "jrom.tables.json"
DEFAULT_DB = ROOT / ".kuhul-data" / "khanary.db"

_SUPPORTED_SCHEMAS = {
    "khanary.tables.v1",
    "kuhul.key-tables.v1",
    "kuhul.jrom.table-manifest.v1",
}

_TYPE_MAP: dict[str, str] = {
    "uuid":      "TEXT",
    "string":    "TEXT",
    "text":      "TEXT",
    "number":    "REAL",
    "integer":   "INTEGER",
    "int":       "INTEGER",
    "float":     "REAL",
    "bool":      "INTEGER",
    "boolean":   "INTEGER",
    "timestamp": "TEXT",
    "json":      "TEXT",
    "enum":      "TEXT",
}


def _pk_col(primary_key: object) -> str | None:
    return primary_key if isinstance(primary_key, str) else None


def _ddl_from_khanary(table_id: str, table_def: dict) -> str | None:
    """DDL for a single khanary.tables.v1 table."""
    fields = table_def.get("fields")
    if not isinstance(fields, dict):
        return None
    primary_key = table_def.get("primary_key")
    pk_col = _pk_col(primary_key)
    lines: list[str] = []
    for col_name, col_def in fields.items():
        if not isinstance(col_def, dict):
            continue
        field_type = col_def.get("type", "string")
        structural = col_def.get("structural") or {}
        sql_type = _TYPE_MAP.get(str(field_type).lower(), "TEXT")
        parts = [f"    {col_name} {sql_type}"]
        if col_name == pk_col:
            parts.append("PRIMARY KEY")
        if col_def.get("required") and not structural.get("nullable"):
            parts.append("NOT NULL")
        lines.append(" ".join(parts))
    if isinstance(primary_key, list):
        lines.append(f"    PRIMARY KEY ({', '.join(primary_key)})")
    if not lines:
        return None
    cols = ",\n".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {table_id} (\n{cols}\n);"


def _ddl_from_inline(entry: dict) -> str | None:
    """DDL for a kuhul.key-tables.v1 table with schema_inline."""
    schema = entry.get("schema_inline")
    if not isinstance(schema, dict):
        return None
    table_id = entry.get("table_id")
    if not table_id:
        return None
    lines: list[str] = []
    for col_name, col_def in schema.items():
        if not isinstance(col_def, dict):
            continue
        field_type = col_def.get("type", "text")
        sql_type = _TYPE_MAP.get(str(field_type).lower(), "TEXT")
        parts = [f"    {col_name} {sql_type}"]
        if col_def.get("primary_key"):
            parts.append("PRIMARY KEY")
        if col_def.get("required"):
            parts.append("NOT NULL")
        lines.append(" ".join(parts))
    if not lines:
        return None
    cols = ",\n".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {table_id} (\n{cols}\n);"


def collect_ddl(jrom_manifest: dict, root: Path) -> list[tuple[str, str]]:
    """Return list of (table_id, ddl_statement) from all referenced manifests."""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for ref in jrom_manifest.get("manifests") or []:
        path = root / ref["path"]
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        schema = data.get("schema") or data.get("$schema_version", "")

        if schema == "khanary.tables.v1":
            for section in ("tables", "ngram_records"):
                for table_id, table_def in (data.get(section) or {}).items():
                    if table_id in seen or not isinstance(table_def, dict):
                        continue
                    ddl = _ddl_from_khanary(table_id, table_def)
                    if ddl:
                        seen.add(table_id)
                        results.append((table_id, ddl))

        elif schema == "kuhul.key-tables.v1":
            for _key_id, entry in (data.get("tables") or {}).items():
                if not isinstance(entry, dict):
                    continue
                table_id = entry.get("table_id", "")
                if table_id in seen:
                    continue
                ddl = _ddl_from_inline(entry)
                if ddl:
                    seen.add(table_id)
                    results.append((table_id, ddl))

    return results


def validate_manifests(jrom_manifest: dict, root: Path) -> bool:
    ok = True
    for ref in jrom_manifest.get("manifests") or []:
        path = root / ref["path"]
        if not path.exists():
            print(f"MISSING  {ref['path']}")
            ok = False
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            schema = data.get("schema") or data.get("$schema_version", "")
            if schema not in _SUPPORTED_SCHEMAS:
                print(f"UNKNOWN  {ref['path']}  schema={schema!r}")
                ok = False
            else:
                print(f"OK       {ref['path']}  schema={schema}")
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR    {ref['path']}: {exc}")
            ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help="Path to jrom.tables.json (default: vendor/.../jrom.tables.json)")
    parser.add_argument("--ddl", action="store_true",
                        help="Print generated DDL to stdout")
    parser.add_argument("--create", action="store_true",
                        help="Create tables in the SQLite database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="SQLite database path for --create")
    parser.add_argument("--validate", action="store_true",
                        help="Validate all referenced table manifests")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"manifest not found: {args.manifest}")
        return 1

    try:
        jrom_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to load manifest: {exc}")
        return 1

    if jrom_manifest.get("schema") != "kuhul.jrom.table-manifest.v1":
        print(f"unsupported manifest schema: {jrom_manifest.get('schema')!r}")
        return 1

    # Manifest paths in jrom.tables.json are relative to the repo root.
    # ROOT is derived from this script's location (tools/sql-tables.py → repo root).
    root = ROOT

    if args.validate:
        return 0 if validate_manifests(jrom_manifest, root) else 1

    statements = collect_ddl(jrom_manifest, root)
    if not statements:
        print("no DDL generated — check manifests exist and have field definitions")
        return 0

    if args.ddl:
        for table_id, stmt in statements:
            print(f"-- {table_id}")
            print(stmt)
            print()

    if args.create:
        args.db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(args.db))
        try:
            created = 0
            for table_id, stmt in statements:
                conn.execute(stmt)
                created += 1
            conn.commit()
            print(f"created/verified {created} table(s) in {args.db}")
        finally:
            conn.close()

    if not args.ddl and not args.create:
        print(f"found {len(statements)} table(s) — use --ddl to print DDL or --create to build the database")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
