from __future__ import annotations
import math
from typing import Any, Callable, Dict, List
from pi_types import PiBody, Vec3, vadd, vmul, vnorm

FieldCalc = Callable[[Dict[str, Any], PiBody], Vec3]

class PiFieldCompositor:
    """
    Pure force resolution.
    - No DOM
    - No time ownership
    - No state mutation beyond returning vectors
    """
    def __init__(self) -> None:
        self._calcs: Dict[str, FieldCalc] = {}

    def register(self, field_type: str, calc: FieldCalc) -> None:
        self._calcs[field_type] = calc

    def total_force(self, fields: List[Dict[str, Any]], body: PiBody) -> Vec3:
        total: Vec3 = (0.0, 0.0, 0.0)
        for f in fields:
            ft = f.get("field_type")
            params = f.get("parameters", {})
            calc = self._calcs.get(ft)
            if not calc:
                continue
            total = vadd(total, calc(params, body))
        return total


def _falloff_scale(falloff: str, distance: float, radius: float, k: float) -> float:
    """Deterministic radial falloff in [0, 1]. radius <= 0 disables falloff."""
    if radius is None or radius <= 0.0:
        return 1.0
    t = max(0.0, min(1.0, distance / radius))
    if falloff == "linear":
        return 1.0 - t
    if falloff == "quadratic":
        return (1.0 - t) * (1.0 - t)
    if falloff == "exponential":
        # Asymptotic: exp(-k) at the radius, not exactly zero.
        return math.exp(-max(0.0, k) * t)
    return 1.0


def _turbulence(position: Vec3, turbulence: float, seed: float) -> Vec3:
    """Deterministic spatial noise in [-turbulence, turbulence] per axis."""
    x, y, z = position
    n1 = math.sin(x * 12.9898 + y * 78.233 + z * 37.719 + seed)
    n2 = math.sin(x * 39.346 + y * 11.135 + z * 83.155 + seed * 1.7)
    n3 = math.sin(x * 73.156 + y * 52.235 + z * 9.151 + seed * 2.3)
    return (n1 * turbulence, n2 * turbulence, n3 * turbulence)


def calc_wind(params: Dict[str, Any], body: PiBody) -> Vec3:
    if body.is_static():
        return (0.0, 0.0, 0.0)

    direction = params.get("direction", [1, 0, 0])
    d = vnorm((float(direction[0]), float(direction[1]), float(direction[2])))
    if d == (0.0, 0.0, 0.0):
        return (0.0, 0.0, 0.0)

    strength = float(params.get("strength", 0.5))

    # Radial falloff from an optional origin.
    origin = params.get("origin", [0.0, 0.0, 0.0])
    dx = body.position[0] - float(origin[0])
    dy = body.position[1] - float(origin[1])
    dz = body.position[2] - float(origin[2])
    distance = (dx * dx + dy * dy + dz * dz) ** 0.5
    radius = float(params.get("radius", 0.0))
    falloff = str(params.get("falloff", "linear"))
    falloff_k = float(params.get("falloff_k", 3.0))
    scale = _falloff_scale(falloff, distance, radius, falloff_k)

    # Deterministic spatial turbulence (no RNG, no clock).
    turbulence = max(0.0, min(1.0, float(params.get("turbulence", 0.0))))
    if turbulence > 0.0:
        seed = float(params.get("turbulence_seed", 0.0))
        d = vnorm(vadd(d, _turbulence(body.position, turbulence, seed)))

    # Drag scales the wind effect slightly (still "field", not "material").
    drag_scale = max(0.0, 1.0 - min(1.0, body.drag))
    s = strength * scale * drag_scale
    return vmul(d, s)


def calc_attraction_well(params: Dict[str, Any], body: PiBody) -> Vec3:
    if body.is_static():
        return (0.0, 0.0, 0.0)
    cx, cy, cz = params.get("position", [0, 0, 0])
    strength = float(params.get("strength", 2.0))
    radius = float(params.get("radius", 5.0))
    power = float(params.get("falloff_power", 2.0))

    dx = float(cx) - body.position[0]
    dy = float(cy) - body.position[1]
    dz = float(cz) - body.position[2]
    dist = (dx*dx + dy*dy + dz*dz) ** 0.5
    if dist <= 1e-6 or dist > radius:
        return (0.0, 0.0, 0.0)

    # normalized distance in (0,1]
    nd = max(1e-3, dist / radius)
    mag = strength * (1.0 / (nd ** power))
    d = vnorm((dx, dy, dz))
    return vmul(d, mag)


def default_field_compositor() -> PiFieldCompositor:
    comp = PiFieldCompositor()
    comp.register("wind", calc_wind)
    comp.register("attraction_well", calc_attraction_well)
    return comp
