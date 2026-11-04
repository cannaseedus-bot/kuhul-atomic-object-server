#!/usr/bin/env python3
"""Python port of khanary::world::gml_parser + runtime_graph.

Replaces the two C++ units the contract files point at:

    data/grammar/runtime-graph.contracts.json
        "owner": "src/world/runtime_graph.cpp"
        "graph": "data/unfold-graph.gml"

The port covers what the contract actually asserts: GML block parsing, canonical
C6 phase identity at the parser boundary, the 48/120 runtime graph build, the
verify report (RG1-RG4), and the three move kinds (RG5-RG7) including the
Xul -> Pop new-execution boundary.

Authority: a legal edge is a candidate route, never permission. Every move asks
the host admission callback, and an unbound callback denies (RG6).
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

PHASES = ("Pop", "Wo", "Yax", "Sek", "Chen", "Xul")
PHASE_ALIASES = {
    "Pop": "Pop",
    "Wo": "Wo",
    "Yax": "Yax",
    "Sek": "Sek",
    "Chen": "Chen",
    "Ch'en": "Chen",
    "Ch_en": "Chen",
    "CHEN": "Chen",
    "chen": "Chen",
    "Ch\u2019en": "Chen",
    "Xul": "Xul",
}

SEMANTIC_VERB = "@semantic_step"
PHASE_VERB = "@phase_step"


class GmlError(ValueError):
    pass


# ── phase identity at the parser boundary ────────────────────────────────────

def canonical_phase_name(raw: str | None) -> str:
    """One identity for the fifth phase; an unknown token is returned unchanged."""
    if raw is None:
        return ""
    return PHASE_ALIASES.get(raw, raw)


def canonical_phase_index(raw: str | None) -> int:
    """Index in the C6 cycle (Pop=0 .. Xul=5), or -1 for a non-phase token."""
    name = canonical_phase_name(raw)
    return PHASES.index(name) if name in PHASES else -1


# ── GML lexer / parser ───────────────────────────────────────────────────────

_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[\[\]]|[^\s\[\]"]+')
_COMMENT = re.compile(r"\(\*.*?\*\)", re.S)


def _strip_comments(text: str) -> str:
    return _COMMENT.sub(" ", text)


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(_strip_comments(text))


def _scalar(token: str):
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        body = token[1:-1]
        return body.replace('\\"', '"').replace("\\n", "\n")
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


def _parse_block(tokens: Sequence[str], index: int) -> tuple[dict, int]:
    if index >= len(tokens) or tokens[index] != "[":
        raise GmlError(f"expected '[' at token {index}")
    index += 1
    block: dict = {}
    while index < len(tokens) and tokens[index] != "]":
        key = tokens[index]
        index += 1
        if index >= len(tokens):
            raise GmlError(f"key {key!r} has no value")
        if tokens[index] == "[":
            value, index = _parse_block(tokens, index)
            block.setdefault(key, []).append(value)
        else:
            block[key] = _scalar(tokens[index])
            index += 1
    if index >= len(tokens):
        raise GmlError("unterminated block")
    return block, index + 1


def parse_gml(text: str) -> dict:
    """Parse one GML document into {directed, id, label, comment, node[], edge[]}."""
    tokens = _tokenize(text)
    if not tokens:
        raise GmlError("empty GML document")
    if tokens[0] != "graph":
        raise GmlError(f"expected 'graph', got {tokens[0]!r}")
    graph, _ = _parse_block(tokens, 1)
    graph.setdefault("node", [])
    graph.setdefault("edge", [])
    return graph


def parse_gml_file(path: str | Path) -> dict:
    return parse_gml(Path(path).read_text(encoding="utf-8"))


# ── runtime graph ────────────────────────────────────────────────────────────

STATUS_NAMES = (
    "ok",
    "unknown_vertex",
    "not_adjacent",
    "address_unchanged",
    "phase_unchanged",
    "multi_bit_flip",
    "phase_not_forward",
    "wrap_requires_new_execution",
    "unknown_phase",
    "admission_denied",
    "graph_invalid",
)


@dataclass(frozen=True)
class RuntimeVertex:
    id: int = 0
    address: int = 0
    theta: int = 0
    phase: str = ""
    micronaut: str = ""


@dataclass(frozen=True)
class RuntimeEdge:
    source: int = 0
    target: int = 0
    verb: str = ""
    bit: str = ""
    weight: float = 0.0
    is_phase_boundary: bool = False


@dataclass
class GraphMove:
    source: int
    target: int
    new_execution: bool = False

    # C++ names these `from` / `to`; keep both spellings so a ported caller reads
    # naturally in either language.
    @property
    def from_(self) -> int:
        return self.source

    @property
    def to(self) -> int:
        return self.target


@dataclass
class GraphMoveResult:
    status: str = "graph_invalid"
    detail: str = ""
    from_vertex: RuntimeVertex | None = None
    to_vertex: RuntimeVertex | None = None
    admitted: bool = False
    started_new_execution: bool = False

    def ok(self) -> bool:
        return self.status == "ok" and self.admitted


@dataclass
class GraphVerification:
    vertices: int = 0
    edges: int = 0
    semantic_edges: int = 0
    phase_edges: int = 0
    degree_is_five: bool = False
    all_semantic_edges_flip_one_bit: bool = False
    all_phase_edges_step_one: bool = False
    all_vertices_have_canonical_phase: bool = False
    every_address_has_six_phases: bool = False

    def ok(self) -> bool:
        return (
            self.vertices == 48
            and self.edges == 120
            and self.semantic_edges == 72
            and self.phase_edges == 48
            and self.degree_is_five
            and self.all_semantic_edges_flip_one_bit
            and self.all_phase_edges_step_one
            and self.all_vertices_have_canonical_phase
            and self.every_address_has_six_phases
        )


def _popcount3(value: int) -> int:
    return bin(value & 0b111).count("1")


Admission = Callable[[GraphMove, RuntimeEdge], bool]


class RuntimeGraph:
    """G_runtime = Q3 (square) C6 — 48 vertices, 120 edges, degree 5."""

    def __init__(self) -> None:
        self.valid = False
        self.detail = ""
        self._vertices: list[RuntimeVertex] = []
        self._edges: list[RuntimeEdge] = []
        self._by_id: dict[int, RuntimeVertex] = {}
        self._admission: Admission | None = None

    # ── construction ─────────────────────────────────────────────────────────
    @classmethod
    def from_gml(cls, graph: dict) -> "RuntimeGraph":
        result = cls()
        for node in graph.get("node", []):
            raw_phase = node.get("phase")
            b0, b1, b2 = node.get("b0", -1), node.get("b1", -1), node.get("b2", -1)
            address = (
                int(b0) + 2 * int(b1) + 4 * int(b2)
                if min(b0, b1, b2) >= 0
                else int(node.get("id", 0)) // 6
            )
            theta = int(node.get("theta", -1))
            if theta < 0:
                theta = int(node.get("id", 0)) % 6
            phase = canonical_phase_name(raw_phase) if raw_phase is not None else ""
            result._vertices.append(
                RuntimeVertex(
                    id=int(node.get("id", 0)),
                    address=address,
                    theta=theta,
                    phase=phase,
                    micronaut=str(node.get("micronaut", "")),
                )
            )
        if not result._vertices:
            result.detail = "no_vertices"
            return result
        result._by_id = {vertex.id: vertex for vertex in result._vertices}

        for edge in graph.get("edge", []):
            source = result.vertex(int(edge.get("source", 0)))
            target = result.vertex(int(edge.get("target", 0)))
            if source is None or target is None:
                result.detail = f"edge_endpoint_unknown:{edge.get('source')}->{edge.get('target')}"
                result._vertices, result._by_id = [], {}
                return result
            verb = str(edge.get("verb", ""))
            result._edges.append(
                RuntimeEdge(
                    source=source.id,
                    target=target.id,
                    verb=verb,
                    bit=str(edge.get("bit", "")),
                    weight=float(edge.get("weight", 0.0)),
                    is_phase_boundary=verb == PHASE_VERB and source.theta == 5 and target.theta == 0,
                )
            )
        result.valid = True
        return result

    @classmethod
    def load(cls, path: str | Path) -> "RuntimeGraph":
        try:
            graph = parse_gml_file(path)
        except (OSError, GmlError) as exc:
            result = cls()
            result.detail = f"gml_unreadable:{path}:{exc}"
            return result
        return cls.from_gml(graph)

    # ── access ───────────────────────────────────────────────────────────────
    @property
    def vertices(self) -> tuple[RuntimeVertex, ...]:
        return tuple(self._vertices)

    @property
    def edges(self) -> tuple[RuntimeEdge, ...]:
        return tuple(self._edges)

    def vertex(self, vertex_id: int) -> RuntimeVertex | None:
        return self._by_id.get(vertex_id)

    def neighbors(self, vertex_id: int) -> list[RuntimeEdge]:
        return [edge for edge in self._edges if edge.source == vertex_id or edge.target == vertex_id]

    def semantic_degree(self, vertex_id: int) -> int:
        return sum(1 for edge in self.neighbors(vertex_id) if edge.verb == SEMANTIC_VERB)

    def phase_degree(self, vertex_id: int) -> int:
        return sum(1 for edge in self.neighbors(vertex_id) if edge.verb == PHASE_VERB)

    def set_admission(self, admission: Admission | None) -> None:
        self._admission = admission

    # ── verification (RG1-RG4) ───────────────────────────────────────────────
    def verify(self) -> GraphVerification:
        report = GraphVerification(vertices=len(self._vertices), edges=len(self._edges))
        report.semantic_edges = sum(1 for edge in self._edges if edge.verb == SEMANTIC_VERB)
        report.phase_edges = sum(1 for edge in self._edges if edge.verb == PHASE_VERB)

        report.degree_is_five = all(
            len(self.neighbors(vertex.id)) == 5
            and self.semantic_degree(vertex.id) == 3
            and self.phase_degree(vertex.id) == 2
            for vertex in self._vertices
        )

        semantic_ok = phase_ok = True
        for edge in self._edges:
            source, target = self.vertex(edge.source), self.vertex(edge.target)
            if source is None or target is None:
                continue
            if edge.verb == SEMANTIC_VERB:
                if _popcount3(source.address ^ target.address) != 1:
                    semantic_ok = False
                if source.theta != target.theta or source.phase != target.phase:
                    semantic_ok = False
            if edge.verb == PHASE_VERB:
                if (target.theta - source.theta + 6) % 6 not in (1, 5):
                    phase_ok = False
                if source.address != target.address:
                    phase_ok = False
        report.all_semantic_edges_flip_one_bit = semantic_ok
        report.all_phase_edges_step_one = phase_ok

        per_address = [0] * 8
        canonical = True
        in_range = True
        for vertex in self._vertices:
            if canonical_phase_index(vertex.phase) < 0:
                canonical = False
            if not 0 <= vertex.address <= 7:
                in_range = False
                continue
            per_address[vertex.address] += 1
        report.all_vertices_have_canonical_phase = canonical
        report.every_address_has_six_phases = in_range and all(count == 6 for count in per_address)
        return report

    # ── moves (RG5-RG7) ──────────────────────────────────────────────────────
    def _edge_between(self, source: int, target: int, verb: str) -> RuntimeEdge | None:
        for edge in self.neighbors(source):
            other = edge.target if edge.source == source else edge.source
            if other == target and edge.verb == verb:
                return edge
        return None

    def semantic_step(self, move: GraphMove) -> GraphMoveResult:
        result = GraphMoveResult()
        source, target = self.vertex(move.source), self.vertex(move.target)
        if source is None or target is None:
            result.status, result.detail = "unknown_vertex", "vertex_unknown"
            return result
        result.from_vertex, result.to_vertex = source, target

        edge = self._edge_between(move.source, move.target, SEMANTIC_VERB)
        if edge is None:
            result.status = "not_adjacent"
            result.detail = f"no_semantic_edge:{move.source}->{move.target}"
            return result
        flipped = _popcount3(source.address ^ target.address)
        if flipped != 1:
            result.status, result.detail = "multi_bit_flip", f"address_bits_flipped:{flipped}"
            return result
        if source.address == target.address:
            result.status, result.detail = "address_unchanged", "semantic_step_kept_address"
            return result
        if source.phase != target.phase:
            result.status, result.detail = "not_adjacent", "semantic_step_changed_phase"
            return result
        if self._admission is None or not self._admission(move, edge):
            result.status, result.detail = "admission_denied", "admission_denied"
            return result
        result.admitted, result.status, result.detail = True, "ok", "semantic_step"
        return result

    def phase_step(self, move: GraphMove) -> GraphMoveResult:
        result = GraphMoveResult()
        source, target = self.vertex(move.source), self.vertex(move.target)
        if source is None or target is None:
            result.status, result.detail = "unknown_vertex", "vertex_unknown"
            return result
        result.from_vertex, result.to_vertex = source, target

        edge = self._edge_between(move.source, move.target, PHASE_VERB)
        if edge is None:
            result.status = "not_adjacent"
            result.detail = f"no_phase_edge:{move.source}->{move.target}"
            return result
        if source.address != target.address:
            result.status = "phase_not_forward"
            result.detail = "phase_step_changed_address"
            return result
        from_index = canonical_phase_index(source.phase)
        to_index = canonical_phase_index(target.phase)
        if from_index < 0 or to_index < 0:
            result.status = "unknown_phase"
            result.detail = f"unknown_phase:{source.phase}->{target.phase}"
            return result
        if from_index == to_index:
            result.status, result.detail = "phase_unchanged", "phase_step_kept_phase"
            return result

        forward = to_index == from_index + 1
        wrap = from_index == 5 and to_index == 0
        if wrap:
            if not move.new_execution:
                result.status = "wrap_requires_new_execution"
                result.detail = f"wrap_requires_new_execution:{source.phase}->{target.phase}"
                return result
            result.started_new_execution = True
        elif not forward:
            result.status = "phase_not_forward"
            result.detail = f"phase_not_forward:{source.phase}->{target.phase}"
            return result

        if not edge.is_phase_boundary and edge.source != move.source:
            result.status, result.detail = "phase_not_forward", "phase_edge_reversed"
            return result
        if self._admission is None or not self._admission(move, edge):
            result.status, result.detail = "admission_denied", "admission_denied"
            return result
        result.admitted = True
        result.status = "ok"
        result.detail = "phase_step_new_execution" if result.started_new_execution else "phase_step"
        return result

    def composite(self, moves: Iterable[GraphMove]) -> dict:
        moves = list(moves)
        if not moves:
            return {"status": "ok", "detail": "no_moves", "visited": []}
        visited = [moves[0].source]
        for move in moves:
            if self.vertex(move.source) is None or self.vertex(move.target) is None:
                return {"status": "unknown_vertex", "detail": "vertex_unknown", "visited": visited}
            kinds = {
                edge.verb
                for edge in self.neighbors(move.source)
                if (edge.target if edge.source == move.source else edge.source) == move.target
            }
            if SEMANTIC_VERB in kinds:
                step = self.semantic_step(move)
            elif PHASE_VERB in kinds:
                step = self.phase_step(move)
            else:
                return {
                    "status": "not_adjacent",
                    "detail": f"no_edge:{move.source}->{move.target}",
                    "visited": visited,
                }
            if not step.ok():
                return {"status": step.status, "detail": step.detail, "visited": visited}
            visited.append(move.target)
        return {"status": "ok", "detail": "composite_walk", "visited": visited}


def _summary(graph: RuntimeGraph) -> dict:
    report = graph.verify()
    return {
        "valid": graph.valid,
        "detail": graph.detail,
        "vertices": report.vertices,
        "edges": report.edges,
        "semantic_edges": report.semantic_edges,
        "phase_edges": report.phase_edges,
        "degree_is_five": report.degree_is_five,
        "all_semantic_edges_flip_one_bit": report.all_semantic_edges_flip_one_bit,
        "all_phase_edges_step_one": report.all_phase_edges_step_one,
        "all_vertices_have_canonical_phase": report.all_vertices_have_canonical_phase,
        "every_address_has_six_phases": report.every_address_has_six_phases,
        "ok": report.ok(),
    }


def _selftest(graph_path: Path) -> int:
    graph = RuntimeGraph.load(graph_path)
    assert graph.valid, graph.detail
    report = graph.verify()
    assert report.vertices == 48, report.vertices
    assert report.edges == 120, report.edges
    assert (report.semantic_edges, report.phase_edges) == (72, 48)
    assert report.degree_is_five and report.ok(), _summary(graph)

    # Phase identity: punctuation is not load-bearing. Every spelling collapses
    # to one canonical form, "Chen"; Ch'en survives as accepted input only.
    for spelling in ("Chen", "Ch'en", "Ch_en", "CHEN", "chen", "Ch\u2019en"):
        assert canonical_phase_name(spelling) == "Chen", spelling
    assert canonical_phase_index("Ch'en") == 4
    assert canonical_phase_index("Ch_en") == 4
    assert canonical_phase_name("Chens") == "Chens"  # a typo never becomes a phase

    # RG6: topology is not permission.
    assert graph.semantic_step(GraphMove(0, 6)).status == "admission_denied"
    graph.set_admission(lambda move, edge: True)
    assert graph.semantic_step(GraphMove(0, 6)).status == "ok"
    assert graph.semantic_step(GraphMove(0, 6)).detail == "semantic_step"

    # RG2: a semantic step flips exactly one address bit and keeps the phase.
    assert graph.semantic_step(GraphMove(0, 1)).status == "not_adjacent"

    # RG3/RG5: phase steps move one C6 step forward; the wrap needs a new execution.
    assert graph.phase_step(GraphMove(0, 1)).status == "ok"
    wrap = graph.phase_step(GraphMove(5, 0))
    assert wrap.status == "wrap_requires_new_execution", wrap.status
    new_run = graph.phase_step(GraphMove(5, 0, new_execution=True))
    assert new_run.status == "ok" and new_run.started_new_execution
    assert graph.phase_step(GraphMove(1, 0)).status == "phase_not_forward"

    # Composite: two legal atomic moves, each admitted separately.
    walk = graph.composite([GraphMove(0, 6), GraphMove(6, 18)])
    assert walk["status"] == "ok" and walk["visited"] == [0, 6, 18], walk

    print("kuhul_world selftest: ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, help="runtime graph GML path")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument(
        "--default",
        type=Path,
        default=Path("vendor/key-grammar-kit/data/unfold-graph.gml"),
        help="graph used by --selftest",
    )
    args = parser.parse_args()

    if args.selftest:
        return _selftest(args.graph or args.default)
    if not args.graph:
        parser.error("--graph is required unless --selftest is used")

    graph = RuntimeGraph.load(args.graph)
    summary = _summary(graph)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"graph: {args.graph}")
        for key, value in summary.items():
            print(f"  {key}: {value}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())