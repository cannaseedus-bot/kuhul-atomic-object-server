# K'UHUL-π — bone + gravity engine

`field/` is a deterministic 3D rigid-body kernel for bone chains and gravity
fields. It owns time, forces, constraints, integration, and hashing. It does
not render and does not fetch anything.

## Files

- `main.py` — load a `%pi` bundle, run N ticks, print per-tick JSON.
- `pi_types.py` — bodies, constraints, events, projections, typed keys, vector
  and quaternion helpers.
- `pi_kernel.py` — locked tick pipeline and hash chain.
- `pi_fields.py` — force compositors: `wind`, `attraction_well`.
- `pi_constraints.py` — soft `spring` forces and rigid `bone` distance constraints.
- `pi_hash.py` — canonical snapshot and SHA-256 seal.
- `pi_symbolic.py` — `⟁tree` → intents (never DOM mutations).
- `attraction_well_spec.json`, `wind_field_spec.json` — field parameter specs.
- `π-bundle.schema.json` — JSON Schema for input bundles.
- `example_bundle.json` — runnable bone-chain demo.
- `test_field_kernel.py` — determinism, gravity, bone, wind, rotation tests.
- `field_composition.py` — deprecated shim; use `pi_fields.py`.
- `semantic_fields.py` — validates the KGF `kgf.semantic-fields/2` key arrays
  and typed relation labels; semantic links remain declarations, not authority.
- `field-distill.py` — creates batched embedding projections and candidate
  similarity links from a semantic-field book. It can use Ollama (Qwen
  `--concept` generation in one request with `think: false` and Gemma embedding
  in one batch) or a local GGUF embedding model. Ollama output is checked against
  the existing neighborhood-attention checkpoint's model and 768 dimensions.
  A different GGUF model is a separate coordinate space and requires an explicit
  `--allow-independent-geometry` flag. Candidate output never rewrites source fields.

## Tick order (locked)

```
step_fields -> step_symbolic_forces -> step_constraints -> step_integrate
            -> step_bones -> step_projection -> step_seal
```

`step_fields` applies gravity, quadratic drag, linear viscous drag, and custom
fields. `step_constraints` applies soft springs and then the rigid bone solver.
`step_integrate` advances translation with semi-implicit Euler and rotation with
quaternion integration. `step_seal` hashes the canonical state and links it to
the previous tick.

## Bundle

```json
{
  "%pi": {
    "world": {
      "gravity": [0, 9.81, 0],
      "air": {"density": 1.225, "viscosity": 0.000018},
      "time": {"dt": 0.0166666667, "substeps": 2},
      "solver": {"integrator": "semi_implicit", "iterations": 8},
      "fields": []
    },
    "bodies": [],
    "constraints": [],
    "events": []
  },
  "⟁tree": {"⟁node": "body", "⟁children": []}
}
```

Bodies accept `position`, `velocity`, `rotation`, `angularVelocity`, `inertia`,
`mass`, `shape`, `size`, `material.drag/friction/restitution`, and `flags`.
`flags: ["static"]` pins a body (mass `0` also works).

## Events

Events are kernel-owned and consumed once:

- `impulse` — `payload.impulse` is added to velocity, divided by mass.
- `attraction` — `payload.force` is added to the force accumulator.
- `torque` — `payload.torque` is added to the torque accumulator.
- `angular_impulse` — `payload.angular_impulse` is added to angular velocity.
- `route_intent` — emitted as an intent; never executed by the kernel.

## Constraints

- `spring` — soft Hooke + damping force (`rest_length`, `stiffness`, `damping`).
- `bone` — rigid distance constraint (`rest_length`, `stiffness`). After
  integration, `solver.iterations` passes move endpoints toward the rest length,
  weighted by inverse mass. Static bodies are pinned.

Bone correction is position-based, so a bone chain stays connected even under
gravity. It runs once before integration (constraint pass) and again after
integration (`step_bones`) so the final projection respects rest length. It is
not a full contact/collision solver.

## Fields

- `wind` — `direction`, `strength`, plus optional `origin`, `radius`, `falloff`
  (`linear` / `quadratic` / `exponential`), `falloff_k`, `turbulence`, and
  `turbulence_seed`. Turbulence is deterministic spatial noise, not RNG.
- `attraction_well` — `position`, `strength`, `radius`, `falloff_power`.

### Semantic key fields

The separate `kgf.semantic-fields/2` format keeps key membership and relation
labels distinct:

```json
{
  "schema": "kgf.semantic-fields/2",
  "fields": {"⟁CAR": ["⟁AUTOMOBILE", "⟁GASOLINE"]},
  "relations": {"⟁CAR": {"⟁GASOLINE": "fuel_option"}}
}
```

`field-distill.py` embeds the unique keys in a single batch and writes
similarity links to a candidate artifact. Existing membership arrays and
authored relation labels are carried through unchanged. A model-generated
field bundle is one Qwen request for the entire bundle, with Ollama `think`
disabled; generated declarations remain candidates for review. The default
`embeddinggemma:latest` model and checkpoint dimension keep vectors in the same
768-dimensional embedding space as `neighborhood-attention.safetensors`.

```powershell
python field/field-distill.py
python field/field-distill.py --concept "CAR" --generator-model qwen3.5:4b
python field/field-distill.py --embedding-backend gguf --embedding-model "C:\Users\canna\.lmstudio\models\lmstudio-community\gemma-3-1B-it-QAT-GGUF\gemma-3-1B-it-QAT-Q4_0.gguf"
```

## Determinism

`pi_hash.canonical_state_snapshot()` stable-sorts bodies and constraints and
rounds floats to 8 decimals. The snapshot includes position, velocity, rotation,
angular velocity, mass, and flags. `step_seal()` computes:

```
tick_hash = sha256({"prev": prev_hash, "snap": snapshot})
```

The chain makes replay differences visible. There is no wall clock, RNG, DOM,
or network in the kernel.

## Run

```bash
python main.py example_bundle.json 5
python test_field_kernel.py
```

Each tick prints one JSON line with `epoch`, `tick`, `tick_hash`, `projection`,
and `intents`.

## Limits

- No collision/contact response; bones are constrained to each other, not to the ground.
- First-order quaternion integration (normalized each step).
- Scalar inertia approximation `m·L²/12` unless `inertia` is supplied.
- The `%pi.memory` typed-key layer is declared in the schema but not yet executed
  by the kernel.
