#!/usr/bin/env python3
"""Create and admit DATA_ONLY Micronaut candidates from declarative MML."""
from __future__ import annotations

import argparse
import os
import re
import json
import tempfile
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")
PHASES = {"Pop", "Wo", "Yax", "Sek", "Chen", "Ch'en", "Ch_en", "Xul"}
TOOL_PERMISSIONS = {"read", "compute", "network", "write", "execute"}
RESEARCH_SCHEMA = "kuhul.micronaut_data.research.v1"
RESEARCH_AUTHORITY = "source_evidence_only; not_verified_fact"


def _children(parent: ET.Element | None, path: str) -> list[ET.Element]:
    return list(parent.findall(path)) if parent is not None else []


def parse_mml(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", raw, re.IGNORECASE):
        raise ValueError("MML DTDs and entities are not accepted")
    root = ET.fromstring(raw)
    if root.tag != "micronaut":
        raise ValueError("MML root element must be <micronaut>")
    agent_id = root.get("id", "")
    if not ID_RE.fullmatch(agent_id):
        raise ValueError("micronaut id must be 1-48 letters, digits, '_' or '-' and start alphanumeric")
    name = root.get("name", agent_id)
    program = root.find("program")
    if program is None or not program.get("language") or not program.get("entry"):
        raise ValueError("<program> requires language and entry references")

    modes = []
    for mode in _children(root.find("behavior"), "mode"):
        ref = mode.get("ref")
        if not ref:
            raise ValueError("behavior mode requires ref")
        weight = float(mode.get("weight", "1"))
        if not 0 <= weight <= 1:
            raise ValueError(f"mode weight out of range for {ref}")
        modes.append({"ref": ref, "weight": weight})

    biases = []
    for bias in _children(root.find("vector"), "bias"):
        key = bias.get("name")
        if not key:
            raise ValueError("vector bias requires name")
        value = float(bias.get("value", "0"))
        if not -1 <= value <= 1:
            raise ValueError(f"vector bias out of range for {key}")
        biases.append({"name": key, "value": value})

    field = root.find("field")
    field_data = dict(field.attrib) if field is not None else {}
    memory = root.find("memory")
    memory_data = {"attributes": dict(memory.attrib), "types": [e.get("ref") for e in _children(memory, "type")]} if memory is not None else None

    capabilities = [e.get("ref") for e in _children(root.find("capabilities"), "invoke")]
    if any(not item for item in capabilities):
        raise ValueError("capability invokes require ref")
    tools = []
    for tool in _children(root.find("tools"), "tool"):
        ref, permission = tool.get("ref"), tool.get("permission")
        if not ref or permission not in TOOL_PERMISSIONS:
            raise ValueError("each <tool> requires ref and a permission from " + ", ".join(sorted(TOOL_PERMISSIONS)))
        tools.append({"ref": ref, "permissionRequest": permission})

    learning = root.find("learning")
    learning_data = {
        "strategies": [e.get("ref") for e in _children(learning, "strategy")],
        "targets": [e.get("ref") for e in _children(learning, "target")],
        "commitAuthority": [e.get("authority") for e in _children(learning, "commit")],
    }
    phases = []
    for phase in _children(root.find("phases"), "phase"):
        ref = phase.get("ref")
        if ref not in PHASES:
            raise ValueError(f"unknown K'uhul phase: {ref}")
        phases.append({"ref": ref, "action": phase.get("action", "")})

    return {
        "schema": "kuhul.mml.micronaut.v1", "id": agent_id, "name": name,
        "version": root.get("version", "1.0"), "type": root.get("type", "programmable-agent"),
        "program": {"language": program.get("language"), "entry": program.get("entry")},
        "behavior": {"modes": modes}, "vector": {"biases": biases},
        "field": field_data, "memory": memory_data, "capabilities": capabilities,
        "toolRequests": tools, "learning": learning_data, "phases": phases,
        "authority": {"status": "candidate", "toolGrants": [], "execution": "not_admitted"},
    }


def create_candidate(mml_path: Path, candidate_root: Path) -> Path:
    spec = parse_mml(mml_path)
    out = candidate_root / spec["id"]
    if out.exists():
        raise FileExistsError(f"candidate already exists: {out}")
    out.mkdir(parents=True)
    name, agent_id = spec["name"], spec["id"]
    # Inherit the host's configured model profile. The factory must not silently
    # select a different model or endpoint for generated agents.
    profile = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8")).get("daemonAgents", {}).get("daemon-bot", {}).get("modelProfile", {})
    profile = json.loads(json.dumps(profile))
    agent = {
        "schema": "kuhul.daemon-agent.v1", "id": agent_id, "name": name,
        "version": spec["version"], "xaiml": "agent.xaiml",
        "systemPrompt": f"You are {name}, a local Micronaut agent. Tool declarations are requests only; never claim a tool ran unless the host returns a result.",
        "modelProfile": profile,
        "micronaut": "micronaut.mml.json",
        "toolRequests": spec["toolRequests"],
        "patternOrder": [f"agent.{agent_id}.hello", f"agent.{agent_id}.help", f"agent.{agent_id}.identity"],
        "routes": {"reply": f"/api/daemon/agents/{agent_id}/reply", "respond": f"/api/daemon/agents/{agent_id}/respond", "patterns": f"/api/daemon/agents/{agent_id}/patterns"},
        "authority": {"patternMatching": True, "modelInference": "separate-request", "execution": False, "verification": False, "commit": False},
    }
    bank = {
        "format": "kuhul.xaiml.pattern-bank.v1", "version": 1, "name": name,
        "authority": "pattern_match_only",
        "patterns": [
            {"id": f"agent.{agent_id}.hello", "pattern": "HELLO", "phase": "Wo", "template": [{"tag": "text", "value": f"Hello. I'm {name}. Ask HELP to see what I can do."}]},
            {"id": f"agent.{agent_id}.help", "pattern": "HELP", "phase": "Wo", "template": [{"tag": "text", "value": f"I'm {name}. My declared tools and capabilities are requests; the host decides which are available and authorized."}]},
            {"id": f"agent.{agent_id}.identity", "pattern": "WHO ARE YOU", "phase": "Wo", "template": [{"tag": "text", "value": f"I'm {name}, a Micronaut agent defined by MML."}]},
        ],
    }
    (out / "micronaut.mml.xml").write_text(mml_path.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "micronaut.mml.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "agent.json").write_text(json.dumps(agent, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "agent.xaiml").write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "candidate.json").write_text(json.dumps({"status": "candidate", "sourceMml": str(mml_path.resolve()), "agentId": agent_id, "toolGrants": [], "admission": "explicit_host_xcfe"}, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(f"# Candidate Micronaut: {name}\n\nGenerated from MML. This directory is not loaded by the daemon. Tool declarations are permission requests, not grants. Review the MML, agent manifest, and XAIML patterns before explicit admission.\n", encoding="utf-8")
    return out


def admit_candidate(candidate: Path, agents_root: Path) -> Path:
    candidate = candidate.resolve()
    required = [candidate / item for item in ("candidate.json", "micronaut.mml.json", "agent.json", "agent.xaiml")]
    if not all(path.is_file() for path in required):
        raise ValueError("candidate is incomplete")
    marker = json.loads(required[0].read_text(encoding="utf-8"))
    spec = json.loads(required[1].read_text(encoding="utf-8"))
    if marker.get("status") != "candidate" or spec.get("authority", {}).get("status") != "candidate":
        raise ValueError("candidate status is invalid")
    reparsed = parse_mml(candidate / "micronaut.mml.xml")
    if spec != reparsed:
        raise ValueError("normalized candidate does not match its source MML")
    if not isinstance(spec.get("id"), str) or not ID_RE.fullmatch(spec["id"]):
        raise ValueError("candidate has an invalid Micronaut id")
    agent = json.loads(required[2].read_text(encoding="utf-8"))
    bank = json.loads(required[3].read_text(encoding="utf-8"))
    if agent.get("id") != spec.get("id") or bank.get("authority") != "pattern_match_only":
        raise ValueError("candidate identity or XAIML authority mismatch")
    if agent.get("toolRequests") != spec.get("toolRequests"):
        raise ValueError("agent tool requests do not match the MML declaration")
    target = agents_root / spec["id"]
    if target.exists():
        raise FileExistsError(f"live agent already exists: {target}")
    # Admission explicitly changes the lifecycle marker; it still does not grant tools.
    agent["authority"]["execution"] = False
    agent["authority"]["verification"] = False
    agent["authority"]["commit"] = False
    target.mkdir(parents=True)
    for filename in ("agent.json", "agent.xaiml", "micronaut.mml.xml", "micronaut.mml.json", "README.md"):
        shutil.copy2(candidate / filename, target / filename)
    marker["status"] = "admitted_to_daemon_registry"
    marker["toolGrants"] = []
    marker["admittedTo"] = str(target.resolve())
    (target / "admission.json").write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    (candidate / "candidate.json").write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    return target


def create_research_record(record: dict, data_root: Path = ROOT / "micronauts-data") -> Path:
    """Validate and atomically materialize a source-evidence-only query record."""
    if not isinstance(record, dict) or record.get("schema") != RESEARCH_SCHEMA:
        raise ValueError(f"research record schema must be {RESEARCH_SCHEMA}")
    question_id = str(record.get("question_id") or "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", question_id):
        raise ValueError("question_id must be a normalized lowercase query slug")
    if not str(record.get("question") or "").strip():
        raise ValueError("research record requires its original question")
    if record.get("authority") != RESEARCH_AUTHORITY:
        raise ValueError("research records must remain source evidence, not verified facts")
    if record.get("retrieval_status") not in {"retrieved", "unavailable"}:
        raise ValueError("research record has an invalid retrieval_status")
    sources = record.get("sources")
    if not isinstance(sources, list) or len(sources) > 12:
        raise ValueError("research record sources must be an array of at most 12 entries")
    for source in sources:
        if not isinstance(source, dict) or not str(source.get("source") or "").strip():
            raise ValueError("each research source requires a name")
        if not str(source.get("text") or "").strip() or len(source["text"]) > 40_000:
            raise ValueError("each source must contain bounded retrieved text")
        parsed = urlsplit(str(source.get("url") or ""))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("research source URLs must be absolute HTTPS URLs without credentials")
    ngrams = record.get("ngrams")
    if not isinstance(ngrams, dict) or any(not isinstance(ngrams.get(key), list) for key in ("unigram", "bigram", "trigram")):
        raise ValueError("research record requires unigram, bigram, and trigram arrays")

    record = dict(record)
    record["created_by"] = ["Librarian-µ", "Factory-µ"]
    record["factory_materialization"] = {
        "track": "Factory-µ",
        "operation": "create_question_scoped_research_record",
        "admission": "evidence_record_only",
        "path": f"micronauts-data/{question_id}.json",
    }
    data_root.mkdir(parents=True, exist_ok=True)
    target = data_root / f"{question_id}.json"
    fd, temporary = tempfile.mkstemp(prefix=f".{question_id}.", suffix=".tmp", dir=data_root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    # Notify autocomplete only after the evidence record is durable. The event
    # is candidate-only; it does not update dictionary bias or verified facts.
    from micronaut.autocomplete_refresh import notify_research_record
    notify_research_record(target, data_root)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="parse MML and create a DATA_ONLY candidate")
    create.add_argument("mml", type=Path)
    create.add_argument("--candidate-root", type=Path, default=ROOT / "micronaut/generated/candidates/agents")
    listing = sub.add_parser("list-tools", help="discover locally implemented host tools")
    gguf_meta = sub.add_parser("inspect-gguf", help="read, but do not activate, GGUF Micronaut metadata")
    gguf_meta.add_argument("model", type=Path)
    admit = sub.add_parser("admit", help="copy a reviewed candidate into the live daemon registry")
    admit.add_argument("candidate", type=Path)
    admit.add_argument("--agents-root", type=Path, default=ROOT / "micronaut/agents")
    research = sub.add_parser("research-record", help="validate and materialize a retrieved research evidence record from JSON stdin")
    research.add_argument("--data-root", type=Path, default=ROOT / "micronauts-data")
    args = parser.parse_args()
    try:
        if args.command == "create":
            print(create_candidate(args.mml.resolve(), args.candidate_root.resolve()))
        elif args.command == "list-tools":
            from micronaut.tool_bridge import make_local_registry
            print(json.dumps(make_local_registry().discover(), ensure_ascii=False, indent=2))
        elif args.command == "inspect-gguf":
            sys.path.insert(0, str(ROOT / "gguf-py"))
            from gguf.micronaut import read_micronaut_manifest
            print(json.dumps(read_micronaut_manifest(args.model.resolve()), ensure_ascii=False, indent=2))
        elif args.command == "research-record":
            record = json.loads(sys.stdin.read())
            print(create_research_record(record, args.data_root.resolve()))
        else:
            print(admit_candidate(args.candidate, args.agents_root.resolve()))
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"mu-factory: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
