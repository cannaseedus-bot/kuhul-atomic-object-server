#!/usr/bin/env python3
"""Ask the local model for gap-closing questions, classify the gap, rank proposals.

This is the driver, not a new rule. It composes what already exists:

    model_questions  -> the model supplies questions, never replies
    cfpc_classifier  -> the verdict: which gap is actually open
    field / lexicon  -> what evidence exists for the subject
    question_engine  -> WCR ranking, always proposal_only

Two ways in:

    --questions FILE     take a model response from disk (offline, reproducible)
    (default)            ask the configured model, using the tools/distill.py profile

The gap comes from `--gap` when given, otherwise from CFPC over the lexicon and
the field. Nothing here answers the user, admits a question, or writes anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from micronaut.cfpc_classifier import (  # noqa: E402
    GAP_ROUTES,
    classify_gap,
    load_contracts,
    match_pattern,
    recognize_intents,
)
from micronaut.model_questions import (  # noqa: E402
    ask_model_questions,
    model_question_candidates,
    parse_questions,
)
from micronaut.question_engine import propose  # noqa: E402
from micronaut.research_evidence import ResearchEvidence  # noqa: E402

KIT = ROOT / "vendor/key-grammar-kit"
LEXICON = KIT / "english-dictionary.lexicon.key-grammar.jsonl"
FIELD = ROOT / "neighborhood.jsonl"


def field_relations(subject):
    """Neighbours already recorded for this subject in the field."""
    if not FIELD.is_file():
        return []
    wanted = subject.casefold()
    found = []
    with FIELD.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if str(record.get("word") or "").casefold() == wanted:
                found.extend(record.get("neighbors") or record.get("neighbours") or [])
    return found


def lexicon_keys(subject):
    """Definition keys the classic lexicon gives this subject, if it has it."""
    if not LEXICON.is_file():
        return []
    try:
        from micronaut.dictionary import Dictionary
    except ImportError:  # pragma: no cover - environment dependent
        return []
    entry = Dictionary.load(LEXICON).define(subject)
    return list(entry["definition_keys"]) if entry else []


def classify(topic, record=None):
    """CFPC's verdict, with the evidence that produced it.

    A research record, when given, is the strongest evidence available: it is
    retrieved text with its sources named. The field and the lexicon are
    fallbacks for subjects no record covers.
    """
    resolver, _faq, patterns = load_contracts()
    intents = recognize_intents(topic, resolver)
    pattern = match_pattern(topic, patterns)
    keys = lexicon_keys(topic)
    values = record.sources if record is not None else field_relations(topic)
    gap = classify_gap(
        query=topic,
        subject=topic,
        intents=intents,
        pattern_present=bool(pattern),
        keys=keys,
        values=values,
    )
    return gap, {
        "intents": [item["name"] for item in intents],
        "pattern": pattern,
        "keys": len(keys),
        "values": len(values),
        "record": record.question_id if record is not None else None,
        "conflicts": record.conflicts() if record is not None else [],
    }


def collect_questions(args, gap):
    """Questions from disk or from the model. Never prose."""
    if args.questions:
        text = Path(args.questions).read_text(encoding="utf-8")
        return parse_questions(text, limit=args.limit), f"file:{args.questions}"
    questions = ask_model_questions(
        args.topic, gap, count=args.count, backend=args.backend,
        model=args.model, endpoint=args.endpoint, limit=args.limit,
    )
    return questions, f"model:{args.backend}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("topic", help="subject or question to build context around")
    parser.add_argument("--gap", choices=sorted(GAP_ROUTES),
                        help="CFPC verdict to use instead of classifying")
    parser.add_argument("--questions", type=Path,
                        help="read a model response from this file instead of calling a model")
    parser.add_argument("--count", type=int, default=5, help="questions to request (default: 5)")
    parser.add_argument("--record", type=Path,
                        help="research record under micronauts-data/ to use as evidence")
    parser.add_argument("--limit", type=int, default=8, help="most questions to keep (default: 8)")
    parser.add_argument("--rank", type=int, default=5, help="proposals to return (default: 5)")
    parser.add_argument("--weight", type=float, default=0.5,
                        help="W selection prior (default: 0.5, a placeholder — not evidence)")
    parser.add_argument("--confidence", type=float, default=0.5,
                        help="C evidence confidence (default: 0.5, a placeholder)")
    parser.add_argument("--relativity", type=float, default=0.5,
                        help="R relevance from a provider (default: 0.5, a placeholder)")
    parser.add_argument("--backend", default="local", choices=("local", "ollama", "lmstudio"))
    parser.add_argument("--model", help="override the model from the distill profile")
    parser.add_argument("--endpoint", help="override the endpoint from the distill profile")
    parser.add_argument("--classify-only", action="store_true",
                        help="return the CFPC gap and evidence without generating question proposals")
    args = parser.parse_args()

    if args.count < 1 or args.limit < 1 or args.rank < 1:
        parser.error("count, limit and rank must be positive")
    if not args.topic.strip():
        parser.error("topic must not be empty")

    record = None
    if args.record:
        try:
            record = ResearchEvidence.load(args.record)
        except ValueError as exc:
            print(f"cfpc-model: {exc}", file=sys.stderr)
            return 1

    if args.gap:
        gap, evidence = args.gap, {"source": "explicit"}
        if record is not None:
            evidence["record"] = record.question_id
            evidence["authority"] = record.authority
            evidence["conflicts"] = record.conflicts()
    else:
        gap, evidence = classify(args.topic, record)
        evidence["source"] = "cfpc"
        if record is not None:
            evidence["authority"] = record.authority

    output = {
        "topic": args.topic,
        "gap": gap,
        "route": GAP_ROUTES.get(gap),
        "evidence": evidence,
        "authority": "proposal_only",
    }

    if args.classify_only:
        output["schema"] = "kuhul.cfpc.classification.v1"
        output["evidence_status"] = (
            "conflicted" if evidence.get("conflicts") else
            "source_evidence_available" if record is not None else "local_gap_evidence"
        )
        print(json.dumps(output, ensure_ascii=True, indent=2))
        return 0

    if gap == "RESOLVED":
        output["questions"] = []
        output["proposals"] = []
        output["note"] = "nothing missing, so no question is asked"
        print(json.dumps(output, ensure_ascii=True, indent=2))
        return 0

    try:
        questions, source = collect_questions(args, gap)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"cfpc-model: {exc}", file=sys.stderr)
        return 1

    rows = model_question_candidates(
        "\n".join(questions), gap=gap,
        weight=args.weight, confidence=args.confidence, relativity=args.relativity,
    )
    ranked = propose(gap, rows, k=args.rank)

    output["questionsFrom"] = source
    output["questions"] = questions
    output["proposals"] = [
        {
            "text": row.text,
            "score": round(row.score, 6),
            "weight": row.weight,
            "confidence": row.confidence,
            "relativity": row.relativity,
            "gate": row.gate,
            "source": row.source,
            "authority": row.authority,
        }
        for row in ranked
    ]
    if not output["proposals"]:
        output["note"] = "the model returned no question, so nothing is proposed"
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
