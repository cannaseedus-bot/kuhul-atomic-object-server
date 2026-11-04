#!/usr/bin/env python3
"""Build the 4-bone fold rig the shaders read.

The shaders declare a rig that nothing in the tree ever produced:

    bone_ids_buf[t*4 + k]     int32   k-th bone for token t (-1 = unused)
    bone_weights_buf[t*4 + k] float32 k-th blend weight for token t (sum = 1)
    priority: innermost fold -> parent fold -> base hash bone

    -- micronaut/shaders/gpt2_kuhul_think_bias.hlsl
    -- micronaut/shaders/cs_bone_argsort_.hlsl
    -- micronaut/shaders/cs_fold_kernel_compute_.hlsl
    -- micronaut/shaders/cs_gravity_field_layer_.hlsl

A fold key is a path, so it already carries its ancestry:

    FOLD:FIELD:⟁CAR:R0   ->   R0 ⊂ ⟁CAR ⊂ FIELD ⊂ FOLD

This module turns those paths into the rig. A bone is an ancestor of the token's
fold at a fixed distance: slot 0 is the innermost fold, slot 1 its parent, and
so on outward. Two tokens that share a bone share family, and the shader's
``lbs_overlap`` is the weight they share.

Authority: this produces structural coordinates only. A shared bone is a family
relationship, never verification, admission, or a committed fact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

SCHEMA = "kuhul.fold-bone-rig.v1"
SLOTS = 4
SEPARATORS = re.compile(r"[:/|>]+")
RECORD_ORDINAL = re.compile(r"^R\d+$", re.IGNORECASE)


class BoneRigError(ValueError):
    """The rig cannot be built without inventing a relationship."""


def parse_fold_key(key: str) -> list[str]:
    """Outermost-first path components, with record ordinals removed."""
    parts = [part for part in SEPARATORS.split(str(key).strip()) if part]
    if not parts:
        raise BoneRigError("fold key is empty")
    while len(parts) > 1 and RECORD_ORDINAL.match(parts[-1]):
        parts.pop()
    return parts


def ancestor_chain(key: str, slots: int = SLOTS) -> list[str]:
    """Innermost-first ancestry: own fold, parent, grandparent, ..., root."""
    if slots < 1:
        raise BoneRigError("slots must be positive")
    return list(reversed(parse_fold_key(key)))[:slots]


def weight_law(count: int) -> list[float]:
    """Geometric blend: innermost dominates, sum is exactly 1."""
    if count < 1:
        return []
    raw = [2.0 ** -(index + 1) for index in range(count)]
    total = sum(raw)
    return [value / total for value in raw]


def _base_hash_bone(key: str, buckets: int) -> str:
    digest = hashlib.sha256(str(key).encode("utf-8")).hexdigest()
    return f"BASE:{int(digest[:8], 16) % buckets}"


class BoneSpace:
    """Deterministic component -> bone id map. Ids are dense and ordered."""

    def __init__(self, bones: Sequence[str]):
        self.bones = list(bones)
        self.index = {name: position for position, name in enumerate(self.bones)}

    def __len__(self) -> int:
        return len(self.bones)

    def id_of(self, name: str) -> int:
        return self.index[name]


def build_rig(
    keys: Iterable[str],
    *,
    slots: int = SLOTS,
    pad: str = "none",
    hash_buckets: int = 8,
) -> dict[str, Any]:
    """Build ``bone_ids`` / ``bone_weights`` for one key per token.

    ``pad="none"`` leaves unused slots at -1 / 0 and renormalises the rest.
    ``pad="hash"`` fills unused slots with a weak shared base-hash bone.
    """
    if pad not in {"none", "hash"}:
        raise BoneRigError("pad must be 'none' or 'hash'")

    keys = [str(key) for key in keys]
    chains: list[list[str]] = []
    for key in keys:
        chain = ancestor_chain(key, slots)
        if pad == "hash":
            while len(chain) < slots:
                chain.append(_base_hash_bone(key, hash_buckets))
        chains.append(chain)

    counts: dict[str, int] = {}
    for chain in chains:
        for name in chain:
            counts[name] = counts.get(name, 0) + 1
    ordered = sorted(counts, key=lambda name: (-counts[name], name))
    space = BoneSpace(ordered)

    bone_ids = np.full((len(chains), slots), -1, dtype=np.int32)
    bone_weights = np.zeros((len(chains), slots), dtype=np.float32)
    for row, chain in enumerate(chains):
        weights = weight_law(len(chain))
        for slot, (name, weight) in enumerate(zip(chain, weights)):
            bone_ids[row, slot] = space.id_of(name)
            bone_weights[row, slot] = weight

    return {
        "schema": SCHEMA,
        "slots": slots,
        "bone_count": len(space),
        "bones": [
            {"id": position, "component": name, "tokens": counts[name]}
            for position, name in enumerate(space.bones)
        ],
        "weight_law": "geometric 2^-(k+1), normalised",
        "pad": pad,
        "bone_ids": bone_ids,
        "bone_weights": bone_weights,
    }


def lbs_overlap(rig: dict[str, Any], left: int, right: int) -> float:
    """Reference implementation of the shader's 4-bone overlap for two tokens.

    This is the shader's formula verbatim: the sum of ``w_i[k] * w_j[m]`` over
    matching bone ids. For two identical chains it therefore yields ``Σ w_k²``,
    not 1.0. ``normalized_overlap`` recovers the [0, 1] reading.
    """
    ids, weights = rig["bone_ids"], rig["bone_weights"]
    total = 0.0
    for ki in range(ids.shape[1]):
        bone = int(ids[left, ki])
        if bone < 0:
            continue
        for kj in range(ids.shape[1]):
            if int(ids[right, kj]) == bone:
                total += float(weights[left, ki]) * float(weights[right, kj])
    return total


def self_overlap(rig: dict[str, Any], token: int) -> float:
    """Σ w_k² — how concentrated a token's own rig is."""
    return float(np.sum(np.square(rig["bone_weights"][token])))


