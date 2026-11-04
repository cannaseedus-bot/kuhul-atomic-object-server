# Weights, Bias, and the Learning Signal

This document describes how a score becomes a proposal, how a proposal becomes
a persisted bias delta, and where each step is allowed to say no.

It covers `micronaut/student.py`, `micronaut/predictive_field.py`,
`micronaut/gradient_lane.py`, `micronaut/parameter_mapping_lane.py`,
`micronaut/learning_lane.py`, and the kGF files under
`vendor/key-grammar-kit/data/grammar/` that declare their contracts:
`learning-lane.kgf`, `gradient-lane.kgf`, `parameter-mapping.kgf`,
`runtime-graph.contracts.json`, and the fold tensor map.

Normative rules live in `RULES.md`; this file explains the reasoning behind them.

## Three quantities, three contracts

These look similar and are not interchangeable. Most of the design exists to
keep them apart.

```
S_base      = W * C * R          ranking score
S_effective = S_base * G         gate-weighted ranking
delta       = eta * gradient     learning mutation
```

- `W` weight — a selection prior, set by the scoring caller.
- `C` confidence — evidence-derived. Never derived from usage.
- `R` relativity — relevance. In `student.py` it is structural coverage of the
  utterance; in an embedding path it would be cosine similarity.
- `G` gate — **authority only**. Binary. Not a magnitude.
- `S` score — what ranks a candidate. Never what admits it.
- `eta` learning rate — declared in the kGF, not passed per call.
- `gradient` — a signed error signal from a `GradientLane`.
- `delta` — the resulting weight change, and the only thing the store sums.

## Where each is enforced

- `S_base` — `WCRFoldAccumulator.fold` refuses `abs(S - W*C*R) > 1e-9`.
- `G` — `gate_of` accepts `True/False/0/1` and refuses anything between.
- `delta` — `LearningLane.verify` refuses `abs(delta - eta*gradient) > 1e-9`.
- `eta` — `KGFContract.load` reads `LEARNING_RATE` (0.05 today).
- rule names — both loaders refuse an unsupported declaration.
- persistence — `LearningLane.commit` requires four flags plus an optional Ch'en report.

## The pipeline

```
STUDENT-µ / PredictiveField        produce W, C, R, G, S
        |
        v
GradientLane                       produce signed error from feedback
   Pop -> Wo -> Yax -> Sek -> Ch'en -> Xul
        |                            closes a PROPOSAL, not a transaction
        v
ParameterMappingLane               error + declared features -> per-parameter dW
   Yax map -> Sek select -> Ch'en verify bounds -> Xul close
        |                            still a proposal
        v
LearningLane                       fold score + delta, verify, gate
   Yax propose -> Sek accumulate -> Ch'en verify -> Xul close
        |
        v
SQLiteLearningStore                idempotent commit, then projection
```

`GradientLane`'s Xul closes a proposal fold. It holds no mutation authority and
writes nothing. `LearningLane`'s Xul is the point where persistence becomes
possible, and only when the host asserts four separate facts.

## The score rule

`SCORE_RULE = "W*C*R"`, declared in `learning-lane.kgf` and re-checked at Ch'en.

The accumulator does not recompute the score and does not correct it. It
verifies that the supplied score matches the declared rule and refuses
otherwise:

```
score_rule_mismatch: W*C*R = 0.504000, supplied S = 0.900000
```

This is deliberate. Recomputing would hide a caller that ranks by one rule and
learns by another; refusing forces the discrepancy into the open.

`student.py` emits `S = W*C*R` with `G` recorded alongside. The gate is not
folded into the score, because a gate-weighted score cannot be checked against
`W*C*R` afterwards.

## The gate

`G` answers one question: may this count? It does not answer "how much".

```python
gate_of(True)   == 1.0
gate_of(1.0)    == 1.0
gate_of(0.05)   -> ContractError
```

The error is explicit: *G is an authority gate and must be 0 or 1; use an
explicit learning_rate or attenuation for fractional weighting.* A fractional
gate is almost always a learning rate that has been stuffed into the wrong
field, and allowing it silently would let an authority signal double as a
magnitude.

`S_effective = S_base * G` is recorded for any consumer that wants gate-weighted
ranking. The lane itself does not rank; ordering happens upstream.

## The delta rule

`DELTA_RULE = "learning_rate*gradient"`.

`eta` comes from the kGF (`LEARNING_RATE 0.05`). `gradient` comes from the
candidate, normally supplied by `GradientLane`. With no gradient the delta is
`0.0` — the candidate ranks and learns nothing. There is no default derivative.

`GradientLane` derives the signal from prediction feedback:

```
gradient = target - prediction
delta    = learning_rate * gradient
```

Both inputs are probabilities in `[0,1]`. A target of `1.0` against a prediction
of `0.30` gives `gradient 0.70` and, at `eta 0.05`, `delta 0.035`.

This is a signed error, not a derivative with respect to every n-gram weight.
For a full softmax over a candidate set the per-candidate signal is `y_i - p_i`,
and the parameter-level gradient follows from whichever parameters the field
actually trains. That mapping is not implemented here and is not claimed.

Each feedback source gets its own lane and its own rule. Prediction feedback,
XCFE outcomes, replay retention and Question Engine answers do not produce the
same derivative and must not be averaged into one.

## Parameter mapping

`RULE = "softmax_feature_gradient"`, declared in `parameter-mapping.kgf`.

GradientLane supplies one signed error per candidate. ParameterMappingLane
turns that into per-parameter updates:

    e_i      = y_i - p_i
    dtheta_j = eta * sum_i e_i * f_ij

