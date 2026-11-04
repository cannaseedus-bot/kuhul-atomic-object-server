from __future__ import annotations
import hashlib, json
from typing import Any, Dict, List, Tuple
from pi_types import PiBody, PiConstraint, Vec3

def _round_vec3(v: Vec3, nd: int = 8) -> Tuple[float, float, float]:
    return (round(v[0], nd), round(v[1], nd), round(v[2], nd))

def _round_quat(q: Tuple[float, float, float, float], nd: int = 8) -> Tuple[float, float, float, float]:
    return (round(q[0], nd), round(q[1], nd), round(q[2], nd), round(q[3], nd))

def canonical_state_snapshot(epoch: int, tick: int, bodies: List[PiBody], constraints: List[PiConstraint]) -> Dict[str, Any]:
    """
    Determinism rules:
    - stable sort
    - rounded floats
    - no non-deterministic fields included
    """
    b = []
    for body in bodies:
        b.append({
            "id": body.id,
            "p": _round_vec3(body.position),
            "v": _round_vec3(body.velocity),
            "r": _round_quat(body.rotation),
            "w": _round_vec3(body.angular_velocity),
            "m": round(body.mass, 8),
            "f": sorted(body.flags),
        })
    b.sort(key=lambda x: x["id"])

    c = []
    for con in constraints:
        c.append({
            "id": con.id,
            "t": con.type,
            "a": con.a,
            "b": con.b,
            "p": con.params  # params are assumed JSON-stable from bundle
        })
    c.sort(key=lambda x: x["id"])

    return {
        "epoch": epoch,
        "tick": tick,
        "bodies": b,
        "constraints": c
    }

def sha256_json(obj: Dict[str, Any]) -> str:
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