def normalized_overlap(rig: dict[str, Any], left: int, right: int) -> float:
    """Cosine-style normalisation: an identical chain scores exactly 1.0."""
    left_self, right_self = self_overlap(rig, left), self_overlap(rig, right)
    if left_self <= 0.0 or right_self <= 0.0:
        return 0.0
    return lbs_overlap(rig, left, right) / float(np.sqrt(left_self * right_self))


def cluster_tables(
    rig: dict[str, Any],
    token_indices: Sequence[int] | None = None,
    *,
    max_clusters: int = 64,
) -> dict[str, Any]:
    """Compact active bones into the local ids ``cs_bone_argsort_`` expects.

    The shader indexes ``n_clusters`` slots directly, so ids must be local to
    the sequence. Fails closed when a sequence needs more than 64 clusters.
    """
    ids = rig["bone_ids"]
    selection = list(range(ids.shape[0])) if token_indices is None else list(token_indices)
    primary = [int(ids[token, 0]) for token in selection]
    active = sorted({bone for bone in primary if bone >= 0})
    if len(active) > max_clusters:
        raise BoneRigError(
            f"sequence needs {len(active)} bone clusters; the shader budget is {max_clusters}"
        )
    local = {bone: position for position, bone in enumerate(active)}
    local_ids = np.array(
        [local.get(int(ids[token, 0]), 0) for token in selection], dtype=np.int32
    )
    order = np.argsort(local_ids, kind="stable")
    sorted_idx = np.array([selection[int(position)] for position in order], dtype=np.int64)
    cluster_count = np.zeros(len(active), dtype=np.int64)
    for value in local_ids:
        cluster_count[int(value)] += 1
    cluster_start = np.zeros(len(active), dtype=np.int64)
    if len(active) > 1:
        cluster_start[1:] = np.cumsum(cluster_count)[:-1]
    return {
        "codec": "kuhul.fold-bone-clusters.v1",
        "primary": "bone_ids[t,0]",
        "active_bone_ids": np.array(active, dtype=np.int32),
        "local_ids": local_ids,
        "sorted_idx": sorted_idx,
        "cluster_start": cluster_start,
        "cluster_count": cluster_count,
        "n_clusters": len(active),
    }


