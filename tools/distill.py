#!/usr/bin/env python3
"""Distill one word into a candidate K'UHUL semantic-neighborhood JSONL record.

This tool generates data only. It does not verify claims, authorize execution,
or compile a KSO package.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from micronaut.model_runtime import generate_text


PROMPT = r'''Return only a compact JSON neighborhood candidate with this shape:
{"root":"⟁WORD","field":"short category","neighbors":[{"word":"concept","relation":"short relation","kind":"identity","question":"How does WORD relate to CONCEPT?"}]}
Provide exactly 8 distinct, useful neighbor concepts. Each neighbor needs only a
short word or phrase, a short relation label, a kind, and one concise reasoning
question. Each question must mention both the input word and its neighbor and ask
about their relationship. Keep concepts plausible and context-sensitive; do not
claim evidence, verification, or universal facts.
The program will construct vector coordinates, typed fields, ten levels, relations,
and verification/commit terminal levels from this compact candidate. No prose.

Input word: {word}
'''


class DistillError(RuntimeError):
    pass


def _context_source_links(context: str) -> list[dict]:
    """Keep user-supplied URLs as provenance references; never fetch them here."""
    links = []
    seen = set()
    for raw in re.findall(r"https?://[^\s<>\"']+", context, flags=re.IGNORECASE):
        uri = raw.rstrip(".,;:!?)]}")
        try:
            parsed = urlsplit(uri)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        if uri not in seen:
            seen.add(uri)
            links.append({"uri": uri, "providedBy": "user_context", "fetched": False})
        if len(links) == 16:
            break
    return links


def _glyph_slug(value: str) -> str:
    """Canonicalize punctuation-bearing names without collapsing them (for example C++)."""
    value = value.strip().upper()
    value = value.replace("++", "_PLUS_PLUS_").replace("#", "_SHARP_")
    value = value.replace("+", "_PLUS_").replace(".", "_DOT_")
    return re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]+", "_", value)).strip("_")


def _check_field(word: str, data: object) -> tuple[str, dict]:
    if isinstance(data, dict) and isinstance(data.get("root"), str) and isinstance(data.get("neighbors"), list):
        expected = "⟁" + _glyph_slug(word)
        source_root = data["root"]
        if not re.fullmatch(r"⟁[A-Z0-9_]+", source_root):
            source_root = expected
        entries = data["neighbors"]
        if len(entries) != 8:
            raise DistillError(f"compact candidate must contain exactly 8 neighbors; received {len(entries)}")
        roles = ["identity", "gradient", "bias", "topology", "sensory", "temporal", "spatial", "operational"]
        neighbors = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("word"), str) or not entry["word"].strip():
                raise DistillError(f"neighbor {index + 1} needs a word")
            label = entry["word"].strip()
            symbol = "⟁" + _glyph_slug(label)
            if len(symbol) < 3:
                raise DistillError(f"neighbor {index + 1} does not produce a valid glyph: {label}")
            relation = re.sub(r"\s+", "_", str(entry.get("relation", "related_to")).strip().lower()) or "related_to"
            kind = re.sub(r"\s+", "_", str(entry.get("kind", roles[index])).strip().lower()) or roles[index]
            question = str(entry.get("question", "")).strip()
            neighbors.append({"label": label, "symbol": symbol, "relation": relation, "kind": kind, "question": question})
        category = str(data.get("field", "semantic_neighborhood")).strip() or "semantic_neighborhood"
        coordinates = [item["symbol"] for item in neighbors] + ["⟁VERIFIED", "⟁COMMIT"]
        field_coordinates = {str(i): f"field.{role}" for i, role in enumerate(roles, 1)}
        fields = {role: {"level": i, "symbol": neighbors[i - 1]["symbol"], "sourceLevel": str(i)} for i, role in enumerate(roles, 1)}
        levels = {}
        relations = []
        format_shapes = []
        reasoning_questions = []
        for i, (role, item) in enumerate(zip(roles, neighbors), 1):
            root_term = re.sub(r"[^A-Za-z0-9]+", "_", word).strip("_").lower()
            neighbor_term = re.sub(r"[^A-Za-z0-9]+", "_", item["label"]).strip("_").lower()
            shape = f"{root_term} relates to {neighbor_term}"
            if len(shape.split()) != 4:
                raise DistillError(f"generated format shape is not four words: {shape}")
            format_shapes.append({"glyph": item["symbol"], "shape": shape, "wordCount": 4})
            question_templates = [
                ("relation_probe.v1", "How does {word} relate to {neighbor}?"),
                ("role_probe.v1", "What role does {neighbor} play for {word}?"),
                ("connection_probe.v1", "What connects {word} with {neighbor}?"),
                ("condition_probe.v1", "When is {neighbor} relevant to {word}?"),
            ]
            seed = f"{expected}:{item['symbol']}".encode("utf-8")
            template_index = int.from_bytes(hashlib.sha256(seed).digest()[:4], "big") % len(question_templates)
            template_id, question_template = question_templates[template_index]
            question = question_template.format(word=word, neighbor=item["label"])
            model_question = item.get("question", "").strip()
            if word.casefold() not in model_question.casefold() or item["label"].casefold() not in model_question.casefold():
                model_question = ""
            reasoning_questions.append({
                "id": f"{expected}:{item['symbol']}:question.v1",
                "targetGlyph": item["symbol"],
                "template": template_id,
                "question": question,
                "modelQuestion": model_question or None,
                "slots": {"subject": expected, "subjectWord": word, "neighbor": item["symbol"], "neighborWord": item["label"], "relation": item["relation"]},
                "responseContract": {"type": "relation_explanation", "requiresEvidence": True, "allowUnknown": True},
                "purpose": "relation_probe",
                "status": "candidate",
            })
            phrase = f"{root_term}_{item['relation']}_{neighbor_term}"
            phrase = re.sub(r"[^a-z0-9_]+", "_", phrase).strip("_")
            levels[str(i)] = {"role": role, "symbol": item["symbol"], "kind": item["kind"], "notation": [shape, phrase]}
            relations.append({"notation": phrase, "subject": expected, "predicate": item["relation"].upper(), "object": item["symbol"], "type": item["kind"], "polarity": "positive"})
        levels["9"] = {"role": "confidence", "symbol": "⟁VERIFIED", "kind": "verification_gate", "notation": ["assertion_requires_evidence", "field_scoped_verification"], "requires": ["assertion", "evidence", "scope", "verification_result"]}
        levels["10"] = {"role": "terminal", "symbol": "⟁COMMIT", "kind": "authorized_closure", "notation": ["verified_field_commit", "authorized_terminal"], "requires": ["authorized_commit", "verified_assertions"]}
        data = {expected: {
            "root": expected, "field": category, "maxLevel": 10, "terminal": 10,
            "vector": {"space": "semantic-field", "dimensions": 10, "coordinates": coordinates,
                       "fieldDimensions": list(range(1, 9)), "evaluationDimensions": [9, 10], "fieldCoordinates": field_coordinates},
            "fields": fields, "levels": levels, "formatShapes": format_shapes,
            "reasoningQuestions": reasoning_questions,
            "semanticNotation": {"format": "underscore_compound", "representation": "typed_relational_graph", "patterns": {"dependency": "*_requires_*", "relation": "*_related_to_*"}},
            "relations": relations,
            "inference": {"mode": "evidence_gated", "rules": [], "constraints": ["candidate_inference_requires_verification", "contextual_properties_are_not_universal"]},
            "memory": {"replay": "candidate_neighborhood_events", "field": category, "provenance": "per_assertion", "commitPolicy": "verified_and_authorized"}
        }}
    if isinstance(data, dict) and isinstance(data.get("glyph"), str) and isinstance(data.get("field"), dict):
        data = {data["glyph"]: data["field"]}
    if not isinstance(data, dict) or len(data) != 1:
        raise DistillError("model output must be an object with exactly one glyph-keyed field")
    model_glyph, field = next(iter(data.items()))
    expected = "⟁" + _glyph_slug(word)
    if not re.fullmatch(r"⟁[A-Z0-9_]+", model_glyph):
        raise DistillError(f"model returned invalid root glyph: {model_glyph!r}")
    if not isinstance(field, dict):
        raise DistillError("glyph value must be a field object")
    field_root = field.get("root")
    if not isinstance(field_root, str) or not re.fullmatch(r"⟁[A-Z0-9_]+", field_root):
        field_root = model_glyph
        field["root"] = model_glyph

    # The prompt requests the input word as root, but models may choose a synonym.
    # Canonicalize that one root identity and all exact references to it.
    aliases = {model_glyph, field_root}
    def replace_root(value):
        if isinstance(value, str):
            return expected if value in aliases else value
        if isinstance(value, list):
            return [replace_root(item) for item in value]
        if isinstance(value, dict):
            return {key: replace_root(item) for key, item in value.items()}
        return value
    field = replace_root(field)
    field["root"] = expected
    glyph = expected
    required = {"root", "field", "maxLevel", "terminal", "vector", "fields", "levels", "semanticNotation", "relations", "inference", "memory"}
    missing = sorted(required - field.keys())
    if missing:
        raise DistillError("field is missing: " + ", ".join(missing))
    if field["root"] != glyph or field["maxLevel"] != 10 or field["terminal"] != 10:
        raise DistillError("root, maxLevel, or terminal does not match the 10-level field contract")
    vector = field["vector"]
    if not isinstance(vector, dict) or vector.get("dimensions") != 10 or len(vector.get("coordinates", [])) != 10:
        raise DistillError("vector must define exactly 10 coordinates and dimensions=10")
    if vector.get("fieldDimensions") != list(range(1, 9)) or vector.get("evaluationDimensions") != [9, 10]:
        raise DistillError("vector field/evaluation dimensions must be [1..8] and [9,10]")
    levels = field["levels"]
    if not isinstance(levels, dict) or set(levels) != {str(n) for n in range(1, 11)}:
        raise DistillError("levels must contain exactly string keys 1 through 10")
    for n in range(1, 11):
        item = levels[str(n)]
        if not isinstance(item, dict) or not all(k in item for k in ("role", "symbol", "kind", "notation")):
            raise DistillError(f"level {n} is missing role, symbol, kind, or notation")
        if not isinstance(item["notation"], list) or not item["notation"]:
            raise DistillError(f"level {n} notation must be a non-empty array")
    # Normalize common model formatting drift into the existing field schema.
    if isinstance(field["fields"], list):
        roles = vector.get("fieldCoordinates", {})
        normalized_fields = {}
        for item in field["fields"]:
            if not isinstance(item, dict):
                raise DistillError("field entries must be objects")
            level = item.get("level")
            if not isinstance(level, int) or not 1 <= level <= 8:
                raise DistillError("field entry level must be an integer from 1 to 8")
            role = str(roles.get(str(level), f"level_{level}")).lower()
            role = re.sub(r"[^a-z0-9]+", "_", role).strip("_")
            symbol = item.get("symbol")
            if not isinstance(symbol, str) or not symbol.startswith("⟁"):
                raise DistillError(f"field level {level} must have a glyph symbol")
            normalized_fields[role] = {"level": level, "symbol": symbol, "sourceLevel": str(item.get("sourceLevel", level))}
        field["fields"] = normalized_fields
    if isinstance(field["relations"], list):
        normalized_relations = []
        for relation in field["relations"]:
            if not isinstance(relation, dict):
                raise DistillError("relation entries must be objects")
            relation = dict(relation)
            notation = relation.get("notation")
            if isinstance(notation, list):
                relation["notation"] = "_".join(str(part).strip().lower().replace(" ", "_") for part in notation)
            for endpoint in ("subject", "object"):
                value = relation.get(endpoint)
                if isinstance(value, str) and not value.startswith("⟁"):
                    relation[endpoint] = "⟁" + _glyph_slug(value)
            if isinstance(relation.get("predicate"), str):
                relation["predicate"] = relation["predicate"].upper()
            if relation.get("polarity") == "neutral":
                relation["polarity"] = "positive"
            normalized_relations.append(relation)
        field["relations"] = normalized_relations
    if isinstance(field.get("memory"), dict) and isinstance(field["memory"].get("replay"), bool):
        field["memory"]["replay"] = "observed_events" if field["memory"]["replay"] else "disabled"
    if not isinstance(field["relations"], list) or not isinstance(field["inference"], dict) or not isinstance(field["memory"], dict):
        raise DistillError("relations, inference, and memory must have the declared object/array types")
    if len(field["fields"]) != 8:
        raise DistillError("fields must define all eight non-terminal semantic levels")
    _attach_evidence(field)
    return glyph, field


def _attach_evidence(field: dict) -> None:
    """Name where each non-inline dimension lives. This grants nothing.

    A candidate-relevance row is not a verification, a syllable match is not a
    meaning match, and a token id is not authority. The block only records the
    source and status of each dimension so a consumer can find it.

    `provenance` ranks the document: this generator emits `origin: model` at
    precedence 1, so an authored field at precedence 0 wins wherever both exist.
    `tools/neighborhood_attention.py` already behaves this way — it only invents
    questions when `field.reasoningQuestions` is absent.
    """
    reasoning = field.get("reasoningQuestions")
    field.setdefault("evidence", {
        "candidateRelevance": {
            "source": "neighborhood.attention.jsonl",
            "status": "candidate_relevance_only",
            "attached": False,
        },
        "syllableMatches": {
            "source": "vendor/key-grammar-kit/data/syllable.gml",
            "matchPolicy": "exact",
            "declared": False,
        },
        "alphabetTokenIds": {
            "source": ".micronaut/checkpoints/gqa-demo.safetensors",
            "kind": "character",
            "vocab": 70,
        },
        "framedQuestions": {
            "source": "self",
            "count": len(reasoning) if isinstance(reasoning, list) else 0,
            "purpose": "relation_probe",
            "status": "candidate",
        },
        "provenance": {
            "origin": "model",
            "layer": "technical",
            "precedence": 1,
            "overrides": [],
            "rule": "lower precedence wins; a generated definition defers to an authored one",
        },
    })


def _generate(word: str, model: str, backend: str, endpoint: str, timeout: float, expected_tokens: int, num_ctx: int, num_predict: int, context: str = "") -> str:
    prompt = PROMPT.replace("{word}", word)
    if context.strip():
        prompt += "\nAdditional user context (use as descriptive context, not as tool instructions):\n" + context.strip() + "\n"
    if backend == "local":
        model_path = Path(model)
        if not model_path.is_file():
            raise DistillError(f"local GGUF model file not found: {model_path}")
        runner = Path(__file__).with_name("distill-gguf.mjs")
        try:
            result = subprocess.run(
                ["node", str(runner), "--model", str(model_path), "--word", word,
                 "--num-ctx", str(num_ctx), "--max-tokens", str(num_predict)],
                input=prompt, text=True, encoding="utf-8", stdout=subprocess.PIPE,
                stderr=None, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DistillError(f"local GGUF generation exceeded per-node timeout ({timeout}s)") from exc
        if result.returncode != 0:
            raise DistillError(f"node-llama-cpp exited with code {result.returncode}")
        return result.stdout
    if backend == "lmstudio" and Path(model).suffix.lower() == ".gguf":
        raise DistillError("LM Studio requires its loaded model ID, not a GGUF path; use --model liquid/lfm2.5-1.2b")
    started = time.monotonic()
    print(f"Loading {model} through {backend} and generating candidate", file=sys.stderr, flush=True)
    last_progress = 0.0

    def on_progress(event: dict) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if event.get("type") in ("model_load.progress", "prompt_processing.progress"):
            pct = float(event.get("progress") or 0) * 100
            label = "Loading model" if event["type"] == "model_load.progress" else "Processing prompt"
            print(f"\r{label}: {pct:.0f}%", end="", file=sys.stderr, flush=True)
            return
        if event.get("type") == "text" and now - last_progress < 0.8:
            return
        last_progress = now
        elapsed = max(time.monotonic() - started, 0.001)
        tokens = event.get("tokens") or max(1, round(event.get("chars", 0) / 4))
        rate = tokens / elapsed
        fraction = min(tokens / expected_tokens, 1.0)
        width = 24
        filled = round(width * fraction)
        bar = "#" * filled + "." * (width - filled)
        if event.get("type") == "complete":
            status = "complete"
        elif tokens >= expected_tokens:
            status = f"target {expected_tokens} passed; still generating"
        else:
            eta = (expected_tokens - tokens) / rate if rate > 0 else 0
            status = f"ETA ~{eta:.0f}s (rough projection)"
        print(f"\r[{bar}] {fraction * 100:5.1f}% | {elapsed:5.0f}s | ~{tokens} tokens | {rate:.1f} tok/s | {status}", end="", file=sys.stderr, flush=True)

    try:
        return generate_text(
            backend=backend, model=model, endpoint=endpoint,
            messages=[
                {"role": "system", "content": "Return only schema-constrained candidate semantic JSON."},
                {"role": "user", "content": prompt},
            ], timeout=timeout, max_tokens=num_predict, context_size=num_ctx,
            temperature=0.2, response_format="json" if backend == "ollama" else None,
            progress=on_progress,
        )
    except (RuntimeError, ValueError) as exc:
        raise DistillError(str(exc)) from exc
    finally:
        print(file=sys.stderr, flush=True)


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("word", help="word or phrase to distill")
    cli.add_argument("--model", help="Ollama name, LM Studio ID, or local GGUF path")
    cli.add_argument("--backend", choices=("ollama", "lmstudio", "local"), default="local", help="inference backend (default: local GGUF)")
    cli.add_argument("--endpoint", help="API base URL (defaults to selected local server)")
    cli.add_argument("--context", default="", help="optional descriptive context preserved from the command utterance")
    cli.add_argument("--output", type=Path, default=Path("neighborhood.jsonl"), help="append destination JSONL")
    cli.add_argument("--timeout", type=float, default=300.0)
    cli.add_argument("--expected-tokens", type=int, default=500, help="rough response size used for progress ETA (default: 500)")
    cli.add_argument("--num-ctx", type=int, default=30000, help="Ollama context window tokens (default: 30000)")
    cli.add_argument("--num-predict", type=int, default=500, help="maximum output tokens per word (default: 500)")
    cli.add_argument("--duration-minutes", type=float, default=15.0, help="total wall-clock budget for recursive neighbor expansion (default: 15 minutes)")
    cli.add_argument("--recursive", action="store_true", help="expand active neighbors recursively after building the root field")
    cli.add_argument("--max-depth", type=int, default=0, help="optional depth cap; 0 means continue until time budget")
    cli.add_argument("--max-nodes", type=int, default=0, help="optional unique-glyph cap; 0 means continue until time budget")
    args = cli.parse_args()
    if not args.model:
        args.model = {
            "ollama": "qwen3.5:4b",
            "lmstudio": "liquid/lfm2.5-1.2b",
            "local": r"C:\Users\canna\.lmstudio\models\lmstudio-community\gemma-3-1B-it-QAT-GGUF\gemma-3-1B-it-QAT-Q4_0.gguf",
        }[args.backend]
    if not args.endpoint:
        args.endpoint = "http://127.0.0.1:11434" if args.backend == "ollama" else "http://127.0.0.1:17889"
    if not args.word.strip():
        cli.error("word must not be empty")
    if args.timeout <= 0:
        cli.error("timeout must be positive")
    if args.expected_tokens <= 0:
        cli.error("expected-tokens must be positive")
    if len(args.context) > 4000:
        cli.error("context must be at most 4000 characters")
    if args.num_ctx <= 0 or args.num_predict <= 0 or args.max_depth < 0 or args.max_nodes < 0 or args.duration_minutes <= 0:
        cli.error("num-ctx, num-predict, duration-minutes must be positive; max-depth and max-nodes must be non-negative")
    deadline = time.monotonic() + args.duration_minutes * 60
    try:
        existing = {}
        if args.output.exists():
            for line_no, line in enumerate(args.output.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DistillError(f"{args.output}:{line_no}: invalid JSONL: {exc}") from exc
                if record.get("schema") == "kuhul.neighborhood.record.v1" and isinstance(record.get("glyph"), str):
                    existing[record["glyph"]] = record

        active: set[str] = set()
        complete: set[str] = set()
        cycles: list[str] = []
        generated = 0
        budget_reached = False
        skipped: list[str] = []

        def neighbors(record: dict) -> list[tuple[str, str]]:
            field = record.get("field", {})
            levels = field.get("levels", {}) if isinstance(field, dict) else {}
            result = []
            seen = set()
            for level in range(1, 9):
                item = levels.get(str(level), {}) if isinstance(levels, dict) else {}
                symbol = item.get("symbol") if isinstance(item, dict) else None
                if not isinstance(symbol, str) or not re.fullmatch(r"⟁[A-Z0-9_]{2,}", symbol) or symbol == record.get("glyph") or symbol in seen:
                    continue
                seen.add(symbol)
                word = re.sub(r"_+", " ", symbol[1:]).strip().lower()
                if word:
                    result.append((symbol, word))
            return result

        def expand(word: str, depth: int, parent: str | None = None) -> None:
            nonlocal generated, budget_reached
            if time.monotonic() >= deadline:
                budget_reached = True
                return
            requested_glyph = "⟁" + _glyph_slug(word)
            if requested_glyph in active:
                cycles.append(f"{parent or requested_glyph} -> {requested_glyph}")
                return
            if requested_glyph in complete or (args.max_nodes and len(complete) >= args.max_nodes):
                return
            active.add(requested_glyph)
            record = existing.get(requested_glyph)
            if record is None:
                elapsed = args.duration_minutes * 60 - max(0, deadline - time.monotonic())
                print(f"\nDistilling unique node {len(complete) + 1}: {requested_glyph} (depth {depth}, expansion elapsed {elapsed:.0f}s)", file=sys.stderr, flush=True)
                content = _generate(word, args.model, args.backend, args.endpoint, args.timeout, args.expected_tokens, args.num_ctx, args.num_predict, args.context)
                try:
                    result = json.loads(content)
                    glyph, field_data = _check_field(word, result)
                except (json.JSONDecodeError, DistillError) as exc:
                    active.remove(requested_glyph)
                    if depth == 0:
                        raise DistillError(f"root distillation failed for {word}: {exc}") from exc
                    skipped.append(f"{requested_glyph}: {exc}")
                    print(f"Skipping invalid child candidate {requested_glyph}: {exc}", file=sys.stderr)
                    return
                node_score = round(1.0 / (1 + depth), 6)
                field_data["relativity"] = {
                    "score": node_score,
                    "discoveryDepth": depth,
                    "metric": "inverse_discovery_depth",
                    "note": "Structural proximity prior; not confidence, evidence, or verification.",
                }
                for shape in field_data.get("formatShapes", []):
                    edge_depth = depth + 1
                    shape["relativityScore"] = round(1.0 / (1 + edge_depth), 6)
                    shape["discoveryDepth"] = edge_depth
                record = {
                    "schema": "kuhul.neighborhood.record.v1", "glyph": glyph, "word": word,
                    "status": "candidate", "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "generator": {"provider": args.backend, "model": args.model, "num_ctx": args.num_ctx},
                    "generationContext": args.context,
                    "provenance": {
                        "origin": "model_generated_candidate",
                        "sourceLinks": _context_source_links(args.context),
                        "externalRetrieval": {"queried": False, "scraped": False, "sources": []},
                        "note": "No external sources were retrieved by this distillation run; generated assertions are unverified candidates.",
                    },
                    "parent": parent, "depth": depth, "field": field_data,
                    "relativityScore": node_score,
                }
                active_neighbors = neighbors(record)
                record["activeNeighbors"] = [g for g, _ in active_neighbors]
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                existing[glyph] = record
                generated += 1
            else:
                active_neighbors = neighbors(record)
            complete.add(requested_glyph)
            if args.recursive and (not args.max_depth or depth < args.max_depth):
                for neighbor_glyph, neighbor_word in active_neighbors:
                    if time.monotonic() >= deadline:
                        budget_reached = True
                        break
                    if args.max_nodes and len(complete) >= args.max_nodes:
                        break
                    if neighbor_glyph in active:
                        cycles.append(f"{requested_glyph} -> {neighbor_glyph}")
                        continue
                    expand(neighbor_word, depth + 1, requested_glyph)
                    if budget_reached:
                        break
            active.remove(requested_glyph)

        expand(args.word.strip(), 0)
    except (DistillError, OSError) as exc:
        print(f"distill failed: {exc}", file=sys.stderr)
        return 1
    duration = args.duration_minutes * 60 - max(0, deadline - time.monotonic())
    action = "Neighborhood expansion" if args.recursive else "Field distillation"
    print(f"{action} ended after {duration:.0f}s; visited {len(complete)} glyphs and generated {generated} new records in {args.output}.")
    if budget_reached and args.recursive:
        print("Time budget reached; the active node was allowed to finish and was saved before expansion stopped.")
    print(f"Active-path cycle edges detected: {len(cycles)}.")
    print(f"Invalid child candidates skipped: {len(skipped)}.")
    for edge in cycles:
        print(f"  cycle: {edge}")
    print("Candidate data only: no verification, XCFE admission, or execution was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
