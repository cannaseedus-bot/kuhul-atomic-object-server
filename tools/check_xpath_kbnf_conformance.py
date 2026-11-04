#!/usr/bin/env python3
"""Check the XPath 3.1 host grammar's expression and extension fixtures.

This is deliberately a conformance smoke-check, not a KBNF parser: XPath
expressions are evaluated by SaxonC, while host forms are classified by the
fixture recognizers below. A future KBNF parser can replace the recognizers
without changing the fixture contract.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


HOST_PATTERNS = [
    ("PhaseBlockOpen", re.compile(r"\[Pop\s+([A-Za-z_][\w.-]*)\]"), "name"),
    ("PhaseBlockClose", re.compile(r"\[Xul\s+([A-Za-z_][\w.-]*)\]"), "name"),
    ("PhaseExpression", re.compile(r"\[(Wo|Yax|Sek|Ch'en|Xul)\s+(.+)\]", re.S), "phase"),
    ("MicronautBlockOpen", re.compile(r"\[Micronaut\s+([^\]\s]+)\]"), "name"),
    ("AIMLBlockOpen", re.compile(r"\[AIML\s+([^\]\s]+)\]"), "name"),
    ("PatternBinding", re.compile(r"\[Pattern\s+(['\"]).*?\1\s*->\s*([^\]\s]+)\]", re.S), "target"),
    ("SRAIBinding", re.compile(r"\[SRAI\s+[^\]\s]+\s*->\s*([^\]\s]+)\]"), "target"),
    ("ELIZABlockOpen", re.compile(r"\[ELIZA\s+([^\]\s]+)\]"), "name"),
    ("XCFEBlockOpen", re.compile(r"\[XCFE\s+([^\]\s]+)\]"), "name"),
]


def classify(source):
    for kind, pattern, field in HOST_PATTERNS:
        match = pattern.fullmatch(source)
        if match:
            value = match.group(1)
            if kind == "PhaseExpression":
                return {"node": kind, "phase": value}
            if kind == "PatternBinding":
                value = match.group(2)
            return {"node": kind, field: value}
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--runtime-cli", type=Path,
                        help="also evaluate XPath fixtures through the compiled native CLI")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    grammar_path = root / "examples" / "starter.kbnf"
    mirror_path = root / "bin" / "examples" / "starter.kbnf"
    runtime_grammar_path = root / "bin" / "src" / "kuhul.ebnf"
    fixture_path = root / "examples" / "xpath-kbnf.conformance.json"
    problems = []

    grammar = grammar_path.read_text(encoding="utf-8")
    mirror = mirror_path.read_text(encoding="utf-8")
    runtime_grammar = runtime_grammar_path.read_text(encoding="utf-8")
    if grammar != mirror:
        problems.append("starter.kbnf mirror differs: bin/examples/starter.kbnf")
    for token in (
        'XPath31Expr     ::= ? external production "Expr" from W3C XPath 3.1 Appendix A ?',
        'EQName          ::= ? external production "EQName" from W3C XPath 3.1 Appendix A ?',
        "xpath-expression-statement ::= XPath31Expr \";\"",
        "phase-expression ::= \"[\" expression-phase XPath31Expr \"]\"",
        "micronaut-block", "aiml-block", "srai-binding", "eliza-block", "xcfe-block",
    ):
        if token not in grammar:
            problems.append(f"starter.kbnf missing host grammar declaration: {token}")
    for token in (
        'XPath31Expr      = ? external production "Expr" from W3C XPath 3.1 Appendix A ?',
        "expression       = XPath31Expr ;",
        "host_phase_block =",
        "phase_expression =",
        "micronaut_block  =",
        "aiml_block       =",
        "srai_binding     =",
        "eliza_block      =",
        "xcfe_block       =",
        "pattern_binding  =",
        "xgc: A host block terminator",
    ):
        if token not in runtime_grammar:
            problems.append(f"bin/src/kuhul.ebnf missing XPath host declaration: {token}")

    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    try:
        from saxonche import PySaxonProcessor
    except ImportError:
        print("FAIL | XPath KBNF conformance: saxonche is required to evaluate XPath 3.1 fixtures")
        return 2

    xpath_count = 0
    runtime_count = 0
    with PySaxonProcessor(license=False) as processor:
        for case in fixtures["xpath"]:
            try:
                xpath = processor.new_xpath_processor()
                for prefix, uri in case.get("namespaces", []):
                    xpath.declare_namespace(prefix, uri)
                if case.get("context"):
                    context_path = root / case["context"]
                    xpath.set_context(xdm_item=processor.parse_xml(xml_file_name=str(context_path)))
                actual = [str(item) for item in xpath.evaluate(case["expression"])]
            except Exception as exc:
                problems.append(f"XPath {case['id']} failed to evaluate: {exc}")
                continue
            xpath_count += 1
            if actual != case["expected"]:
                problems.append(f"XPath {case['id']}: expected {case['expected']!r}, got {actual!r}")
            if args.runtime_cli:
                command = [str(args.runtime_cli.resolve()), "--xpath", case["expression"]]
                if case.get("context"):
                    command.extend(["--context", str((root / case["context"]).resolve())])
                for prefix, uri in case.get("namespaces", []):
                    command.extend(["--namespace", f"{prefix}={uri}"])
                try:
                    completed = subprocess.run(command, capture_output=True, text=True,
                                               encoding="utf-8", timeout=60)
                    payload = json.loads(completed.stdout)
                    cli_values = [item["value"] for item in payload.get("items", [])
                                  if item.get("kind") == "atomic"]
                    if completed.returncode != 0 or not payload.get("ok"):
                        problems.append(f"native XPath {case['id']} failed: "
                                        f"{payload.get('error', completed.stderr.strip())}")
                    elif cli_values != case["expected"]:
                        problems.append(f"native XPath {case['id']}: expected "
                                        f"{case['expected']!r}, got {cli_values!r}")
                    else:
                        runtime_count += 1
                except Exception as exc:
                    problems.append(f"native XPath {case['id']} failed to launch/read: {exc}")

    host_count = 0
    for case in fixtures["host_forms"]:
        actual = classify(case["source"])
        expected = {key: value for key, value in case.items() if key != "source"}
        if actual != expected:
            problems.append(f"host form {case['source']!r}: expected typed node {expected!r}, got {actual!r}")
        else:
            host_count += 1

    if args.runtime_cli:
        external_uri = (root / "examples" / "xpath-context.xml").resolve().as_uri()
        command = [str(args.runtime_cli.resolve()), "--xpath", f"doc('{external_uri}')"]
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       encoding="utf-8", timeout=60)
            payload = json.loads(completed.stdout)
            if completed.returncode == 0 or payload.get("ok"):
                problems.append("native XPath evaluator allowed fn:doc() external-resource access")
        except Exception as exc:
            problems.append(f"native XPath external-resource denial check failed: {exc}")

        structured_cases = [
            ("array result", "[1, 2]", lambda payload:
             payload.get("items") == [{"kind": "array", "members": [
                 [{"kind": "atomic", "type": "Q{http://www.w3.org/2001/XMLSchema}integer", "value": "1"}],
                 [{"kind": "atomic", "type": "Q{http://www.w3.org/2001/XMLSchema}integer", "value": "2"}],
             ]}]),
            ("map result", "map { 'a': 1 }", lambda payload:
             payload.get("items", [{}])[0].get("kind") == "map" and
             payload["items"][0]["entries"][0]["key"].get("value") == "a" and
             payload["items"][0]["entries"][0]["value"][0].get("value") == "1"),
        ]
        for label, expression, predicate in structured_cases:
            try:
                completed = subprocess.run([str(args.runtime_cli.resolve()), "--xpath", expression],
                                           capture_output=True, text=True, encoding="utf-8", timeout=60)
                payload = json.loads(completed.stdout)
                if completed.returncode != 0 or not payload.get("ok") or not predicate(payload):
                    problems.append(f"native XPath {label} serialization mismatch: {payload!r}")
            except Exception as exc:
                problems.append(f"native XPath {label} failed: {exc}")

        try:
            completed = subprocess.run([str(args.runtime_cli.resolve()), "--xpath", "1 +"],
                                       capture_output=True, text=True, encoding="utf-8", timeout=60)
            payload = json.loads(completed.stdout)
            if completed.returncode == 0 or payload.get("ok") or not payload.get("error"):
                problems.append("native XPath syntax error did not return a structured failure")
        except Exception as exc:
            problems.append(f"native XPath syntax error handling failed: {exc}")

    status = "PASS" if not problems else "FAIL"
    runtime_summary = (f", {runtime_count}/{xpath_count} native runtime evaluation(s)"
                       if args.runtime_cli else "")
    print(f"{status} | XPath KBNF conformance: {xpath_count} XPath 3.1 expression(s)"
          f"{runtime_summary}, "
          f"{host_count}/{len(fixtures['host_forms'])} typed host form(s); "
          "host checks use fixture recognizers, not a full KBNF parser")
    for problem in problems:
        print(f"  error | {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
