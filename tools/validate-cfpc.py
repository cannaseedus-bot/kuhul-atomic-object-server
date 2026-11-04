#!/usr/bin/env python3
"""Structural + referential validator for data/cfpc contracts."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFPC = ROOT / "vendor/key-grammar-kit/data/cfpc"

PHASES = {"Pop","Wo","Yax","Sek","Chen","Ch'en","Ch_en","Xul"}
DERIVED_KINDS = {"khanary.cfpc-faq-map.v1"}

REQUIRED = {
    "khanary.cfpc.pattern.v1": ["@kind","id","intent","phase","@captures","neighborhood_resolve","question_templates","context_template"],
    "cfpc.intent_resolver": ["@kind","id","@candidates","@q_factory","@gap_expansion","@selection","@routing"],
    "semantic.event.v1": ["@kind","@id","@subject","@subject_type","@predicate","@object","@object_type","@epistemic_status","@provenance","@authority"],
    "semantic.fact.v1": ["@kind","@id","@subject","@subject_type","@predicate","@object","@object_type","@epistemic_status","@provenance","@authority"],
    "semantic.tool.v1": ["@kind","@id","@capability","@provider_ref","@provider_type","@governs","@description"],
    "semantic.relation.v1": ["@kind","@id","@domain","@range","@transitive","@authority","@description"],
    "semantic.learn.v1": ["@kind","@id","@owner","@targets","@candidates","@policy"],
    "semantic.function.v1": ["@kind","@id","@intent","@owner","@governs","@capabilities","@bindings","@backend","@policy","@result"],
    "semantic.think.v1": ["@kind","@id","@owner","@mode","@subject","@context","@functions","@policy"],
    "semantic.structure.v1": ["@kind","@id","@template","@sections"],
    "semantic.elaborate.v1": ["@kind","@id","@owner","@subject","@intent","@modes","@backend","@policy"],
    "semantic.tools.v1": ["@kind","@id","@owner","@permitted","@policy"],
    "khanary.task.v1": ["@kind","id","intent","capability","@query","@micronauts","@policy","@result"],
    "micronaut.invocation": ["@kind","caller","intent","@query","@route","@execution","@result"],
}

def present(v):
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return True
    return True

def main():
    ids = {}
    pattern_ids = set()
    failures = []
    files = sorted(CFPC.glob("*.json"))
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append((p.name, f"parse error: {e}"))
            continue
        kind = data.get("@kind")
        if kind in DERIVED_KINDS:
            continue
        req = REQUIRED.get(kind)
        if req is None:
            failures.append((p.name, f"unknown @kind {kind!r}"))
            continue
        missing = [k for k in req if k not in data or not present(data.get(k))]
        if missing:
            failures.append((p.name, f"missing/empty {missing}"))
        if kind == "khanary.cfpc.pattern.v1":
            pattern_ids.add(data.get("id"))
            rules = data.get("match", {}).get("rules", [])
            if not rules or not any(
                isinstance(rule, dict)
                and isinstance(rule.get("prefix"), str)
                and rule["prefix"].strip()
                for rule in rules
            ):
                failures.append((p.name, "missing reachable match.prefix rule"))
            for index, rule in enumerate(rules):
                if not isinstance(rule, dict) or not isinstance(rule.get("prefix"), str) or not rule["prefix"].strip():
                    failures.append((p.name, f"match.rules[{index}] requires a non-empty prefix"))
                    continue
                if "contains_any" in rule and (
                    not isinstance(rule["contains_any"], list)
                    or not all(isinstance(term, str) and term.strip() for term in rule["contains_any"])
                ):
                    failures.append((p.name, f"match.rules[{index}].contains_any must be non-empty strings"))
            temporal = data.get("temporal_contract")
            if data.get("id") == "how-many" and not isinstance(temporal, dict):
                failures.append((p.name, "how-many requires temporal_contract metadata"))
            if isinstance(temporal, dict) and temporal.get("classification") == "MUTABLE":
                if temporal.get("freshness_required") is not True:
                    failures.append((p.name, "mutable facts must require freshness validation"))
                if temporal.get("answer_requires_verified_observation") is not True:
                    failures.append((p.name, "mutable answers must require verified observations"))
        # phase validity
        for key in ("phase",):
            if key in data and data[key] not in PHASES:
                failures.append((p.name, f"invalid phase {data[key]!r}"))
        # id uniqueness
        ident = data.get("@id") or data.get("id")
        if ident:
            ids.setdefault(ident, []).append(p.name)

    faq_path = CFPC / "cfpc-faq-map.v1.json"
    try:
        faq_map = json.loads(faq_path.read_text(encoding="utf-8"))
        for pattern_id in faq_map.get("cfpc_patterns", []):
            if pattern_id not in pattern_ids:
                failures.append((faq_path.name, f"registered pattern {pattern_id!r} has no contract"))
    except Exception as e:
        failures.append((faq_path.name, f"could not validate registered matcher contracts: {e}"))

    dup_ids = {k: v for k, v in ids.items() if len(v) > 1}

    print(f"cfpc files checked: {len(files)}")
    if failures:
        for name, msg in failures:
            print(f"  FAIL {name}: {msg}")
    else:
        print("  all structural checks pass")
    print(f"  duplicate @id values: {dup_ids if dup_ids else 'none'}")
    print(f"  unique identifiers: {len(ids)}")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
