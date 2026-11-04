#!/usr/bin/env python3
"""Serialize one XAIML track and its trigrams to canonical K'UHUL feed v1."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XSL = ROOT / "vendor/key-grammar-kit/data/grammar/xaiml/v1/kuhul-feed-serializer.xsl"


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def build_feed(source: Path, generated_at: str | None = None, stylesheet: Path = DEFAULT_XSL):
    try:
        from saxonche import PySaxonProcessor
    except ImportError as exc:
        raise RuntimeError("SaxonC-HE is required; install requirements.txt") from exc

    with PySaxonProcessor(license=False) as processor:
        xslt = processor.new_xslt30_processor()
        executable = xslt.compile_stylesheet(stylesheet_file=str(stylesheet.resolve()))
        if generated_at:
            stamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("--generated-at must include Z or a UTC offset")
            stamp = stamp.astimezone(timezone.utc).replace(microsecond=0)
            executable.set_parameter("generated-at", processor.make_atomic_value(
                "dateTime", stamp.isoformat(timespec="seconds").replace("+00:00", "Z")))
        source_xml = source.read_text(encoding="utf-8-sig")
        source_node = processor.parse_xml(xml_text=source_xml)
        serialized = executable.transform_to_string(xdm_node=source_node)

    feed = json.loads(serialized)
    if ("generated_at" not in feed
            or feed.get("content_digest") != "sha256:PENDING"
            or not isinstance(feed.get("content_digest_input"), str)):
        raise ValueError("XSLT output has an invalid feed envelope")
    digest_payload = feed.pop("content_digest_input")
    digest_map = {key: value for key, value in feed.items()
                  if key not in {"generated_at", "content_digest"}}
    if json.loads(digest_payload) != digest_map:
        raise ValueError("XSLT digest payload does not match the serialized feed content")
    digest = "sha256:" + hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()
    feed["content_digest"] = digest

    seen = set()
    for item in feed["items"]:
        if len(item.get("pattern", [])) != 3:
            raise ValueError("serialized trigram does not contain exactly three atoms")
        if not all(isinstance(item.get(field), str) and item[field]
                   for field in ("phase", "phase_code", "phase_role")):
            raise ValueError("serialized item has an incomplete phase descriptor")
        if item.get("guid") in seen:
            raise ValueError(f"duplicate canonical guid: {item['guid']}")
        seen.add(item["guid"])
    return feed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="XML track/trigram source document")
    parser.add_argument("--output", type=Path, help="canonical JSON output; defaults to stdout")
    parser.add_argument("--bson", type=Path, help="also write the BSON document")
    parser.add_argument("--cbor", type=Path, help="also write canonical CBOR (requires cbor2)")
    parser.add_argument("--generated-at", help="RFC 3339 timestamp; defaults to current UTC")
    parser.add_argument("--stylesheet", type=Path, default=DEFAULT_XSL)
    args = parser.parse_args()
    try:
        feed = build_feed(args.input, args.generated_at, args.stylesheet)
        encoded = (canonical_json(feed) + "\n").encode("utf-8")
        if args.output:
            args.output.write_bytes(encoded)
        else:
            sys.stdout.buffer.write(encoded)
        if args.bson:
            from bson import BSON
            args.bson.write_bytes(BSON.encode(feed))
        if args.cbor:
            try:
                import cbor2
            except ImportError as exc:
                raise RuntimeError("CBOR output requires cbor2") from exc
            args.cbor.write_bytes(cbor2.dumps(feed, canonical=True))
    except Exception as exc:
        print(f"feed serializer error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