def write_sidecar(rig: dict[str, Any], path: str | Path, *, extra: dict[str, Any] | None = None) -> Path:
    """Write the shader-facing sidecar: bone_ids int32 [T,4] and bone_weights float32 [T,4]."""
    from safetensors.numpy import save_file
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    tensors = {
        "bone_ids": np.ascontiguousarray(rig["bone_ids"], dtype=np.int32),
        "bone_weights": np.ascontiguousarray(rig["bone_weights"], dtype=np.float32),
    }
    metadata = {
        "schema": SCHEMA,
        "slots": str(rig["slots"]),
        "bone_count": str(rig["bone_count"]),
        "weight_law": str(rig["weight_law"]),
        "layout": "bone_ids[t*4+k], bone_weights[t*4+k]; unused = -1 / 0",
    }
    for key, value in (extra or {}).items():
        metadata[str(key)] = str(value)
    save_file(tensors, str(output), metadata=metadata)
    return output


def load_sidecar(path: str | Path) -> dict[str, Any]:
    """Load and validate a bone sidecar, returning the exact dispatch layout."""
    from safetensors import safe_open
    from safetensors.numpy import load_file
    source = Path(path)
    if not source.is_file():
        raise BoneRigError(f"bone sidecar is missing: {source}")
    with safe_open(str(source), framework="np", device="cpu") as handle:
        metadata = handle.metadata() or {}
    if metadata.get("schema") != SCHEMA:
        raise BoneRigError("unsupported bone sidecar schema")
    tensors = load_file(str(source))
    bone_ids = tensors.get("bone_ids")
    bone_weights = tensors.get("bone_weights")
    if bone_ids is None or bone_weights is None:
        raise BoneRigError("bone sidecar must carry bone_ids and bone_weights")
    if bone_ids.dtype != np.int32 or bone_weights.dtype != np.float32:
        raise BoneRigError("bone sidecar dtypes must be int32 and float32")
    if bone_ids.ndim != 2 or bone_ids.shape != bone_weights.shape or bone_ids.shape[1] != SLOTS:
        raise BoneRigError("bone sidecar must be [T, 4] for both tensors")
    if not np.all(np.isfinite(bone_weights)):
        raise BoneRigError("bone sidecar weights contain non-finite values")
    return {"schema": SCHEMA, "bone_ids": bone_ids, "bone_weights": bone_weights, "metadata": metadata}


def dispatch_buffers(rig: dict[str, Any]) -> dict[str, np.ndarray]:
    """Flatten to the interleaved SRV layout both shaders index directly."""
    ids = np.ascontiguousarray(rig["bone_ids"], dtype=np.int32).reshape(-1)
    weights = np.ascontiguousarray(rig["bone_weights"], dtype=np.float32).reshape(-1)
    return {"bone_ids_buf": ids, "bone_weights_buf": weights}


def rig_from_index(index: dict[str, Any]) -> dict[str, Any]:
    """Build a rig from a neighborhood index whose rows carry ``fold_key``."""
    rows = index.get("rows")
    if not isinstance(rows, list) or not rows:
        raise BoneRigError("index has no rows")
    keys = []
    for position, row in enumerate(rows):
        fold_key = row.get("fold_key") or {}
        key = fold_key.get("key") if isinstance(fold_key, dict) else None
        if not isinstance(key, str) or not key.strip():
            raise BoneRigError(f"row {position} has no fold_key.key")
        keys.append(key)
    return build_rig(keys)


def _jsonable(rig: dict[str, Any]) -> dict[str, Any]:
    summary = {key: value for key, value in rig.items() if not isinstance(value, np.ndarray)}
    summary["bone_count"] = int(rig["bone_count"])
    return summary


