from __future__ import annotations
import json, sys
from typing import Any, Dict, List

from pi_types import PiWorldSpec, PiBody, PiConstraint, PiEvent
from pi_kernel import PiKernel

def load_bundle(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_world(bundle: Dict[str, Any]) -> PiWorldSpec:
    w = (bundle.get("%pi", {}) or {}).get("world", {}) or {}

    gravity = tuple(w.get("gravity", [0, 9.81, 0]))
    air = w.get("air", {}) or {}
    time = w.get("time", {}) or {}
    solver = w.get("solver", {}) or {}

    fields = w.get("fields", []) or []

    return PiWorldSpec(
        gravity=(float(gravity[0]), float(gravity[1]), float(gravity[2])),
        air_density=float(air.get("density", 1.225)),
        air_viscosity=float(air.get("viscosity", 0.000018)),
        dt=float(time.get("dt", 1.0/60.0)),
        substeps=int(time.get("substeps", 1)),
        integrator=str(solver.get("integrator", "semi_implicit")),
        solver_iterations=int(solver.get("iterations", 8)),
        fields=fields
    )

def parse_bodies(bundle: Dict[str, Any]) -> List[PiBody]:
    arr = (bundle.get("%pi", {}) or {}).get("bodies", []) or []
    out: List[PiBody] = []
    for b in arr:
        mat = b.get("material", {}) or {}
        inertia = b.get("inertia")
        out.append(PiBody(
            id=str(b.get("id")),
            mass=float(b.get("mass", 1.0)),
            position=tuple(b.get("position", [0,0,0])),
            velocity=tuple(b.get("velocity", [0,0,0])),
            rotation=tuple(b.get("rotation", [0,0,0,1])),
            angular_velocity=tuple(b.get("angularVelocity", [0,0,0])),
            inertia=(float(inertia) if inertia is not None else None),
            shape=str(b.get("shape", "box")),
            size=tuple(b.get("size", [1,1,0.1])),
            friction=float(mat.get("friction", 0.45)),
            restitution=float(mat.get("restitution", 0.08)),
            drag=float(mat.get("drag", 0.02)),
            flags=list(b.get("flags", [])),
            role=str(b.get("@role", "ui.node")),
            bind_dom=b.get("@bind_dom"),
            dom_key=b.get("@dom_key")
        ))
    return out

def parse_constraints(bundle: Dict[str, Any]) -> List[PiConstraint]:
    arr = (bundle.get("%pi", {}) or {}).get("constraints", []) or []
    out: List[PiConstraint] = []
    for c in arr:
        out.append(PiConstraint(
            id=str(c.get("id")),
            type=str(c.get("type")),
            a=str(c.get("a")),
            b=str(c.get("b")),
            params=dict(c.get("params", {}) or {})
        ))
    return out

def parse_events(bundle: Dict[str, Any]) -> List[PiEvent]:
    """Read kernel-owned events from the bundle (no hardcoded demo impulse)."""
    arr = (bundle.get("%pi", {}) or {}).get("events", []) or []
    out: List[PiEvent] = []
    for e in arr:
        target = e.get("target")
        out.append(PiEvent(
            type=str(e.get("type")),
            target=(str(target) if target is not None else None),
            payload=dict(e.get("payload", {}) or {})
        ))
    return out

def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python main.py <bundle.json> [ticks]")
        return 2

    bundle_path = sys.argv[1]
    ticks = int(sys.argv[2]) if len(sys.argv) >= 3 else 1

    bundle = load_bundle(bundle_path)

    world = parse_world(bundle)
    bodies = parse_bodies(bundle)
    constraints = parse_constraints(bundle)
    tree = bundle.get("⟁tree", {"⟁node": "body", "⟁children": []})

    kernel = PiKernel(world, bodies, constraints, tree)

    for ev in parse_events(bundle):
        kernel.enqueue_event(ev)

    for _ in range(ticks):
        res = kernel.tick_once()
        # emit projection as JSON for CSS-VER consumers
        print(json.dumps({
            "epoch": res.epoch,
            "tick": res.tick,
            "tick_hash": res.tick_hash,
            "projection": res.projection.bodies,
            "intents": [e.__dict__ for e in kernel.symbolic_intents]  # safe: intent list only
        }, ensure_ascii=False))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
