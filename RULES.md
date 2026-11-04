# RULES

Normative. Where this file and any other document disagree, this file wins.
Where this file and a checker disagree, the checker is the bug.

Companions:

- `Weights-Bias.md` — why the pipeline is shaped this way (explanatory, not binding)
- `vendor/key-grammar-kit/data/grammar/*.kgf` — declared contracts, parsed at load
- `vendor/key-grammar-kit/data/bias.gml`, `wildcard.gml` — declared topology, parsed at load
- `flat/README.md` — the two deployments and why they must not be mixed

Each rule names the artifact that enforces it and the check that proves it.
A rule with no check is a comment, not a rule.

## A. Authority

1. **A score ranks; it never admits.**
   Owner: `micronaut/learning_lane.py` · Check: `test_commit_requires_all_four_authorities`

2. **Persistence needs four independent facts**, asserted separately: admission,
   Sek authority, Ch'en verification, Xul closure. No single flag substitutes for
   the set.
   Owner: `LearningLane.commit` · Check: `test_commit_requires_all_four_authorities`, `test_commit_requires_admission`

3. **A failing verification report blocks the commit before the four flags are read.**
   Owner: `LearningLane.commit(verification=...)` · Check: `test_failed_verification_blocks_commit`

4. **Xul closes proposals; only the learning lane's Xul may persist.** Gradient and
   parameter-mapping lanes close a proposal fold and record
   `persist_authorized: false`.
   Owner: `gradient_lane.propose`, `parameter_mapping_lane.propose` · Check: `test_xul_does_not_persist`

5. **Topology is not permission.** A legal edge is a candidate route; the admission
   callback decides, and an unbound callback denies.
   Owner: `tools/kuhul_world.py` · Check: `micronaut/test_graph_topology.py`, `python tools/kuhul_world.py --selftest`

6. **A mode narrows; it never grants.** Modes filter selection and are recorded as
   narrowing only.

## B. Scoring

7. **`S_base = W * C * R`**, verified against `SCORE_RULE`, never recomputed and
   never corrected. A mismatch is refused, not fixed.
   Owner: `WCRFoldAccumulator.fold` · Check: `test_rejects_a_forged_score`

8. **`G` is authority, not magnitude.** Accepts `True/False/0/1`; a fractional value
   is an attenuation error, not a weight.
   Owner: `gate_of` · Check: `test_fractional_gate_is_rejected`, `test_binary_float_gate`

9. **`S_effective = S_base * G` is recorded, never substituted** for `S_base`.

10. **Confidence `C` is evidence-derived**, never usage-derived. `C` and `R` are in
    `[0, 1]`.
    Owner: `WCRFoldAccumulator.fold` · Check: `test_rejects_confidence_outside_unit_interval`

11. **`R` is relevance.** In `student.py` it is structural coverage of the utterance,
    not embedding similarity, and the record says so (`score_kind`).

## C. Learning

12. **`delta = learning_rate * gradient`.** `eta` comes from the kGF; no default
    gradient is invented. A candidate without a gradient learns nothing.
    Owner: `learning_lane` contract, `WCRFoldAccumulator.fold` · Check: `test_missing_gradient_means_no_learning`, `test_tampered_delta_fails_verification`

13. **`gradient = target - prediction`**, both probabilities in `[0, 1]`.
    Owner: `micronaut/gradient_lane.py` · Check: `test_gradient_is_target_minus_prediction`, `test_rejects_out_of_range_inputs`

14. **`dtheta_j = eta * sum_i e_i * f_ij`.** The feature mapping is supplied; it is
    never inferred from the candidate set.
    Owner: `ParameterMappingLane` · Check: `test_shared_column_accumulates`

15. **Updates are bounded**: `|delta| <= MAX_STEP`, checked before Ch'en and again
    during verification.
    Owner: `parameter_mapping_lane` · Check: `test_bounds_refuse_an_oversized_step`, `test_out_of_bounds_record_fails_verification`

16. **The corpus prior is immutable.** `corpus_prior` is never a learning target, and
    a family/target mismatch is refused at load.
    Owner: `MappingContract.load` · Check: `test_rejects_the_immutable_corpus_prior_as_a_family`, `test_rejects_a_family_target_mismatch`

17. **Ordinary online learning writes `W_learned`.** Other families (`W_vector`,
    `W_graph`) require their own declared mapping.

18. **Feedback sources are not averaged.** Each source declares its own rule; two
    different derivatives do not combine into a gradient of anything.

## D. Storage

19. **Storage identity is the logical proposal**, not the delivery attempt:
    `key = sha256([principal, workspace, proposal_id])`.
    Owner: `LearningLane.commit` · Check: `test_key_is_derived_from_provenance`

20. **Replay with an identical payload inserts nothing** and reports
    `inserted: false`.
    Check: `test_replay_with_same_payload_is_idempotent`