`f` comes from `bias.gml`, one feature row per observation. The lane sums the
error-weighted columns and refuses to invent a feature mapping. A feature that
addresses three parameters fans out to three deltas.

Updates are bounded: `MAX_STEP 0.25` is checked before Ch'en and again during
verification, so one outlier cannot produce an unbounded step.

Parameter families are declared and not interchangeable:

- `ngram_weights` and `gram_multiplier` write `W_learned`
- `vector_component` writes `W_vector`
- `edge_weight` writes `W_graph`
- `corpus_prior` is `immutable` and refused as a target

The corpus prior stays immutable by construction: the loader rejects a family
whose target is `immutable`, and rejects a family/target mismatch. Ordinary
online learning is directed at `W_learned`.

`scalar_signal(record, parameter)` returns the parameter gradient shaped for
LearningLane, so `eta * signal` reproduces exactly what this lane proposed.

## What matches, what adapts

`wildcard.gml` declares what can match; `bias.gml` declares what can adapt.

Wildcards are pattern operators, not another n-gram order. `*` absorbs the
remainder and yields a capture:

    HOW TO *   matches  HOW TO GROW TOMATOES  capturing "GROW TOMATOES"

Relations are checked structurally at load: a `matches` edge must produce the
declared capture, a `suffix` edge must be a real tail, and a `generalizes` edge
must actually generalize. A graph that disagrees with the matcher fails to load.

The stable/adapting split is deliberate. `wildcard.gml` can stay fixed while
`bias.gml` carries the trainable relationships, and the KGF lanes decide how
adaptation is evaluated.

## Provenance and idempotency

A proposal carries `proposal_id`, `principal` and `workspace`. The storage key
is derived from the logical proposal, not the delivery attempt:

```
key = sha256(canonical([principal, workspace, proposal_id]))
```

Commit behaviour:

- key unseen — insert, return `inserted: True`
- key seen, identical payload hash — return `inserted: False`, no write
- key seen, different payload hash — `ContractError`, refused

The last case is the important one. It catches a caller reusing a proposal id
for a different delta, which would otherwise silently apply nothing or apply
twice depending on implementation.

`projection()` rebuilds the bias deterministically by summing committed deltas
in key order. There is no separate mutable bias tensor: the projection *is* the
bias, and it survives a restart because the events do.

## Invariants and their tests

1. A forged score is rejected — `test_forged_score_is_rejected`
2. A fractional gate is rejected — `test_fractional_gate_is_rejected`
3. Valid score with unauthorized admission is refused, store untouched
4. Valid authorized delta commits exactly once
5. Replay does not double-apply
6. Restart reconstructs the same projection
7. `delta == eta * gradient` — `test_tampered_delta_fails_verification`
8. `gradient == target - prediction` — `test_tampered_gradient_fails_verification`
9. A failing Ch'en report blocks the commit before the four flags are read
10. Gradient lanes cannot persist — `persist_authorized: False`

Current suite: 111 tests across `test_student`, `test_prediction`,
`test_gradient_lane`, `test_parameter_mapping_lane`, `test_graph_topology`,
`test_learning_lane`, `test_learning_lane_durable`, `test_pi_learning`.

## Declared values

```
SCORE_RULE      W*C*R
GATE_TYPE       authority            (binary)
DELTA_RULE      learning_rate*gradient
LEARNING_RATE   0.05
LANE_MODE       propose
commit_phase    Xul
MAPPING_RULE      softmax_feature_gradient
PARAMETER_FAMILY  ngram_weights -> W_learned
MAX_STEP          0.25
CORPUS_PRIOR      immutable
```

These live in `learning-lane.kgf` and `gradient-lane.kgf`. The loaders refuse a
file where any of them differs, so editing the declaration is the only way to
change behaviour — and it cannot be done silently in code.

## Two deployments

The lane exists in two forms, and they are not interchangeable.

`flat/` — the original contract. `delta = G`, so the gate value is also the
update magnitude. Scores are trusted as supplied and there is no `verify()`
step. It is self-contained: no gradient lane, no parameter mapping.

`micronaut/` — the three-contract form. `S = W*C*R` verified, `G` binary,
`delta = eta * gradient`, `verify()` at Ch'en. This is what GradientLane and
ParameterMappingLane feed.

Mixing them either double-applies a delta or refuses a valid one, because the
two disagree about what `G` means. `flat/README.md` carries the comparison.

## Rejected designs

- **G as a magnitude.** Makes "may this count" and "how much does it count"
  the same number. Produces a projection that cannot be audited.
- **Silently recomputing S.** Hides a caller that ranks by `W*C*R*G` and learns
  by `W*C*R`.
- **Deriving a default gradient.** Invents a training rule no one declared.
- **A mutable bias tensor.** Loses the event history that makes the projection
  reproducible.
- **Averaging feedback sources.** Different sources have different derivatives;
  averaging them produces a number that is not a gradient of anything.

## Not implemented

- **Feature extraction.** ParameterMappingLane requires a declared feature row
  per observation; `bias.gml` supplies it. No extractor is bundled, so the graph
  decides what the update actually means.
- **Quadgram counts.** `tables.json` declares order 4 in `retrieval_layer` but
  has no `ngram_quadgram` record or table. The prediction field has no order-4
  counts as a result.
- **Materialized bias artifact.** `projection()` computes on demand. Writing a
  serialized bias file would be a consumer of it, not a change to the store.
- **Non-text sources.** XCFE outcome and replay retention have no lane yet;
  each would be a separate kGF with its own rule.