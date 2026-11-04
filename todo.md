# K'UHUL Micronaut Task Board

This is the retrievable task source for `Micronaut.ps1 Todo`, the advisor, and the bounded worker. A task's `files` list is the worker's edit allowlist for that task. The worker records replay events and produces a proposal by default; pass `-Apply` only when edits should be written.

## Active work

- [ ] MN-PI-001 — Implement π fold-key registry and neighborhood lookup backed by candidate JSONL records.
  - files: field/pi_types.py, field/π-bundle.schema.json, manifest.json
- [ ] MN-PI-002 — Add π coordinate projection and relativity scoring adapter for neighborhood attention vectors.
  - files: field/pi_kernel.py, field/pi_types.py, tools/neighborhood_attention.py
- [ ] MN-PI-003 — Document user-request admission checks and preserve XCFE as execution authority.
  - files: micronaut/docs/verifier_rules.md, manifest.json
- [ ] MN-XAIML-001 — Connect query and thought keys to XAIML pattern lookup and replayable memory folds.
  - files: micronaut/daemon_cli.py, micronaut/xaiml/daemon-cli.xaiml, manifest.json
- [ ] MN-FEL-001 — Document the FEL 1.1 replay and verification path and connect it to the manifest task projection.
  - files: manifest.json, micronaut/docs/verifier_rules.md
- [ ] MN-AGENT-001 — Prepare a reviewable π vector-sidecar registry proposal without editing pinned registry authority.
  - files: manifest.json
- [ ] MN-GGL-001 — Connect the GGL transformer tensor-pack contract to replayable Micronaut inference events and distinguish tensor metadata from tensor execution.
  - files: micronaut/docs/ggl/transformers_py_to_ggl_v1.py, manifest.json

## Worker protocol

- One worker run handles one task ID.
- The worker may read repository files, but can edit only files listed under that task and accepted by the worker policy.
- The worker cannot execute shell commands or grant semantic, XCFE, or commit authority.
- Tool calls, file proposals, applied edits, and completion reports are appended to a FEL replay log.
- Replay and verification artifacts are projections and evidence; a model's completion claim does not itself close the task.
