#!/usr/bin/env python3
"""Generate or embed a KGF semantic-field bundle as candidate field data.

The optional Qwen pass generates all field arrays in one Ollama request with
thinking disabled. Embedding is then a single batch request to Ollama or one
batched llama-cpp-python call. Neither stage edits the source manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib import error, request

from semantic_fields import SemanticFieldBook, SemanticFieldError, cosine_similarity


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "vendor/key-grammar-kit/data/manifest/semantic-fields.manifest.json"
DEFAULT_GGUF = Path(r"C:\Users\canna\.lmstudio\models\lmstudio-community\gemma-3-1B-it-QAT-GGUF\gemma-3-1B-it-QAT-Q4_0.gguf")
DEFAULT_GEOMETRY_INDEX = ROOT / ".micronaut/checkpoints/neighborhood-attention.safetensors.index.json"


class DistillError(RuntimeError):
    pass


def _http_json(url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DistillError(f"Ollama request failed at {url}: {exc}") from exc
    if not isinstance(result, dict):
        raise DistillError(f"Ollama returned a non-object response from {url}")
    return result


def _ollama_model_ids(endpoint: str, timeout: float) -> set[str]:
    """Use `ollama list` as the user's local model inventory, with API fallback."""
    try:
        proc = subprocess.run(["ollama", "list"], text=True, encoding="utf-8", errors="replace",
                              capture_output=True, timeout=min(timeout, 20), check=False)
        if proc.returncode == 0:
            ids = set()
            for line in proc.stdout.splitlines()[1:]:
                parts = line.split()
                if parts:
                    ids.add(parts[0])
            return ids
    except (OSError, subprocess.TimeoutExpired):
        pass
    response = _http_json(endpoint.rstrip("/") + "/api/tags", None, timeout)
    models = response.get("models", [])
    return {m["name"] for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)}


def _require_ollama_model(model: str, endpoint: str, timeout: float) -> None:
    models = _ollama_model_ids(endpoint, timeout)
    if model not in models:
        options = ", ".join(sorted(models)) or "<none found>"
        raise DistillError(f"Ollama model {model!r} is not in `ollama list`; available: {options}")


