from __future__ import annotations
import math
from typing import Any, Dict, List, Tuple
from pi_types import (
    PiWorldSpec, PiBody, PiConstraint, PiEvent, PiProjection, PiTickResult,
    Vec3, vadd, vmul, qmul, qnormalize
)
from pi_fields import default_field_compositor
from pi_constraints import solve_springs, solve_bones
from pi_symbolic import extract_symbolic_intents
from pi_hash import canonical_state_snapshot, sha256_json


class PiKernel:
    """
    π-KUHUL Kernel (bone + gravity engine)
    - Owns time advancement
    - Owns physics integration (linear + angular)
    - Owns constraint solving (soft springs + rigid bones)
    - Owns deterministic hashing
    - Does NOT fetch URLs
    - Does NOT project visuals (only emits projection state)
    """
    def __init__(self, world: PiWorldSpec, bodies: List[PiBody], constraints: List[PiConstraint], tree: Dict[str, Any]) -> None:
        if world.integrator != "semi_implicit":
            raise ValueError(
                f"unsupported integrator {world.integrator!r}; only 'semi_implicit' is defined"
            )

        self.world = world
        self.bodies = bodies
        self.constraints = constraints
        self.tree = tree

        self.epoch = 0
        self.tick = 0
        self.prev_hash = "0" * 64

        self.events: List[PiEvent] = []  # kernel-owned event queue
        self.field_comp = default_field_compositor()

        self._bodies_by_id: Dict[str, PiBody] = {b.id: b for b in self.bodies}

        # symbolic scan produces intents (not actions) — this is safe and deterministic
        self.symbolic_intents: List[PiEvent] = extract_symbolic_intents(self.tree)

    def enqueue_event(self, ev: PiEvent) -> None:
        self.events.append(ev)

    # -------------------- Tick Steps (Locked Order) --------------------

    def step_fields(self) -> None:
        fields = self.world.fields
        eta = max(0.0, self.world.air_viscosity)

        for b in self.bodies:
            if b.is_static():
                continue

            # gravity (mass-scaled)
            g = self.world.gravity
            b.force = vadd(b.force, (g[0] * b.mass, g[1] * b.mass, g[2] * b.mass))

            vx, vy, vz = b.velocity

            # quadratic drag
            if self.world.air_density > 0.0:
                speed2 = vx*vx + vy*vy + vz*vz
                drag_mag = 0.5 * self.world.air_density * speed2 * max(0.0, b.drag)
                b.force = vadd(b.force, (-drag_mag * vx, -drag_mag * vy, -drag_mag * vz))

            # linear viscous drag (Stokes-like, characteristic half-extent)
            if eta > 0.0:
                radius = max(b.size) * 0.5 if b.size else 0.5
                coeff = 6.0 * math.pi * eta * radius
                b.force = vadd(b.force, (-coeff * vx, -coeff * vy, -coeff * vz))

            # custom fields (wind, wells, etc.)
            ff = self.field_comp.total_force(fields, b)
            b.force = vadd(b.force, ff)

    def step_symbolic_forces(self) -> None:
        """
        Events -> forces/torque. Kernel-owned. No JS.
        """
        for ev in self.events:
            b = self._bodies_by_id.get(ev.target) if ev.target else None

            if ev.type == "impulse" and b is not None:
                if b.is_static():
                    continue
                imp = ev.payload.get("impulse", [0, 0, 0])
                ix, iy, iz = float(imp[0]), float(imp[1]), float(imp[2])
                if b.mass > 0:
                    b.velocity = (
                        b.velocity[0] + ix / b.mass,
                        b.velocity[1] + iy / b.mass,
                        b.velocity[2] + iz / b.mass,
                    )

            elif ev.type == "attraction" and b is not None:
                if b.is_static():
                    continue
                f = ev.payload.get("force", [0, 0, 0])
                b.force = vadd(b.force, (float(f[0]), float(f[1]), float(f[2])))

            elif ev.type == "torque" and b is not None:
                if b.is_static():
                    continue
                t = ev.payload.get("torque", [0, 0, 0])
                b.torque = vadd(b.torque, (float(t[0]), float(t[1]), float(t[2])))

            elif ev.type == "angular_impulse" and b is not None:
                if b.is_static():
                    continue
                w = ev.payload.get("angular_impulse", [0, 0, 0])
                b.angular_velocity = vadd(b.angular_velocity, (float(w[0]), float(w[1]), float(w[2])))

            # route_intent is emitted as intent; it is NOT executed here.
            # It can be surfaced to higher layers as "available actions".

        self.events = []

    def step_constraints(self) -> None:
        solve_springs(self._bodies_by_id, self.constraints)
        solve_bones(self._bodies_by_id, self.constraints, self.world.solver_iterations)

    def step_bones(self) -> None:
        """Post-integration rigid pass so bones stay connected after moving."""
        solve_bones(self._bodies_by_id, self.constraints, self.world.solver_iterations)

    def step_integrate(self, dt: float) -> None:
        """
        Semi-implicit Euler for translation, quaternion integration for rotation.
        """
        for b in self.bodies:
            if b.is_static():
                b.force = (0.0, 0.0, 0.0)
                b.torque = (0.0, 0.0, 0.0)
                b.angular_velocity = (0.0, 0.0, 0.0)
                continue
            if b.mass <= 0:
                b.force = (0.0, 0.0, 0.0)
                b.torque = (0.0, 0.0, 0.0)
                continue

            ax = b.force[0] / b.mass
            ay = b.force[1] / b.mass
            az = b.force[2] / b.mass

            # v <- v + a dt
            b.velocity = (b.velocity[0] + ax * dt,
                          b.velocity[1] + ay * dt,
                          b.velocity[2] + az * dt)

            # p <- p + v dt
            b.position = (b.position[0] + b.velocity[0] * dt,
                          b.position[1] + b.velocity[1] * dt,
                          b.position[2] + b.velocity[2] * dt)

            # angular: omega <- omega + (torque / I) dt
            inertia = b.moment_of_inertia()
            wx = b.angular_velocity[0] + (b.torque[0] / inertia) * dt
            wy = b.angular_velocity[1] + (b.torque[1] / inertia) * dt
            wz = b.angular_velocity[2] + (b.torque[2] / inertia) * dt

            # light angular damping tied to the material drag coefficient
            damp = max(0.0, 1.0 - max(0.0, b.drag) * dt)
            wx *= damp
            wy *= damp
            wz *= damp

            # q <- normalize(q + 0.5 * (omega_quat * q) * dt)
            dq = qmul((wx, wy, wz, 0.0), b.rotation)
            b.rotation = qnormalize((
                b.rotation[0] + 0.5 * dq[0] * dt,
                b.rotation[1] + 0.5 * dq[1] * dt,
                b.rotation[2] + 0.5 * dq[2] * dt,
                b.rotation[3] + 0.5 * dq[3] * dt,
            ))
            b.angular_velocity = (wx, wy, wz)

            b.force = (0.0, 0.0, 0.0)
            b.torque = (0.0, 0.0, 0.0)

    def step_projection(self) -> PiProjection:
        """
        Output only: CSS-VER reads this. Kernel does not render.
        """
        out: Dict[str, Dict[str, Any]] = {}
        for b in self.bodies:
            out[b.id] = {
                "position": [b.position[0], b.position[1], b.position[2]],
                "rotation": [b.rotation[0], b.rotation[1], b.rotation[2], b.rotation[3]],
                "angular_velocity": [b.angular_velocity[0], b.angular_velocity[1], b.angular_velocity[2]],
                "scale": [1.0, 1.0, 1.0],
                "flags": list(b.flags),
                "@dom_key": b.dom_key,
                "@bind_dom": b.bind_dom,
                "@role": b.role
            }
        return PiProjection(bodies=out)

    def step_seal(self) -> str:
        snap = canonical_state_snapshot(self.epoch, self.tick, self.bodies, self.constraints)
        h = sha256_json({
            "prev": self.prev_hash,
            "snap": snap
        })
        self.prev_hash = h
        return h

    # -------------------- Public API --------------------

    def tick_once(self) -> PiTickResult:
        dt = self.world.dt
        sub = max(1, int(self.world.substeps))
        sub_dt = dt / sub

        for _ in range(sub):
            # LOCKED ORDER
            self.step_fields()
            self.step_symbolic_forces()
            self.step_constraints()
            self.step_integrate(sub_dt)
            self.step_bones()

        proj = self.step_projection()
        previous_hash = self.prev_hash
        h = self.step_seal()

        # advance counters (epoch policy can be tuned later, but kernel-owned)
        self.tick += 1
        if self.tick % 60 == 0:
            self.epoch += 1

        return PiTickResult(
            epoch=self.epoch,
            tick=self.tick,
            projection=proj,
            tick_hash=h,
            prev_hash=previous_hash
        )
