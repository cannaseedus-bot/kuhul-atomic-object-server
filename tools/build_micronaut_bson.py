#!/usr/bin/env python3
"""Build a deterministic, DATA_ONLY BSON bundle of the local Micronaut runtime."""
from __future__ import annotations

import argparse
import hashlib
import gzip
import sys
import json
from pathlib import Path

try:
    from bson import BSON, Binary
except ImportError as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("PyMongo is required: python -m pip install pymongo") from exc


ROOT = Path(__file__).resolve().parents[1]
MAX_BSON_BYTES = 64 * 1024 * 1024
EXCLUDED_PARTS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "bin", "obj", "build"}
EXCLUDED_NAMES = {".asx_memory.json"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}
MICROPROGRAM_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".kuhul", ".h", ".hpp", ".cpp", ".hlsl", ".glsl", ".aiml", ".xaiml", ".wasm"}


def entry_type(path: Path) -> str:
    relative = path.as_posix().lower()
    if "/docs/" in relative or path.suffix.lower() in {".json", ".md", ".ebnf", ".toml", ".properties"}:
        return "metadata"
    if path.suffix.lower() in MICROPROGRAM_SUFFIXES:
        return "micro_program"
    return "runtime_resource"


def selected_paths(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for relative in ("micronaut", "field", "gguf-py/gguf", "mu-py", "bus", "bin/src", "vendor/key-grammar-kit/data/manifest", "vendor/key-grammar-kit/data/micronauts", "vendor/key-grammar-kit/data/programs", "vendor/key-grammar-kit/data/schema", "vendor/key-grammar-kit/data/tracks", "vendor/key-grammar-kit/data/cfpc", "vendor/key-grammar-kit/data/facts", "vendor/key-grammar-kit/tools"):
        base = root / relative
        if not base.is_dir():
            raise FileNotFoundError(f"required bundle directory is missing: {base}")
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            excluded_parts = EXCLUDED_PARTS - {"bin"} if relative == "bin/src" else EXCLUDED_PARTS
            if any(part in excluded_parts for part in rel.parts):
                continue
            if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            paths.add(path)

    # Runtime field and topology graphs live at the key-grammar data root. Keep
    # this inventory data-driven: new GML assets should enter the DATA_ONLY
    # bundle without needing a second hand-maintained filename list.
    data_root = root / "vendor/key-grammar-kit/data"
    for path in data_root.glob("*.gml"):
        if path.is_file():
            paths.add(path)

    # Versioned XAIML contracts are optional in older checkouts but, when the
    # directory is present, every file under it belongs in the DATA_ONLY bundle.
    xaiml_contracts = root / "vendor/key-grammar-kit/data/grammar/xaiml/v1"
    if xaiml_contracts.is_dir():
        for path in xaiml_contracts.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            paths.add(path)

    # MX2LM gram containers and vector projections are model-side data assets.
    # Include the full directory when present; bundle admission stays DATA_ONLY.
    mx2lm_data = root / "vendor/key-grammar-kit/data/mx2lm"
    if mx2lm_data.is_dir():
        for path in mx2lm_data.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            paths.add(path)

    standard_library = root / "vendor/key-grammar-kit/data/stdlib"
    if standard_library.is_dir():
        for path in standard_library.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            paths.add(path)

    for relative in (
        "manifest.json",
        "programs.md",
        "Micronaut.ps1",
        "mu-factory.py",
        "scraper_worker_bot.py",
        "micronaut.bat",
        "requirements.txt",
        "gguf-py/pyproject.toml",
        "gguf-py/README.md",
        "gguf-py/LICENSE",
        "tools/distill.py",
        "tools/neighborhood_attention.py",
        "tools/neighborhood_to_kso.py",
        "tools/kso_validate.py",
        "tools/build_micronaut_bson.py",
        "tools/install_question_bindings.py",
        "tools/validate-cfpc.py",
        "tools/check_xpath_kbnf_conformance.py",
        "tools/kuhul_feed_serializer.py",
        "tools/check_kuhul_feed_serializer.py",
        "examples/starter.kbnf",
        "examples/xpath-kbnf.conformance.json",
        "tools/grammar/syntax_compiler.py",
        "vendor/key-grammar-kit/tools/grammar/syntax_compiler.py",
        "vendor/key-grammar-kit/tools/grammar/mini_transpilers.py",
        "vendor/key-grammar-kit/keygraph_bootstrap.py",
        "vendor/key-grammar-kit/data/apps/daemon-bot.asx-app.json",
        "vendor/key-grammar-kit/data/apps/daemon-bot-knowledge.json",
        "vendor/key-grammar-kit/data/projection_abi_v1.json",
        "vendor/key-grammar-kit/data/mx2lm.vectors.meta.json",
        "vendor/key-grammar-kit/data/memory/memory-field.v1.json",
        "bin/rest_api.py",
        "bin/REST_API.md",
        "vendor/key-grammar-kit/data/alice/semantic-control-classes.aiml",
        "vendor/key-grammar-kit/data/alice/baseball-game-theory.aiml",
        "vendor/key-grammar-kit/data/alice/daemon-modes.aiml",
        "vendor/key-grammar-kit/data/alice/emotion.aiml",
        "vendor/key-grammar-kit/data/alice/fold-field-product-graph.aiml",
        "vendor/key-grammar-kit/data/alice/game-theory-puzzle-jokes.aiml",
        "vendor/key-grammar-kit/data/alice/greetings.aiml",
        "vendor/key-grammar-kit/data/alice/humor.aiml",
        "vendor/key-grammar-kit/data/alice/joke.aiml",
        "vendor/key-grammar-kit/data/alice/joke-harvest.aiml",
        "vendor/key-grammar-kit/data/alice/khanary-distilled.aiml",
        "vendor/key-grammar-kit/data/alice/kuhul-phases.aiml",
        "vendor/key-grammar-kit/data/alice/memory-u.aiml",
        "vendor/key-grammar-kit/data/alice/morphism-fixpoint-wcr-session.json",
        "vendor/key-grammar-kit/data/alice/morphisms-fixedpoints.aiml",
        "vendor/key-grammar-kit/data/alice/npc-grammar.aiml",
        "vendor/key-grammar-kit/data/alice/regex-fsm.aiml",
        "vendor/key-grammar-kit/data/alice/wildcard-grammar.aiml",
        "vendor/key-grammar-kit/data/alice/advisor.aiml",
        "vendor/key-grammar-kit/data/alice/alice.aiml",
        "vendor/key-grammar-kit/data/alice/ana-pi-fold.aiml",
        "vendor/key-grammar-kit/data/alice/atomic.aiml",
        "vendor/key-grammar-kit/data/alice/badanswer.aiml",
        "vendor/key-grammar-kit/data/alice/joke.aiml",
        "vendor/key-grammar-kit/data/grammar/joke-bootstrap.json",
        "vendor/key-grammar-kit/data/grammar/joke-bootstrap.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/css.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/micronaut-route-contracts.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/kuhul-question-engine.kgf",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational-graph.xml",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational.sdm.xml",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational.xsl",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational.xsl.fixtures.json",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational-3.0.xsl",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational-3.0.fixtures.json",
        "vendor/key-grammar-kit/data/grammar/aiml-functions.kgf",
        "vendor/key-grammar-kit/data/grammar/xaiml.xpath-function-lane.contracts.json",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational.sdm.css",
        "vendor/key-grammar-kit/advisor-bootstrap.key-grammar.jsonl",
        "vendor/key-grammar-kit/english-dictionary.definition-relations.key-grammar.jsonl",
        "vendor/key-grammar-kit/english-dictionary.key-grammar.meta.json",
        "vendor/key-grammar-kit/english-dictionary.lexicon.key-grammar.jsonl",
        "vendor/key-grammar-kit/greeting-bank.key-grammar.jsonl",
        "vendor/key-grammar-kit/micronaut-route-contracts.key-grammar.jsonl",
        "vendor/key-grammar-kit/kuhul-question-engine.kgf",
        "vendor/key-grammar-kit/npc-theory.key-grammar.jsonl",
        "vendor/key-grammar-kit/regex-fsm.key-grammar.jsonl",
        "vendor/key-grammar-kit/regex-kuhul.key-grammar.jsonl",
        "vendor/key-grammar-kit/script-pattern.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/english-dictionary.definition-relations.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/english-dictionary.lexicon.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/dataset.advisor_mu.key-grammar.candidates.jsonl",
        "vendor/key-grammar-kit/data/grammar/dataset.joke_mu.key-grammar.candidates.jsonl",
        "vendor/key-grammar-kit/data/grammar/dataset.key-grammar.candidates.jsonl",
        "vendor/key-grammar-kit/data/grammar/dataset.mx2lm.key-grammar.candidates.jsonl",
        "vendor/key-grammar-kit/data/grammar/dataset.plan_mu.key-grammar.candidates.jsonl",
        "vendor/key-grammar-kit/data/grammar/dataset.politics_mu.key-grammar.candidates.jsonl",
        "vendor/key-grammar-kit/data/grammar/joke-bootstrap.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/kuhul-relational.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/micronaut-program.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/micronaut-route-contracts.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/ngram-key-grammar.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/foldgraph-lineage.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/greeting-bank.key-grammar.jsonl",
        "vendor/key-grammar-kit/data/grammar/daemon-behavior-modes.v1.json",
        "vendor/key-grammar-kit/data/grammar/micronaut.runtime-grammar.ebnf",
        "vendor/key-grammar-kit/micronaut.runtime-grammar.ebnf",
        "vendor/key-grammar-kit/micronaut.runtime-grammar.v2.ebnf",
        "vendor/key-grammar-kit/data/grammar/SEMANTICS.md",
        "vendor/key-grammar-kit/data/grammar/scfml.normalization.json",
        "vendor/key-grammar-kit/data/grammar/scfml.runtime-grammar.ebnf",
        "vendor/key-grammar-kit/scfml.runtime-grammar.ebnf",
        "vendor/key-grammar-kit/data/micronaut_fieldgraph.gml",
        "vendor/key-grammar-kit/data/grammar/mml/v1/MicronautFieldGraph.mml",
        "vendor/key-grammar-kit/data/grammar/mml/v1/AliceStrategyAssets.mml",
    ):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"required bundle file is missing: {path}")
        paths.add(path)
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def build_document(root: Path) -> dict:
    entries = []
    digest_rows = []
    total_bytes = 0
    for path in selected_paths(root):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        total_bytes += len(data)
        digest_rows.append({"path": rel, "bytes": len(data), "sha256": sha256})
        stored_data = data
        entry = {
            "path": rel,
            "entryType": entry_type(path),
            "entryStatus": "candidate" if rel.startswith("micronaut/generated/candidates/") else "source",
            "mediaType": "application/json" if path.suffix.lower() == ".json" else "application/octet-stream",
            "bytes": len(data),
            "sha256": sha256,
        }
        if path.suffix.lower() in {".json", ".jsonl", ".gml"}:
            compressed = gzip.compress(data, compresslevel=9, mtime=0)
            if len(compressed) + 64 < len(data):
                stored_data = compressed
                entry["contentEncoding"] = "gzip"
                entry["storedBytes"] = len(stored_data)
        entry["content"] = Binary(stored_data)
        entries.append(entry)

    manifest_bytes = json.dumps(digest_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    registry_path = root / "micronaut/docs/micronaut.registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.is_file() else {"agents": []}
    rpc_path = root / "bus/rpc-api.json"
    rpc_bytes = rpc_path.read_bytes()
    rpc_api = json.loads(rpc_bytes)
    if rpc_api.get("schema") != "kuhul.micronaut.rpc-api.v1" or not isinstance(rpc_api.get("ports"), dict):
        raise ValueError("bus/rpc-api.json has an invalid schema or missing ports")
    programs = [entry["path"] for entry in entries if entry["entryType"] == "micro_program"]
    return {
        "format": "kuhul.micronaut-bundle",
        "version": 1,
        "status": "DATA_ONLY",
        "executionAdmission": "explicit_host_xcfe",
        "bundleSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "sourceRoots": ["micronaut/", "field/", "gguf-py/gguf/", "gguf-py/pyproject.toml", "gguf-py/README.md", "gguf-py/LICENSE", "mu-py/", "bus/", "bin/src/", "manifest.json", "kuhul.xjson.json", "programs.md", "Micronaut.ps1", "mu-factory.py", "scraper_worker_bot.py", "micronaut.bat", "requirements.txt", "tools/distill.py", "tools/neighborhood_attention.py", "tools/neighborhood_to_kso.py", "tools/kso_validate.py", "tools/build_micronaut_bson.py", "tools/install_question_bindings.py", "tools/validate-cfpc.py", "tools/check_xpath_kbnf_conformance.py", "tools/kuhul_feed_serializer.py", "tools/check_kuhul_feed_serializer.py", "examples/starter.kbnf", "examples/xpath-kbnf.conformance.json", "bin/rest_api.py", "bin/REST_API.md", "vendor/key-grammar-kit/tools/", "vendor/key-grammar-kit/keygraph_bootstrap.py", "vendor/key-grammar-kit/data/manifest/", "vendor/key-grammar-kit/data/micronauts/", "vendor/key-grammar-kit/data/programs/", "vendor/key-grammar-kit/data/schema/", "vendor/key-grammar-kit/data/tracks/", "vendor/key-grammar-kit/data/cfpc/", "vendor/key-grammar-kit/data/facts/", "vendor/key-grammar-kit/data/apps/daemon-bot.asx-app.json", "vendor/key-grammar-kit/data/apps/daemon-bot-knowledge.json", "vendor/key-grammar-kit/data/projection_abi_v1.json", "vendor/key-grammar-kit/data/mx2lm.vectors.meta.json", "vendor/key-grammar-kit/data/memory/memory-field.v1.json", "vendor/key-grammar-kit/data/mx2lm/", "vendor/key-grammar-kit/data/stdlib/", "vendor/key-grammar-kit/data/alice/", "vendor/key-grammar-kit/advisor-bootstrap.key-grammar.jsonl", "vendor/key-grammar-kit/english-dictionary.definition-relations.key-grammar.jsonl", "vendor/key-grammar-kit/english-dictionary.key-grammar.meta.json", "vendor/key-grammar-kit/english-dictionary.lexicon.key-grammar.jsonl", "vendor/key-grammar-kit/greeting-bank.key-grammar.jsonl", "vendor/key-grammar-kit/micronaut.runtime-grammar.ebnf", "vendor/key-grammar-kit/micronaut.runtime-grammar.v2.ebnf", "vendor/key-grammar-kit/micronaut-route-contracts.key-grammar.jsonl", "vendor/key-grammar-kit/npc-theory.key-grammar.jsonl", "vendor/key-grammar-kit/regex-fsm.key-grammar.jsonl", "vendor/key-grammar-kit/script-pattern.key-grammar.jsonl", "vendor/key-grammar-kit/data/grammar/", "vendor/key-grammar-kit/data/grammar/xaiml/v1/", "vendor/key-grammar-kit/data/grammar/micronaut.runtime-grammar.ebnf", "vendor/key-grammar-kit/data/grammar/daemon-behavior-modes.v1.json", "vendor/key-grammar-kit/data/*.gml", "vendor/key-grammar-kit/data/grammar/mml/v1/MicronautFieldGraph.mml", "vendor/key-grammar-kit/data/grammar/mml/v1/AliceStrategyAssets.mml", "vendor/key-grammar-kit/scfml.runtime-grammar.ebnf"],
        "entryCount": len(entries),
        "sourceBytes": total_bytes,
        "updateModel": {
            "owner": "runtime_factory",
            "candidateOnly": True,
            "candidatePath": "micronaut/generated/candidates/",
            "admission": "explicit_host_xcfe",
        },
        "micronautRegistry": {
            "source": "micronaut/docs/micronaut.registry.json",
            "agents": registry.get("agents", []),
            "microProgramPaths": programs,
        },
        "rpcApi": {
            "source": "bus/rpc-api.json",
            "schema": rpc_api["schema"],
            "version": rpc_api["version"],
            "ports": rpc_api["ports"],
        },
        "rpcApiSha256": hashlib.sha256(rpc_bytes).hexdigest(),
        "ggufIntegration": {
            "packageRoot": "gguf-py/gguf/",
            "metadataLoader": "gguf-py/gguf/metadata.py",
            "micronautAdapter": "gguf-py/gguf/micronaut.py",
            "writer": "gguf-py/gguf/gguf_writer.py",
            "reader": "gguf-py/gguf/gguf_reader.py",
            "keyDefinitions": "gguf-py/gguf/constants.py",
            "dependencyManifest": "gguf-py/pyproject.toml",
            "bundleScriptRunner": "mu-py/micronaut_adapter.py",
            "bundleScriptPrefix": "mu-py/",
            "role": "model_metadata_and_gguf_io",
            "weightsEmbedded": False,
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="K'UHUL project root")
    parser.add_argument("--output", type=Path, default=None, help="output BSON path (default: <root>/micronaut.bson)")
    parser.add_argument("--max-bytes", type=int, default=MAX_BSON_BYTES, help="maximum encoded BSON document size")
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or (root / "micronaut.bson")).resolve()
    try:
        document = build_document(root)
        encoded = BSON.encode(document)
        if len(encoded) > args.max_bytes:
            raise ValueError(f"encoded BSON is {len(encoded)} bytes, over limit {args.max_bytes}; bundle external payloads or raise the explicit limit")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded)
        decoded = BSON(encoded).decode()
        if decoded.get("bundleSha256") != document["bundleSha256"] or len(decoded.get("entries", [])) != document["entryCount"]:
            raise ValueError("post-write BSON round-trip did not preserve bundle metadata")
    except (OSError, ValueError) as exc:
        print(f"Micronaut BSON build failed: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {output}")
    print(f"Entries: {document['entryCount']} | source bytes: {document['sourceBytes']} | BSON bytes: {len(encoded)}")
    print(f"Bundle SHA-256: {document['bundleSha256']}")
    print("Status: DATA_ONLY; execution admission remains host-controlled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
