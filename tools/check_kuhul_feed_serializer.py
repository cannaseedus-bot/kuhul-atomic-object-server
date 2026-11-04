#!/usr/bin/env python3
"""Conformance checks for the canonical K'UHUL feed v1 serializer."""

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from kuhul_feed_serializer import build_feed, canonical_json


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "vendor/key-grammar-kit/data/grammar/xaiml/v1/fixtures/feed-phases-escaping.xml"
TRACK_ESCAPE_FIXTURE = ROOT / "vendor/key-grammar-kit/data/grammar/xaiml/v1/fixtures/feed-track-escape.xml"


def canonical_component(value):
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-'*")
    pieces = []
    for char in value:
        if char in "#@ %":
            pieces.append({"#": "%23", "@": "%40", " ": "%20", "%": "%25"}[char])
        elif char in allowed or char == "µ":
            pieces.append(char)
        else:
            raise ValueError(f"invalid address component character {char!r}")
    return "".join(pieces)


def derived_guid(track, atoms, phase):
    return (canonical_component(track) + "#" +
            " ".join(canonical_component(atom) for atom in atoms) + "@" + phase)


def validate_guid(guid, track, atoms, phase):
    expected = derived_guid(track, atoms, phase)
    if guid != expected:
        raise ValueError(f"non-canonical guid: expected {expected!r}, got {guid!r}")


def with_input(xml):
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".xml", delete=False)
    path = Path(handle.name)
    try:
        handle.write(xml)
        handle.close()
    except Exception:
        handle.close()
        path.unlink(missing_ok=True)
        raise
    return path


def expect_failure(xml, label):
    path = with_input(xml)
    try:
        try:
            build_feed(path, "2025-11-03T00:00:00Z")
        except Exception:
            return
        raise AssertionError(f"invalid fixture unexpectedly serialized: {label}")
    finally:
        path.unlink(missing_ok=True)


def main():
    feed = build_feed(FIXTURE, "2025-11-03T00:00:00Z")
    assert feed["feed"] == "kuhul.feed/1"
    assert feed["items"][0]["pattern"] == ["def", "foo", "bar"]
    assert feed["items"][0]["bindings"][0]["index"] == 1
    assert type(feed["items"][0]["bindings"][0]["index"]) is int
    assert feed["items"][0]["phase_code"] == "010"
    assert feed["items"][1]["phase_code"] == "000"
    assert feed["items"][0]["phase_role"] == "Expansion"
    assert feed["items"][1]["phase_role"] == "Ingress"
    assert feed["items"][0]["guid"] != feed["items"][1]["guid"]
    assert feed["items"][0]["pattern"] == feed["items"][1]["pattern"]
    assert feed["items"][2]["guid"] == "CODEGEN-PY-µ#a%23b x%40y _@Sek"
    assert feed["items"][3]["guid"] == "CODEGEN-PY-µ#* middle µ@Xul"
    for item in feed["items"]:
        validate_guid(item["guid"], item["track"], item["pattern"], item["phase"])
    escaped_track = build_feed(TRACK_ESCAPE_FIXTURE, "2025-11-03T00:00:00Z")
    assert escaped_track["items"][0]["guid"] == "a%23b%25#x%40y * a%20b@Wo"
    assert derived_guid("track-one", ["a", "b", "c"], "Pop") != derived_guid(
        "track-two", ["a", "b", "c"], "Pop")

    canonical = canonical_json(feed)
    assert canonical_json(json.loads(canonical)) == canonical
    without_digest = {key: value for key, value in feed.items()
                      if key not in {"generated_at", "content_digest"}}
    expected_digest = "sha256:" + hashlib.sha256(
        canonical_json(without_digest).encode("utf-8")).hexdigest()
    assert feed["content_digest"] == expected_digest

    later = build_feed(FIXTURE, "2026-11-03T00:00:00Z")
    assert later["generated_at"] != feed["generated_at"]
    assert later["content_digest"] == feed["content_digest"]
    changed = copy.deepcopy(feed)
    changed["items"][0]["fold_ref"] += ".changed"
    changed_core = {key: value for key, value in changed.items()
                    if key not in {"generated_at", "content_digest"}}
    changed_digest = "sha256:" + hashlib.sha256(
        canonical_json(changed_core).encode("utf-8")).hexdigest()
    assert changed_digest != feed["content_digest"]

    try:
        from bson import BSON
        assert BSON(BSON.encode(feed)).decode() == feed
        bson_status = "pass"
    except ImportError:
        bson_status = "skip (pymongo unavailable)"
    try:
        import cbor2
        assert cbor2.loads(cbor2.dumps(feed, canonical=True)) == feed
        cbor_status = "pass"
    except ImportError:
        cbor_status = "skip (optional cbor2 unavailable)"

    base = '<aiml-feed><track id="t" grammar_ref="g"/><trigram track="t" pattern="{pattern}" phase="Yax" fold_ref="f"/></aiml-feed>'
    for count, label in (("a b", "two atoms"), ("a b c d", "four atoms")):
        expect_failure(base.format(pattern=count), label)
    for phase in ("Chen", "xul"):
        expect_failure(base.replace('phase="Yax"', f'phase="{phase}"'), f"phase {phase}")
    expect_failure(base.replace(' fold_ref="f"', ''), "missing fold_ref")
    duplicate = ('<aiml-feed><track id="t" grammar_ref="g"/>'
                 '<trigram track="t" pattern="a b c" phase="Yax" fold_ref="f"/>'
                 '<trigram track="t" pattern="a b c" phase="Yax" fold_ref="f"/>'
                 '</aiml-feed>')
    expect_failure(duplicate, "duplicate guid")

    try:
        validate_guid("t#a b c@Pop", "t", ["a", "b", "c"], "Yax")
        raise AssertionError("mismatched GUID was accepted")
    except ValueError:
        pass

    print("PASS | K'UHUL feed serializer: phase identity, escaping, bindings, digest, "
          f"negative validation; BSON {bson_status}; CBOR {cbor_status}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL | K'UHUL feed serializer: {exc}", file=sys.stderr)
        sys.exit(1)
