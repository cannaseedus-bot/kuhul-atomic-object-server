"""Load and validate KGF semantic-field books for read-only field projection.

Semantic links remain keyed declarations. Embeddings may suggest neighbors,
but never rewrite this source or grant execution/authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


KEY_RE = re.compile(r"⟁[A-Z0-9_]+\Z")


class SemanticFieldError(ValueError):
    pass


@dataclass(frozen=True)
class SemanticFieldBook:
    schema: str
    fields: dict[str, tuple[str, ...]]
    relations: dict[str, dict[str, str]]
    sha256: str

    @classmethod
    def load(cls, path: str | Path) -> "SemanticFieldBook":
        source = Path(path)
        raw = source.read_bytes()
        try:
            document = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SemanticFieldError(f"{source}: invalid UTF-8 JSON: {exc}") from exc
        return cls.from_document(document, hashlib.sha256(raw).hexdigest())

    @classmethod
    def from_document(cls, document: Any, digest: str = "") -> "SemanticFieldBook":
        if not isinstance(document, dict) or document.get("schema") != "kgf.semantic-fields/2":
            raise SemanticFieldError("schema must be 'kgf.semantic-fields/2'")
        fields = document.get("fields")
        relations = document.get("relations")
        if not isinstance(fields, dict) or not fields:
            raise SemanticFieldError("fields must be a non-empty object of key arrays")
        if not isinstance(relations, dict):
            raise SemanticFieldError("relations must be an object")

        normalized_fields: dict[str, tuple[str, ...]] = {}
        for field_key, members in fields.items():
            if not isinstance(field_key, str) or not KEY_RE.fullmatch(field_key):
                raise SemanticFieldError(f"invalid field key: {field_key!r}")
            if not isinstance(members, list) or any(not isinstance(k, str) or not KEY_RE.fullmatch(k) for k in members):
                raise SemanticFieldError(f"{field_key}: members must be an array of glyph keys")
            if len(members) != len(set(members)):
                raise SemanticFieldError(f"{field_key}: duplicate member key")
            normalized_fields[field_key] = tuple(members)

        normalized_relations: dict[str, dict[str, str]] = {}
        for subject, targets in relations.items():
            if subject not in normalized_fields:
                raise SemanticFieldError(f"relation subject {subject!r} has no field declaration")
            if not isinstance(targets, dict):
                raise SemanticFieldError(f"relations[{subject}]: expected target-to-label object")
            normalized_relations[subject] = {}
            for target, label in targets.items():
                if target not in normalized_fields[subject]:
                    raise SemanticFieldError(f"{subject} -> {target}: relation target is not a field member")
                if not isinstance(label, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", label):
                    raise SemanticFieldError(f"{subject} -> {target}: relation label must be snake_case")
                normalized_relations[subject][target] = label

        return cls("kgf.semantic-fields/2", normalized_fields, normalized_relations, digest)

    @property
    def keys(self) -> tuple[str, ...]:
        ordered: dict[str, None] = {}
        for field_key, members in self.fields.items():
            ordered.setdefault(field_key, None)
            for key in members:
                ordered.setdefault(key, None)
        return tuple(ordered)

    def embedding_text(self, key: str) -> str:
        """Build a stable descriptive text from declared inbound/outbound links."""
        if key not in self.keys:
            raise KeyError(key)
        descriptions = [key[1:].replace("_", " ").lower()]
        memberships = [field for field, members in self.fields.items() if key == field or key in members]
        if memberships:
            descriptions.append("semantic fields: " + ", ".join(k[1:].replace("_", " ").lower() for k in memberships))
        outgoing = self.relations.get(key, {})
        if outgoing:
            descriptions.append("relations: " + "; ".join(
                f"{label.replace('_', ' ')} {target[1:].replace('_', ' ').lower()}"
                for target, label in outgoing.items()
            ))
        incoming = []
        for subject, targets in self.relations.items():
            if key in targets:
                incoming.append(f"{targets[key].replace('_', ' ')} from {subject[1:].replace('_', ' ').lower()}")
        if incoming:
            descriptions.append("incoming relations: " + "; ".join(incoming))
        return ". ".join(descriptions)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("vectors must have the same non-zero dimension")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        raise ValueError("zero-length embedding vector")
    return dot / (norm_a * norm_b)
