"""Deterministic tests for the π bone + gravity kernel.

Run:
    python test_field_kernel.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pi_types import PiWorldSpec, PiBody, PiConstraint, PiEvent, vsub, vlen
from pi_kernel import PiKernel
from pi_fields import calc_wind


HERE = Path(__file__).resolve().parent


def make_world(**overrides) -> PiWorldSpec:
    values = dict(
        gravity=(0.0, 9.81, 0.0),
        air_density=0.0,
        air_viscosity=0.0,
        dt=1.0 / 60.0,
        substeps=1,
        integrator="semi_implicit",
        solver_iterations=8,
        fields=[],
    )
    values.update(overrides)
    return PiWorldSpec(**values)


def test_gravity() -> None:
    body = PiBody(id="b", mass=1.0)
    kernel = PiKernel(make_world(), [body], [], {})
    kernel.tick_once()
    assert body.velocity[1] > 0.0
    assert body.position[1] > 0.0


def test_bone_holds_distance() -> None:
    root = PiBody(id="root", mass=0.0, position=(0.0, 0.0, 0.0), flags=["static"])
    bone = PiBody(id="bone", mass=1.0, position=(0.0, 1.0, 0.0), drag=0.0)
    joint = PiConstraint("j", "bone", "root", "bone", {"rest_length": 1.0, "stiffness": 1.0})

    kernel = PiKernel(make_world(gravity=(0.0, 0.0, 0.0)), [root, bone], [joint], {})
    kernel.enqueue_event(PiEvent("impulse", "bone", {"impulse": [1.0, 0.0, 0.0]}))

    for _ in range(120):
        kernel.tick_once()

    distance = vlen(vsub(bone.position, root.position))
    assert abs(distance - 1.0) < 1e-6, distance


def test_wind_falloff_and_turbulence() -> None:
    body = PiBody(id="b", position=(5.0, 0.0, 0.0), drag=0.0)
    params = {
        "direction": [1.0, 0.0, 0.0],
        "strength": 1.0,
        "origin": [0.0, 0.0, 0.0],
        "radius": 10.0,
        "falloff": "linear",
        "turbulence": 0.0,
    }

    force = calc_wind(params, body)
    assert abs(force[0] - 0.5) < 1e-12, force

    body.position = (10.0, 0.0, 0.0)
    assert calc_wind(params, body) == (0.0, 0.0, 0.0)

    params["falloff"] = "quadratic"
    body.position = (5.0, 0.0, 0.0)
    assert abs(calc_wind(params, body)[0] - 0.25) < 1e-12

    params["falloff"] = "linear"
    params["turbulence"] = 0.2
    body.position = (5.0, 0.0, 0.0)
    noisy_a = calc_wind(params, body)
    noisy_b = calc_wind(params, body)
    assert noisy_a == noisy_b, "turbulence must be deterministic"
    assert noisy_a != force, "turbulence should perturb the direction"


def test_rotation_integration() -> None:
    body = PiBody(id="b", mass=1.0, inertia=1.0, drag=0.0)
    kernel = PiKernel(make_world(gravity=(0.0, 0.0, 0.0)), [body], [], {})
    kernel.enqueue_event(PiEvent("torque", "b", {"torque": [0.0, 0.0, 1.0]}))
    kernel.tick_once()

    assert body.angular_velocity[2] > 0.0
    norm = sum(value * value for value in body.rotation) ** 0.5
    assert abs(norm - 1.0) < 1e-12, norm
    assert body.rotation != (0.0, 0.0, 0.0, 1.0)


def test_hash_chain_and_determinism() -> None:
    def build():
        root = PiBody(id="root", mass=0.0, position=(0.0, 0.0, 0.0), flags=["static"])
        bone = PiBody(id="bone", mass=1.0, position=(0.0, 1.0, 0.0), drag=0.01)
        joint = PiConstraint("j", "bone", "root", "bone", {"rest_length": 1.0, "stiffness": 1.0})
        world = make_world(
            fields=[{
                "field_type": "wind",
                "parameters": {"direction": [1, 0, 0], "strength": 0.5, "turbulence": 0.1},
            }],
        )
        return PiKernel(world, [root, bone], [joint], {})

    first = build()
    second = build()

    hashes_a = []
    hashes_b = []
    for _ in range(30):
        a = first.tick_once()
        b = second.tick_once()
        hashes_a.append(a.tick_hash)
        hashes_b.append(b.tick_hash)
        assert a.prev_hash == b.prev_hash
        assert a.projection == b.projection

    assert hashes_a == hashes_b, "same inputs must produce the same tick chain"
    assert len(set(hashes_a)) == len(hashes_a), "each tick must seal differently"

    assert hashes_a[1] != hashes_a[0]


def test_example_bundle_runs() -> None:
    output = subprocess.check_output(
        [sys.executable, "main.py", "example_bundle.json", "3"],
        cwd=str(HERE),
        text=True,
    )
    lines = [json.loads(line) for line in output.splitlines() if line.strip()]
    assert len(lines) == 3
    assert lines[0]["tick"] == 1
    assert "projection" in lines[0]
    assert "tick_hash" in lines[0]


def main() -> None:
    test_gravity()
    test_bone_holds_distance()
    test_wind_falloff_and_turbulence()
    test_rotation_integration()
    test_hash_chain_and_determinism()
    test_example_bundle_runs()
    print("PI FIELD KERNEL TESTS PASS")


if __name__ == "__main__":
    main()