21. **Reusing a key with a different payload is refused**, never merged.
    Check: `test_reused_key_with_different_payload_is_refused`

22. **The projection is the bias.** It is reconstructed from committed events in key
    order; there is no separately mutable bias tensor.
    Check: `test_projection_survives_a_new_store_instance`

23. **Connections are closed.** A `sqlite3` connection opened for a request is closed
    on every path.
    Owner: `SQLiteLearningStore._db`

## E. Topology

24. **The runtime graph is Q3 ☐ C6**: 48 vertices, 120 edges, 72 semantic, 48 phase,
    degree 5 at every vertex.
    Owner: `RuntimeGraph.verify` · Check: `python tools/kuhul_world.py --selftest`

25. **A semantic step flips exactly one address bit and keeps the phase.**

26. **A phase step advances one C6 step.** The `Xul -> Pop` wrap requires
    `new_execution`; without it the move is refused, not silently allowed.
    Check: `micronaut/test_graph_topology.py` (phase wrap)

27. **Phase identity is single-valued**: `Chen`, `Ch_en`, `Ch'en` are one phase,
    canonicalised at the parser boundary. A near-miss stays a near-miss.
    Owner: `canonical_phase_name` · Check: `kuhul_world --selftest`

28. **A graph that disagrees with its matcher fails to load.** A `matches` edge must
    produce its declared capture, a `suffix` edge must be a real tail, a `generalizes`
    edge must actually generalize.
    Owner: `micronaut/wildcard_graph.py` · Check: `micronaut/test_graph_topology.py` (wildcard cases)

29. **A feature edge may not target a `corpus_prior`**, and graph family, target and
    `max_step` must agree with the kGF.
    Owner: `micronaut/bias_graph.py` · Check: `micronaut/test_graph_topology.py` (bias graph cases)

## F. Execution

30. **Every executor resolves in-stack.** No subprocess, no loopback HTTP, no external
    executable.
    Owner: `data/host/executor-bindings.json` · Check: `vendor\key-grammar-kit\check_executor_bindings.py`

31. **An unavailable capability states why.** Silence is not a capability.
    Check: `check_executor_bindings.py` (unavailable requires a reason)

32. **Legacy identifiers are aliases, not calls.** Resolution consults the alias
    table and spawns nothing.

33. **`data/gram` is content**, not binding declarations. Generated corpora are exempt
    from the binary scan; manifests and schemas are not.

## G. Declarations

34. **Declarations are parsed, not assumed.** Family, target, rule, learning rate,
    maximum step, lane mode, commit phase and program phase order are read from the
    kGF and refused on mismatch.
    Owner: `KGFContract.load`, `MappingContract.load`, `GradientContract.load`

35. **Omitted declarations take the strict default; declared ones must match exactly.**
    Check: `test_declarations_are_optional`, `test_rejects_a_wrong_declared_score_rule`

36. **Phase order is exactly `Yax, Sek, Ch'en, Xul`** for the learning, gradient and
    mapping lanes. Adding a stage is a contract change, not a code change.

37. **Every kGF is validated by the kit's own checker** before it is considered
    declarative.
    Check: `vendor\key-grammar-kit\test.bat`

## H. Deployments

38. **Two lanes exist and do not mix.** `flat/` uses `delta = G`; `micronaut/` uses
    `delta = eta * gradient`. A proposal built for one is refused or double-applied by
    the other.

39. **A deployment states which lane it uses.** Silence is an ambiguity, and the two
    share a contract name.

## I. Change control

If you change a declaration, change its consumer in the same commit:

- `SCORE_RULE` → `WCRFoldAccumulator.fold`, `LearningLane.verify`
- `GATE_TYPE` → `gate_of`
- `LEARNING_RATE` / `DELTA_RULE` → `fold`, `verify`
- `MAX_STEP` → `apply_learning_rate` bounds check
- `PARAMETER_FAMILY` / `UPDATE_TARGET` → `MappingContract.load`, `bias.gml`
- phase order in any kGF → its `program` lines and the loader's expected tuple
- a new `.kgf` → `check_2d_key_graph_execution_field.py` `KGF_FILES` and the manifest

A rule may be relaxed only by deleting it here first, with the reason recorded. A
checker may not be relaxed to make a rule pass; if a rule and a checker disagree, the
checker is the bug.

## Gate

```
vendor\key-grammar-kit\test.bat
python -m unittest micronaut.test_graph_topology micronaut.test_parameter_mapping_lane ^
  micronaut.test_gradient_lane micronaut.test_learning_lane ^
  micronaut.test_learning_lane_durable micronaut.test_student micronaut.test_pi_learning
python flat\test_learning_lane_durable.py
```

Expected: 7 PASS checks plus 16 track tests from the kit, 111 unit tests, and 1
standalone deployment test. `SKIP | K'UHUL source sync` is environmental — the
KHANARY runtime tree is not part of this workspace.