def _selftest() -> int:
    keys = [
        "FOLD:FIELD:⟁CAR:R0",
        "FOLD:FIELD:⟁CAR:R1",
        "FOLD:FIELD:⟁GASOLINE:R2",
        "ALT:OTHER:⟁Z:R9",
    ]
    rig = build_rig(keys)
    assert rig["schema"] == SCHEMA
    assert parse_fold_key("FOLD:FIELD:⟁CAR:R0") == ["FOLD", "FIELD", "⟁CAR"]
    assert ancestor_chain("FOLD:FIELD:⟁CAR:R0") == ["⟁CAR", "FIELD", "FOLD"]
    assert [round(value, 6) for value in weight_law(3)] == [0.571429, 0.285714, 0.142857]
    assert rig["bone_ids"].shape == (4, SLOTS)
    assert np.allclose(rig["bone_weights"].sum(axis=1), 1.0)

    # Identity: the shader formula gives Σw²; normalisation restores 1.0.
    concentration = self_overlap(rig, 0)
    assert abs(concentration - 3.0 / 7.0) < 1e-6, concentration
    assert abs(lbs_overlap(rig, 0, 1) - concentration) < 1e-6
    assert abs(normalized_overlap(rig, 0, 1) - 1.0) < 1e-6
    # Cousins: same field and root, different leaf fold.
    cousin = lbs_overlap(rig, 0, 2)
    assert 0.0 < cousin < concentration, cousin
    # A different family shares no bone at all.
    assert lbs_overlap(rig, 0, 3) == 0.0
    # Determinism: the same key always yields the same row.
    again = build_rig(["FOLD:FIELD:⟁CAR:R0"])
    assert int(again["bone_ids"][0, 0]) == int(rig["bone_ids"][0, 0])
    # Missing slots stay -1 / 0 and the present weights still sum to 1.
    shallow = build_rig(["FOLD:⟁CAR"])
    row = list(shallow["bone_ids"][0])
    assert row[2:] == [-1, -1]
    assert np.isclose(shallow["bone_weights"][0].sum(), 1.0)
    # Active-cluster compaction is local and capped.
    table = cluster_tables(rig, [0, 1, 2])
    assert table["n_clusters"] == 2
    assert list(table["cluster_count"]) == [2, 1]

    wide = build_rig([f"FOLD:FIELD:⟁W{index}:R0" for index in range(65)])
    assert wide["bone_count"] > 64
    try:
        cluster_tables(wide, list(range(65)))
    except BoneRigError:
        pass
    else:
        raise AssertionError("cluster_tables must fail closed above the shader budget")

    # Sidecar round-trip: the exact tensors the shaders bind.
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        sidecar = write_sidecar(rig, Path(directory) / "bones.safetensors", extra={"tokens": rig["bone_ids"].shape[0]})
        loaded = load_sidecar(sidecar)
        assert loaded["bone_ids"].dtype == np.int32
        assert loaded["bone_weights"].dtype == np.float32
        assert np.array_equal(loaded["bone_ids"], rig["bone_ids"])
        assert np.allclose(loaded["bone_weights"], rig["bone_weights"])
        assert loaded["metadata"]["schema"] == SCHEMA
        buffers = dispatch_buffers(loaded)
        tokens = rig["bone_ids"].shape[0]
        assert buffers["bone_ids_buf"].shape == (tokens * SLOTS,)
        assert buffers["bone_weights_buf"].shape == (tokens * SLOTS,)
        assert np.isclose(buffers["bone_weights_buf"].reshape(tokens, SLOTS).sum(axis=1), 1.0).all()
    print("bone_rig selftest: ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, help="neighborhood index JSON with rows[].fold_key.key")
    parser.add_argument("--out", type=Path, help="write the rig manifest as JSON")
    parser.add_argument("--emit", type=Path, help="write the bone sidecar (bone_ids int32, bone_weights float32)")
    parser.add_argument("--json", action="store_true", help="print the rig manifest")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()
    if not args.index:
        parser.error("--index is required unless --selftest is used")

    index = json.loads(args.index.read_text(encoding="utf-8"))
    try:
        rig = rig_from_index(index)
    except BoneRigError as exc:
        parser.error(str(exc))

    summary = _jsonable(rig)
    active = cluster_tables(rig, range(min(rig["bone_ids"].shape[0], 64)))
    summary["sample_window"] = {
        "tokens": int(len(active["local_ids"])),
        "n_clusters": int(active["n_clusters"]),
    }
    emitted = None
    if args.emit:
        emitted = write_sidecar(rig, args.emit, extra={
            "tokens": rig["bone_ids"].shape[0],
            "source_index": str(args.index),
        })
        summary["sidecar"] = str(emitted)
    if args.out:
        args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"rig: {rig['bone_count']} bones over {rig['bone_ids'].shape[0]} tokens, {rig['slots']} slots")
        print(f"weight law: {rig['weight_law']}")
        print(f"first 64-token window: {active['n_clusters']} active clusters")
        if args.emit:
            print(f"sidecar: {args.emit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())