def _generate_semantic_fields(concept: str, endpoint: str, model: str, timeout: float,
                              field_count: int, keys_per_field: int) -> SemanticFieldBook:
    _require_ollama_model(model, endpoint, timeout)
    root_key = "⟁" + re.sub(r"[^A-Z0-9]+", "_", concept.upper()).strip("_")
    prompt = f"""Create a useful KGF semantic field bundle for the concept {concept!r}.
Return ONLY JSON with exactly this shape:
{{"schema":"kgf.semantic-fields/2","fields":{{"⟁FIELD_KEY":["⟁KEY", ...]}},"relations":{{"⟁FIELD_KEY":{{"⟁KEY":"snake_case_relation"}}}}}}
Create exactly {field_count} distinct, overlapping semantic field arrays, each with exactly {keys_per_field} unique related keys. Include the root key {root_key} as a field. Use concrete everyday concepts like CAR, COMBUSTION, GASOLINE, ELECTRIC, ENGINE, PETROLEUM, and BATTERY when relevant. Every key must be a stable glyph key matching ⟁ followed by uppercase ASCII letters, digits, or underscores. Keep each array as an array of keys. Add relation labels only for meaningful links and only for keys present in that field's array. Relations are descriptive labels, not authority. Do not add prose, explanations, markdown, vectors, or weights."""
    response = _http_json(endpoint.rstrip("/") + "/api/chat", {
        "model": model,
        "messages": [
            {"role": "system", "content": "Produce concise structured semantic data. Do not expose reasoning."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }, timeout)
    message = response.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise DistillError("Qwen response had no message.content JSON")
    try:
        document = json.loads(content)
        book = SemanticFieldBook.from_document(document, hashlib.sha256(content.encode("utf-8")).hexdigest())
        if len(book.fields) != field_count:
            raise SemanticFieldError(f"expected {field_count} field arrays, received {len(book.fields)}")
        wrong_sizes = [f"{key}={len(members)}" for key, members in book.fields.items() if len(members) != keys_per_field]
        if wrong_sizes:
            raise SemanticFieldError(f"each field needs exactly {keys_per_field} unique members: " + ", ".join(wrong_sizes))
        if root_key not in book.fields:
            raise SemanticFieldError(f"generated fields omit required root field {root_key}")
        return book
    except (json.JSONDecodeError, SemanticFieldError) as exc:
        raise DistillError(f"generated semantic-field bundle failed validation: {exc}") from exc


def _ollama_embeddings(texts: list[str], endpoint: str, model: str, timeout: float) -> list[list[float]]:
    _require_ollama_model(model, endpoint, timeout)
    response = _http_json(endpoint.rstrip("/") + "/api/embed", {
        "model": model, "input": texts, "truncate": False,
    }, timeout)
    vectors = response.get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise DistillError("Ollama embedding response count does not match input key count")
    return _validate_vectors(vectors)


def _gguf_embeddings(texts: list[str], model_path: Path, context: int) -> list[list[float]]:
    if not model_path.is_file():
        raise DistillError(f"GGUF model file not found: {model_path}")
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise DistillError("GGUF embeddings require llama-cpp-python (Llama(..., embedding=True))") from exc
    try:
        llm = Llama(model_path=str(model_path), n_ctx=context, embedding=True, verbose=False)
        raw = llm.embed(texts, normalize=True, truncate=False)
        llm.close()
    except Exception as exc:
        raise DistillError(f"GGUF model could not produce embeddings: {exc}") from exc
    if isinstance(raw, dict):
        raw = raw.get("data")
        if isinstance(raw, list):
            raw = [row.get("embedding") if isinstance(row, dict) else row for row in raw]
    return _validate_vectors(raw)


def _validate_vectors(value: Any) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise DistillError("embedding backend returned no vectors")
    vectors: list[list[float]] = []
    dimension = None
    for index, row in enumerate(value):
        if not isinstance(row, (list, tuple)) or not row:
            raise DistillError(f"embedding {index} is not a non-empty vector")
        try:
            vector = [float(x) for x in row]
        except (TypeError, ValueError) as exc:
            raise DistillError(f"embedding {index} contains a non-numeric value") from exc
        if not all(math.isfinite(x) for x in vector):
            raise DistillError(f"embedding {index} contains a non-finite value")
        if dimension is None:
            dimension = len(vector)
        if len(vector) != dimension:
            raise DistillError("embedding dimensions are inconsistent")
        vectors.append(vector)
    return vectors


def _candidate_document(book: SemanticFieldBook, vectors: list[list[float]], backend: str,
                        model: str, source_path: Path, top_k: int, minimum: float,
                        geometry: dict[str, Any] | None) -> dict[str, Any]:
    keys = list(book.keys)
    if len(keys) != len(vectors):
        raise DistillError("embedding count does not match unique semantic key count")
    vector_by_key = dict(zip(keys, vectors))
    neighbors = []
    for source in keys:
        scored = []
        for target in keys:
            if source == target:
                continue
            score = cosine_similarity(vector_by_key[source], vector_by_key[target])
            if score >= minimum:
                scored.append((score, target))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        for score, target in scored[:top_k]:
            neighbors.append({"source": source, "target": target, "cosine": round(score, 8), "status": "embedding_candidate"})
    source_bytes = source_path.read_bytes() if source_path.is_file() else b""
    return {
        "schema": "kuhul.semantic-field-embedding-candidates.v1",
        "source_schema": book.schema,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest() if source_bytes else book.sha256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "embedding": {"backend": backend, "model": model, "dimensions": len(vectors[0]), "normalization": "l2", "batch_count": 1,
                      "coordinate_space": f"{model}/{len(vectors[0])}",
                      "compatible_with_neighborhood_attention": bool(geometry and geometry.get("compatible")),
                      "geometry_checkpoint": geometry.get("path") if geometry else None},
        "authority": {"status": "candidate_only", "changes_source_fields": False, "changes_source_relations": False, "xcfe_admission": "separate"},
        "source_snapshot": {
            "fields": {field: list(members) for field, members in book.fields.items()},
            "relations": book.relations,
        },
        "keys": [{"key": key, "text": book.embedding_text(key), "vector": vector_by_key[key]} for key in keys],
        "similarity_candidates": neighbors,
        "declared_relations": [
            {"source": source, "target": target, "label": label}
            for source, targets in book.relations.items() for target, label in targets.items()
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="kgf.semantic-fields/2 JSON input")
    parser.add_argument("--concept", help="ask Qwen to generate one whole semantic field bundle (one request)")
    parser.add_argument("--output", type=Path, default=ROOT / "field/distilled/semantic-field-candidates.json")
    parser.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--generator-model", default="qwen3.5:4b")
    parser.add_argument("--embedding-backend", choices=("ollama", "gguf"), default="ollama")
    parser.add_argument("--embedding-model", default="embeddinggemma:latest", help="Ollama model ID or GGUF path (backend dependent)")
    parser.add_argument("--geometry-index", type=Path, default=DEFAULT_GEOMETRY_INDEX,
                        help="neighborhood-attention index used to enforce embedding model and dimension alignment")
    parser.add_argument("--allow-independent-geometry", action="store_true",
                        help="allow vectors from another model space; output will be marked incompatible with the checkpoint")
    parser.add_argument("--context", type=int, default=4096, help="GGUF embedding context size")
    parser.add_argument("--field-count", type=int, default=4)
    parser.add_argument("--keys-per-field", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--minimum-similarity", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    if args.timeout <= 0 or args.context <= 0 or args.field_count <= 0 or args.keys_per_field <= 0 or args.top_k < 0:
        parser.error("timeout, context, field-count, and keys-per-field must be positive; top-k must be non-negative")
    if not -1.0 <= args.minimum_similarity <= 1.0:
        parser.error("minimum-similarity must be between -1 and 1")
    try:
        if args.concept:
            book = _generate_semantic_fields(args.concept.strip(), args.ollama_endpoint, args.generator_model,
                                             args.timeout, args.field_count, args.keys_per_field)
            # Preserve the generated declaration beside vectors for review.
            args.source = args.output.with_suffix(".source.json")
            args.source.parent.mkdir(parents=True, exist_ok=True)
            args.source.write_text(json.dumps({"schema": book.schema,
                                               "fields": {k: list(v) for k, v in book.fields.items()},
                                               "relations": book.relations}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            book = SemanticFieldBook.load(args.source)

        texts = [book.embedding_text(key) for key in book.keys]
        if args.embedding_backend == "ollama":
            model = args.embedding_model
            vectors = _ollama_embeddings(texts, args.ollama_endpoint, model, args.timeout)
        else:
            model_path = Path(args.embedding_model) if args.embedding_model != "embeddinggemma:latest" else DEFAULT_GGUF
            model = str(model_path)
            vectors = _gguf_embeddings(texts, model_path, args.context)
        geometry = None
        if args.geometry_index.is_file():
            try:
                checkpoint = json.loads(args.geometry_index.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DistillError(f"cannot read embedding geometry index {args.geometry_index}: {exc}") from exc
            expected_model = checkpoint.get("embedding_model")
            expected_dimension = checkpoint.get("dimension")
            compatible = model == expected_model and len(vectors[0]) == expected_dimension
            geometry = {"path": str(args.geometry_index), "model": expected_model,
                        "dimension": expected_dimension, "compatible": compatible}
            if not compatible and not args.allow_independent_geometry:
                raise DistillError(
                    f"embedding geometry mismatch: generated {model}/{len(vectors[0])}; "
                    f"checkpoint requires {expected_model}/{expected_dimension}. "
                    "Use embeddinggemma:latest from `ollama list`, or pass --allow-independent-geometry "
                    "to keep a separate, explicitly incompatible vector space."
                )
        elif not args.allow_independent_geometry:
            raise DistillError(f"geometry index is missing: {args.geometry_index}; pass --allow-independent-geometry to proceed without checkpoint alignment")
        result = _candidate_document(book, vectors, args.embedding_backend, model, args.source,
                                     args.top_k, args.minimum_similarity, geometry)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    except (OSError, SemanticFieldError, DistillError, ValueError) as exc:
        print(f"field-distill failed: {exc}", file=sys.stderr)
        return 1
    print(f"Embedded {len(book.keys)} unique keys in one batch; wrote {args.output}")
    print(f"Backend: {result['embedding']['backend']} | model: {result['embedding']['model']} | dimensions: {result['embedding']['dimensions']}")
    print(f"Similarity candidates: {len(result['similarity_candidates'])}; declared fields and relations remain unchanged; no XCFE admission or execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
