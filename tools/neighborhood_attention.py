#!/usr/bin/env python3
"""Embed neighborhood questions and score their field neighbors with attention.

Writes a separate JSONL sidecar. Scores are candidate relevance weights only;
they are not verification confidence, XCFE admission, or execution authority.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from micronaut.embed_client import EmbeddingError, embed  # noqa: E402
from micronaut.wcr import cosine, dot, softmax  # noqa: E402


class AttentionError(RuntimeError):
    pass


def candidate_texts(record: dict) -> list[dict]:
    field = record.get("field", {})
    levels = field.get("levels", {}) if isinstance(field, dict) else {}
    relations = field.get("relations", []) if isinstance(field, dict) else []
    relation_by_target = {}
    if isinstance(relations, list):
        for relation in relations:
            if isinstance(relation, dict) and isinstance(relation.get("object"), str):
                relation_by_target.setdefault(relation["object"], []).append(relation)
    candidates = []
    seen = set()
    for level_no in range(1, 9):
        level = levels.get(str(level_no), {}) if isinstance(levels, dict) else {}
        if not isinstance(level, dict):
            continue
        glyph = level.get("symbol")
        if not isinstance(glyph, str) or glyph in seen:
            continue
        seen.add(glyph)
        relation_items = relation_by_target.get(glyph, [])
        relation_text = "; ".join(
            " ".join(str(relation.get(key, "")) for key in ("subject", "predicate", "object", "type") if relation.get(key))
            for relation in relation_items
        )
        notation = level.get("notation", [])
        if not isinstance(notation, list):
            notation = [notation] if notation else []
        notation_text = "; ".join(str(item) for item in notation)
        role = str(level.get("role", ""))
        kind = str(level.get("kind", ""))
        label = glyph[1:].replace("_", " ").lower()
        key_text = f"Glyph {label}. Role {role}. Kind {kind}. Relation {relation_text}. Notation {notation_text}."
        value_text = f"{record.get('word', record.get('glyph', ''))}: {role} {kind}; {relation_text}; {notation_text}"
        candidates.append({"glyph": glyph, "label": label, "role": role, "kind": kind,
                           "relationText": relation_text, "notation": notation,
                           "keyText": key_text, "valueText": value_text})
    return candidates


def score_record(record: dict, backend: str, model: str, endpoint: str, timeout: float, temperature: float) -> dict | None:
    field = record.get("field", {})
    questions = field.get("reasoningQuestions", []) if isinstance(field, dict) else []
    if not questions:
        word = str(record.get("word") or record.get("glyph") or "this concept")
        glyph = str(record.get("glyph") or "")
        questions = [
            {"id": "identity", "targetGlyph": glyph, "question": f"What does {word} mean, and which field neighbor best identifies it?"},
            {"id": "relations", "targetGlyph": glyph, "question": f"How is {word} related to its semantic neighbors and their properties?"},
            {"id": "context", "targetGlyph": glyph, "question": f"Which context, dependency, or limitation matters when reasoning about {word}?"},
        ]
    candidates = candidate_texts(record)
    if not isinstance(questions, list) or not questions or not candidates:
        return None

    texts: list[str] = []
    positions: dict[str, int] = {}

    def register(text: str) -> int:
        if text not in positions:
            positions[text] = len(texts)
            texts.append(text)
        return positions[text]

    question_rows = []
    for question in questions:
        if not isinstance(question, dict) or not isinstance(question.get("question"), str):
            continue
        query_text = question["question"]
        query_index = register(query_text)
        for candidate in candidates:
            candidate["keyIndex"] = register(candidate["keyText"])
            candidate["valueIndex"] = register(candidate["valueText"])
        question_rows.append((question, query_index))
    if not question_rows:
        return None

    vectors = embed(texts, backend, model, endpoint, timeout)
    dimension = len(vectors[0])
    scale = math.sqrt(dimension)
    scored_questions = []
    for question, query_index in question_rows:
        query_vector = vectors[query_index]
        key_vectors = [vectors[candidate["keyIndex"]] for candidate in candidates]
        raw_scores = [dot(query_vector, key_vector) for key_vector in key_vectors]
        scaled_logits = [score / scale for score in raw_scores]
        scaled_dot_weights = softmax(scaled_logits)
        cosine_scores = [cosine(query_vector, key_vector) for key_vector in key_vectors]
        calibrated_logits = [score / temperature for score in cosine_scores]
        weights = softmax(calibrated_logits)
        context = [0.0] * dimension
        ranked = []
        for candidate, raw_score, scaled_logit, scaled_weight, cosine_score, weight in zip(
            candidates, raw_scores, scaled_logits, scaled_dot_weights, cosine_scores, weights
        ):
            value_vector = vectors[candidate["valueIndex"]]
            for index, value in enumerate(value_vector):
                context[index] += weight * value
            ranked.append({
                "glyph": candidate["glyph"], "label": candidate["label"],
                "key": {"type": "glyph_key", "key": candidate["glyph"]},
                "role": candidate["role"], "kind": candidate["kind"],
                "rawDotProduct": raw_score,
                "scaledLogit": scaled_logit, "scaledDotProductWeight": scaled_weight,
                "cosineSimilarity": cosine_score, "attentionWeight": weight,
            })
        ranked.sort(key=lambda item: item["attentionWeight"], reverse=True)
        scored_questions.append({
            "id": question.get("id"),
            "queryKey": {"type": "query_key", "key": f"QUERY:{record.get('glyph', 'UNKNOWN')}:{question.get('id', 'question')}"},
            "thoughtKey": {"type": "thought_key", "key": f"THOUGHT:{record.get('glyph', 'UNKNOWN')}:{question.get('id', 'question')}"},
            "targetGlyph": question.get("targetGlyph"),
            "question": question["question"], "queryEmbedding": query_vector,
            "score": "softmax(cosine(Q,K)/temperature)", "candidates": ranked,
            "weightedValueContext": context,
            "status": "candidate_relevance_only",
        })
    return {
        "schema": "kuhul.neighborhood.attention.v1",
        "glyph": record.get("glyph"), "word": record.get("word"),
        "parent": record.get("parent"), "depth": record.get("depth"),
        "foldKey": {"type": "fold_key", "key": f"FOLD:FIELD:{record.get('glyph', 'UNKNOWN')}", "family": "field_attention"},
        "provenance": record.get("provenance"),
        "sourceLinks": record.get("provenance", {}).get("sourceLinks", []) if isinstance(record.get("provenance"), dict) else [],
        "embedding": {"provider": backend, "model": model, "dimensions": dimension},
        "attention": {"type": "embedding_cosine_softmax", "heads": 1, "temperature": temperature,
                      "comparison": "scaledDotProductWeight stores softmax(dot(Q,K)/sqrt(dimension)); attentionWeight uses temperature-calibrated cosine because embedding vectors are unit-normalized.",
                      "note": "Single-head semantic retrieval over this field's neighbor candidates; not verification."},
        "candidateEmbeddings": [
            {"glyph": candidate["glyph"], "keyText": candidate["keyText"], "keyEmbedding": vectors[candidate["keyIndex"]],
             "valueText": candidate["valueText"], "valueEmbedding": vectors[candidate["valueIndex"]]}
            for candidate in candidates
        ],
        "questions": scored_questions,
        "relativityScore": record.get("relativityScore"),
        "relativityNote": "Discovery-depth prior; kept separate from attention weights.",
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", type=Path, default=Path("neighborhood.jsonl"))
    cli.add_argument("--output", type=Path, default=Path("neighborhood.attention.jsonl"))
    cli.add_argument("--entry", help="score one record by glyph (⟁PYTHON) or word (python)")
    cli.add_argument("--backend", choices=("ollama", "lmstudio"), default="ollama")
    cli.add_argument("--model", required=True, help="an embedding-capable model, not a chat-only model")
    cli.add_argument("--endpoint", help="API base URL (defaults to local Ollama or LM Studio)")
    cli.add_argument("--timeout", type=float, default=120.0)
    cli.add_argument("--temperature", type=float, default=0.07, help="softmax temperature for normalized embedding cosine scores (default: 0.07)")
    cli.add_argument("--batch-size", type=int, default=1, help="records per progress group; each record is independently scored")
    args = cli.parse_args()
    if args.timeout <= 0:
        cli.error("timeout must be positive")
    if args.temperature <= 0:
        cli.error("temperature must be positive")
    if args.batch_size <= 0:
        cli.error("batch-size must be positive")
    if not args.endpoint:
        args.endpoint = "http://127.0.0.1:11434" if args.backend == "ollama" else "http://127.0.0.1:17889/v1"
    try:
        records = []
        with args.input.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AttentionError(f"{args.input}:{line_no}: invalid JSONL: {exc}") from exc
                if isinstance(record, dict):
                    records.append(record)
        if args.entry:
            requested = args.entry if args.entry.startswith("⟁") else "⟁" + re.sub(r"[^A-Za-z0-9]+", "_", args.entry).strip("_").upper()
            records = [record for record in records if record.get("glyph") == requested]
            if not records:
                raise AttentionError(f"neighborhood record not found: {requested}")
        rows = []
        for index, record in enumerate(records, 1):
            if index == 1 or index % args.batch_size == 0 or index == len(records):
                print(f"Embedding neighborhood {index}/{len(records)}: {record.get('glyph', '?')}", file=sys.stderr, flush=True)
            row = score_record(record, args.backend, args.model, args.endpoint, args.timeout, args.temperature)
            if row is not None:
                rows.append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        temporary.replace(args.output)
    except (AttentionError, EmbeddingError, OSError) as exc:
        print(f"attention scoring failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(rows)} attention records to {args.output}; neighborhood.jsonl was left unchanged.")
    print("Attention weights are relevance scores only; they do not verify assertions or authorize execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())