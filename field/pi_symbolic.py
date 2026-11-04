from __future__ import annotations
from typing import Any, Dict, List, Optional
from pi_types import PiEvent

def extract_symbolic_intents(tree: Dict[str, Any]) -> List[PiEvent]:
    """
    ⟁tree is symbolic structure (not markup).
    Kernel may read it to produce intents, but MUST NOT mutate DOM here.
    """
    out: List[PiEvent] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        role = node.get("⟁role")
        if role == "ui.action":
            href = node.get("@href")
            if href:
                # Intent only; actual navigation is not performed by kernel.
                out.append(PiEvent(type="route_intent", target=node.get("⟁id"), payload={"href": href}))
        for ch in node.get("⟁children", []) or []:
            walk(ch)

    walk(tree)
    return out
