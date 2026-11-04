from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

Vec3 = Tuple[float, float, float]
Quat = Tuple[float, float, float, float]


class PiKeyType(str, Enum):
    """Recognized address classes; none of these classes grants authority."""

    GLYPH = "glyph_key"
    LANE = "lane_key"
    FIELD = "field_key"
    FOLD = "fold_key"
    REPLAY = "replay_key"
    QUERY = "query_key"
    THOUGHT = "thought_key"
    REASONING_ENGINE = "reasoning_engine_key"
    RELATION = "relation_key"
    OPERATION = "operation_key"


@dataclass(frozen=True)
class PiTypedKey:
    """A typed K'UHUL-π address resolved by its key class."""

    key: str
    key_type: PiKeyType
    namespace: Optional[str] = None
    target: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("PiTypedKey.key must be a non-empty address")
        for name, value in (("namespace", self.namespace), ("target", self.target)):
            if value is not None and not value.strip():
                raise ValueError(f"PiTypedKey.{name} must be non-empty when provided")


@dataclass(frozen=True)
class PiQuery:
    """Question/query payload; its address, when needed, is a query_key."""

    text: str
    query_key: Optional[PiTypedKey] = None
    context_keys: Tuple[PiTypedKey, ...] = ()
    intent: str = "retrieve"

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError("PiQuery.text must be non-empty")
        if self.query_key is not None and self.query_key.key_type is not PiKeyType.QUERY:
            raise ValueError("PiQuery.query_key must have type query_key")


@dataclass(frozen=True)
class PiThought:
    """Structured process state for routing a query through candidate folds."""

    thought_key: PiTypedKey
    query: PiQuery
    reasoning_engine_key: Optional[PiTypedKey] = None
    active_fold_keys: Tuple[PiTypedKey, ...] = ()
    candidate_keys: Tuple[PiTypedKey, ...] = ()
    phase: str = "Pop"
    status: str = "candidate"
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.thought_key.key_type is not PiKeyType.THOUGHT:
            raise ValueError("PiThought.thought_key must have type thought_key")
        if self.reasoning_engine_key is not None and self.reasoning_engine_key.key_type is not PiKeyType.REASONING_ENGINE:
            raise ValueError("PiThought.reasoning_engine_key must have type reasoning_engine_key")
        if self.phase not in {"Pop", "Wo", "Yax", "Sek", "Chen", "Ch'en", "Ch_en", "Xul"}:
            raise ValueError("PiThought.phase must be a canonical K'UHUL phase")
        if self.status not in {"candidate", "verified", "closed", "rejected"}:
            raise ValueError("PiThought.status is not a recognized thought state")
        if any(key.key_type is not PiKeyType.FOLD for key in self.active_fold_keys):
            raise ValueError("PiThought.active_fold_keys must contain fold_key values")


@dataclass(frozen=True)
class PiFoldKey:
    """Typed address for a K'UHUL-π memory neighborhood.

    A fold key identifies data and its operation context. It is not an
    execution permission or an XCFE admission token.
    """

    key: str
    family: str
    neighborhood: Optional[str] = None
    key_type: str = field(default="fold_key", init=False)

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("PiFoldKey.key must be a non-empty address")
        if not self.family or not self.family.strip():
            raise ValueError("PiFoldKey.family must be a non-empty family")
        if self.neighborhood is not None and not self.neighborhood.strip():
            raise ValueError("PiFoldKey.neighborhood must be non-empty when provided")

def vadd(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

def vsub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def vmul(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)

def vdot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def vlen(a: Vec3) -> float:
    return (a[0]*a[0] + a[1]*a[1] + a[2]*a[2]) ** 0.5

def vnorm(a: Vec3) -> Vec3:
    L = vlen(a)
    if L <= 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0]/L, a[1]/L, a[2]/L)

def qmul(a: Quat, b: Quat) -> Quat:
    """Hamilton product (a * b)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )

def qnormalize(q: Quat) -> Quat:
    L = (q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3]) ** 0.5
    if L <= 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return (q[0]/L, q[1]/L, q[2]/L, q[3]/L)

@dataclass(frozen=True)
class PiWorldSpec:
    gravity: Vec3 = (0.0, 9.81, 0.0)
    air_density: float = 1.225
    air_viscosity: float = 0.000018
    dt: float = 1.0 / 60.0
    substeps: int = 1
    integrator: str = "semi_implicit"  # locked default
    solver_iterations: int = 8
    fields: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class PiBody:
    id: str
    mass: float = 1.0
    position: Vec3 = (0.0, 0.0, 0.0)
    velocity: Vec3 = (0.0, 0.0, 0.0)
    rotation: Quat = (0.0, 0.0, 0.0, 1.0)
    angular_velocity: Vec3 = (0.0, 0.0, 0.0)
    inertia: Optional[float] = None
    shape: str = "box"
    size: Vec3 = (1.0, 1.0, 0.1)
    friction: float = 0.45
    restitution: float = 0.08
    drag: float = 0.02
    flags: List[str] = field(default_factory=list)

    # bindings (projection only, not authority)
    role: str = "ui.node"
    bind_dom: Optional[str] = None
    dom_key: Optional[str] = None

    # runtime accumulators (π-only)
    force: Vec3 = (0.0, 0.0, 0.0)
    torque: Vec3 = (0.0, 0.0, 0.0)

    def is_static(self) -> bool:
        return "static" in self.flags or self.mass <= 0.0

    def moment_of_inertia(self) -> float:
        """Scalar inertia approximation for a rod/box bone.

        Uses L^2/12 along the longest axis. An explicit ``inertia`` overrides.
        """
        if self.inertia is not None and self.inertia > 0.0:
            return float(self.inertia)
        length = max(self.size) if self.size else 1.0
        return max(1e-9, self.mass * length * length / 12.0)

@dataclass(frozen=True)
class PiConstraint:
    id: str
    type: str  # "spring" (soft) or "bone" (rigid distance)
    a: str
    b: str
    params: Dict[str, Any]

@dataclass
class PiEvent:
    """
    Event bus is kernel-owned: events become forces/torque. No DOM/JS ownership.

    Supported types: impulse, attraction, torque, angular_impulse, route_intent.
    """
    type: str
    target: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PiProjection:
    """
    Read-only output for CSS-VER projection: mapping body_id -> CSS vars or transforms.
    """
    bodies: Dict[str, Dict[str, Any]]

@dataclass
class PiTickResult:
    epoch: int
    tick: int
    projection: PiProjection
    tick_hash: str
    prev_hash: str
