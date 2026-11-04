"""Compile advisor-bootstrap.json into a validated XPath-style semantic route map.

Reads key.grammar.advisor_bootstrap.v1, validates wildcard precedence (a broad
wildcard must not appear before a more-specific sibling in the route array),
classifies each route as xcfe_gated (direct user intent) or cue_only (self-
generated assistant text that must not auto-dispatch), groups patterns into
route families, and writes kuhul.advisor-map.v1 JSON. Optionally projects to AIML.

Usage:
  python tools/advisor_map.py --validate
  python tools/advisor_map.py --output vendor/key-grammar-kit/data/advisor-map.json
  python tools/advisor_map.py --aiml vendor/key-grammar-kit/data/micronaut/advisor-routes.aiml
  python tools/advisor_map.py --output ... --aiml ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOOTSTRAP = (
    ROOT / "vendor" / "key-grammar-kit" / "data" / "advisor-bootstrap.json"
)
DEFAULT_OUTPUT = ROOT / "vendor" / "key-grammar-kit" / "data" / "advisor-map.json"
DEFAULT_AIML = (
    ROOT / "vendor" / "key-grammar-kit" / "data" / "micronaut" / "advisor-routes.aiml"
)

# Patterns that look like assistant self-reference (not imperative user commands)
# must create a typed cue event and pass through XCFE rather than dispatching
# directly. An assistant's own generated text must not auto-authorize a tool call.
_SELF_REFERENCE_STARTS = (
    "I DON'T ",
    "I DO NOT ",
    "I'M NOT ",
    "I AM NOT ",
    "LET ME SEARCH",
    "LET ME ASK",
)

# Canonical route-family key for each known expert.
_EXPERT_KEY: dict[str, str] = {
    "MATH-µ": "math",
    "coder": "code",
    "WEB-RESEARCH-µ": "research",
    "reasoner": "explain",
    "CHAT-u": "tool_help",
    "Coordinator": "plan",
}


# ---------------------------------------------------------------------------
# Pattern analysis helpers
# ---------------------------------------------------------------------------

def _specificity(pattern: str) -> int:
    """Count literal (non-wildcard) tokens in an AIML-style pattern."""
    return sum(1 for tok in pattern.split() if tok != "*")


def _has_wildcard(pattern: str) -> bool:
    return "*" in pattern.split()


def _is_self_reference(pattern: str) -> bool:
    return any(pattern.startswith(prefix) for prefix in _SELF_REFERENCE_STARTS)


def _parse_prefix_cue(prefix: str) -> dict[str, str]:
    """Extract key=value tokens from an advisor prefix string."""
    result: dict[str, str] = {}
    for token in prefix.split():
        if "=" in token:
            key, _, value = token.partition("=")
            result[key] = value
    return result


def _family_key(expert: str, is_cue: bool) -> str:
    base = _EXPERT_KEY.get(expert, re.sub(r"[^a-z0-9]+", "_", expert.lower()))
    return base + ("_cue" if is_cue else "")


# ---------------------------------------------------------------------------
# Precedence validation
# ---------------------------------------------------------------------------

def _validate_precedence(routes: list[dict[str, Any]]) -> list[str]:
    """Return precedence issues found in route array order.

    A broad wildcard pattern (e.g. ADVISE *) that appears before a sibling
    more-specific pattern (e.g. ADVISE MATH *) would shadow it in a sequential
    JSON-array matcher. This check catches that case.

    The existing bootstrap is already correctly ordered (catch-all last) so a
    clean result proves nothing about the validator itself — the caller is
    responsible for running it against a reordered fixture when testing.
    """
    issues: list[str] = []
    for i, broad in enumerate(routes):
        if not _has_wildcard(broad["pattern"]):
            continue
        # Strip the trailing wildcard to get the literal prefix this pattern claims.
        broad_prefix = broad["pattern"].rsplit(" *", 1)[0].strip()
        for j in range(i + 1, len(routes)):
            later = routes[j]
            if later["pattern"].startswith(broad_prefix + " "):
                issues.append(
                    f"index {j} '{later['pattern']}' is more specific than "
                    f"index {i} '{broad['pattern']}' but appears after it; "
                    f"sequential matchers would never reach the specific pattern"
                )
    return issues


# ---------------------------------------------------------------------------
# Route family builder
# ---------------------------------------------------------------------------

def _build_families(routes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}

    for route in routes:
        expert = route["expert"]
        phase = route["phase"]
        next_phase = route["next"]
        pattern = route["pattern"]
        prefix = route.get("prefix", "")
        is_cue = _is_self_reference(pattern)
        cue_data = _parse_prefix_cue(prefix)

        key = _family_key(expert, is_cue)
        if key not in families:
            entry: dict[str, Any] = {
                "expert": expert,
                "phase": phase,
                "next": next_phase,
                "dispatch_policy": "cue_only" if is_cue else "xcfe_gated",
                "patterns": [],
            }
            if is_cue:
                entry["cue_event"] = cue_data.get("event", "")
                entry["cue_type"] = cue_data.get("cue", "")
            families[key] = entry

        families[key]["patterns"].append({
            "pattern": pattern,
            "wildcards": _has_wildcard(pattern),
            "specificity": _specificity(pattern),
            "dispatch_policy": "cue_only" if is_cue else "xcfe_gated",
        })

    # Within each family sort patterns: exact matches first, then by specificity
    # descending so more-specific wildcards precede broader ones.
    for family in families.values():
        family["patterns"].sort(
            key=lambda p: (p["wildcards"], -p["specificity"], p["pattern"])
        )

    return families


# ---------------------------------------------------------------------------
# Map builder
# ---------------------------------------------------------------------------

def build_map(bootstrap: dict[str, Any]) -> dict[str, Any]:
    routes = bootstrap.get("routes") or []
    issues = _validate_precedence(routes)
    families = _build_families(routes)
    source_hash = hashlib.sha256(
        json.dumps(bootstrap, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "kuhul.advisor-map.v1",
        "source_schema": bootstrap.get("schema", ""),
        "source_hash": source_hash,
        "micronaut": bootstrap.get("track", "ADVISOR-µ"),
        "authority": "none",
        "xcfe": {
            "admission": "required",
            "dispatch": "host_controlled",
            "route_authority": "proposal_only",
        },
        "routes": families,
        "precedence_validation": {
            "checked": True,
            "issues": issues,
        },
    }


# ---------------------------------------------------------------------------
# AIML projection
# ---------------------------------------------------------------------------

def _aiml_template(family: dict[str, Any]) -> str:
    """AIML template that creates a typed xcfe_pending event — never direct dispatch."""
    expert = family["expert"]
    phase = family["phase"]
    next_phase = family["next"]
    if family["dispatch_policy"] == "cue_only":
        cue_event = family.get("cue_event", "")
        cue_type = family.get("cue_type", "")
        # Self-generated text: record the cue event; do not redirect or dispatch.
        return (
            f'<think>'
            f'<set name="advisor_cue_event">'
            f'cue expert="{expert}" phase="{phase}" next="{next_phase}" '
            f'event="{cue_event}" cue="{cue_type}" dispatch="xcfe_pending"'
            f'</set>'
            f'</think>'
        )
    else:
        # Direct user command: set route event; actual dispatch waits for XCFE.
        return (
            f'<think>'
            f'<set name="advisor_route_event">'
            f'route expert="{expert}" phase="{phase}" next="{next_phase}" '
            f'dispatch="xcfe_pending"'
            f'</set>'
            f'</think>'
            f'<srai>XCFE ROUTE <star/></srai>'
        )


def build_aiml(advisor_map: dict[str, Any]) -> str:
    """Generate AIML projection ordered by pattern specificity (most-specific first)."""
    # Collect all patterns from all families.
    all_entries: list[tuple[bool, int, str, dict[str, Any]]] = []
    for family in advisor_map["routes"].values():
        for pat in family["patterns"]:
            all_entries.append((
                pat["wildcards"],    # False (exact) sorts before True (wildcard)
                -pat["specificity"], # more literal words first
                pat["pattern"],
                family,
            ))
    all_entries.sort(key=lambda x: (x[0], x[1], x[2]))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- AIML projection of ADVISOR-µ route bootstrap. -->",
        "<!-- Generated by tools/advisor_map.py — the runtime router remains authoritative. -->",
        "<!-- Templates create xcfe_pending events; dispatch requires XCFE admission. -->",
        '<aiml version="2.0">',
    ]
    for _wc, _spec, _pat, family in all_entries:
        template = _aiml_template(family)
        lines += [
            "  <category>",
            f"    <pattern>{_pat}</pattern>",
            f"    <template>{template}</template>",
            "  </category>",
        ]
    lines.append("</aiml>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_BOOTSTRAP,
        help="advisor-bootstrap.json (default: vendor/.../data/advisor-bootstrap.json)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="write kuhul.advisor-map.v1 JSON to this path",
    )
    parser.add_argument(
        "--aiml", type=Path, default=None,
        help="write AIML projection to this path",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="validate precedence only (exit 1 on issues)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"bootstrap not found: {args.input}")
        return 1

    try:
        bootstrap = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to load bootstrap: {exc}")
        return 1

    if bootstrap.get("schema") != "key.grammar.advisor_bootstrap.v1":
        print(f"unsupported bootstrap schema: {bootstrap.get('schema')!r}")
        return 1

    advisor_map = build_map(bootstrap)
    issues = advisor_map["precedence_validation"]["issues"]

    if issues:
        for issue in issues:
            print(f"PRECEDENCE: {issue}")
        if args.validate:
            return 1
    else:
        n_families = len(advisor_map["routes"])
        n_patterns = sum(len(f["patterns"]) for f in advisor_map["routes"].values())
        if args.validate:
            print(
                f"OK  precedence clean — {n_families} route families, "
                f"{n_patterns} patterns"
            )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(advisor_map, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output.relative_to(ROOT)}")

    if args.aiml:
        aiml_content = build_aiml(advisor_map)
        args.aiml.parent.mkdir(parents=True, exist_ok=True)
        args.aiml.write_text(aiml_content, encoding="utf-8")
        print(f"wrote {args.aiml.relative_to(ROOT)}")

    if not args.output and not args.aiml and not args.validate:
        print(json.dumps(advisor_map, ensure_ascii=False, indent=2))

    return 1 if (issues and not args.validate) else 0


if __name__ == "__main__":
    raise SystemExit(main())
