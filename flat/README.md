# Flat deployment — the original lane contract

These three files are the LearningLane as originally specified, kept runnable
and unchanged in semantics.

    learning_lane.py                delta = G        (gate doubles as magnitude)
    LearningLane.kgf                no score/gate/delta declarations
    test_learning_lane_durable.py   the durable replay test

This is **not** the corrected contract in `micronaut/`. The two differ in four
places, and the difference is deliberate:

    flat/                          micronaut/
    ---------------------------    -------------------------------------
    delta = G                      delta = eta * gradient
    G may be any value in [0,1]    G is binary (authority only)
    S is trusted as supplied       S is verified against W*C*R
    no verify() step               verify() at Ch'en, blocks commit

`micronaut/` is what GradientLane and ParameterMappingLane feed: they produce a
signed error and a parameter gradient, which only make sense against
`delta = eta * gradient`. `flat/` is self-contained and has no upstream
dependency; it takes the gate value as the update magnitude directly.

Do not mix them. Pick one lane for a deployment and keep the whole chain
consistent — a `learning_lane.py` from one directory with a proposal built for
the other will either double-apply a delta or refuse a valid one.

Run the standalone test:

    python flat/test_learning_lane_durable.py

The file here is byte-identical to the original except for
`TemporaryDirectory(ignore_cleanup_errors=True)` in the test harness: the
original `_db()` returns an unclosed connection, so temp-directory cleanup
raises `WinError 32` on Windows. The module itself is unchanged.
