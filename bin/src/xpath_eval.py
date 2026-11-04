#!/usr/bin/env python3
"""SaxonC-backed XPath 3.1 evaluator used by kuhul_phase_runtime."""

import json
import sys
from pathlib import Path


def sequence_value(value, processor):
    return [item_value(item, processor) for item in value]


def item_value(item, processor):
    if item.is_atomic:
        return {
            "kind": "atomic",
            "type": item.primitive_type_name,
            "value": item.string_value,
        }
    if item.is_node:
        return {"kind": "node", "value": item.to_string()}
    if item.is_map:
        entries = []
        for key in item.keys():
            entries.append({
                "key": item_value(key, processor),
                "value": sequence_value(item.get(key), processor),
            })
        return {"kind": "map", "entries": entries}
    if item.is_array:
        return {
            "kind": "array",
            "members": [sequence_value(item.get(index), processor)
                        for index in range(0, item.array_length)],
        }
    if item.is_function:
        return {"kind": "function", "name": item.name, "arity": item.arity}
    return {"kind": "item", "value": str(item)}


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "--request":
        print(json.dumps({"ok": False, "error": "usage: xpath_eval.py --request <json-file>"}))
        return 2
    try:
        request = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        expression = request["expression"]
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError("expression must be a non-empty string")

        from saxonche import PySaxonProcessor

        with PySaxonProcessor(license=False) as processor:
            # Keep XPath's document-reading functions from opening arbitrary
            # file/network resources. The explicitly supplied XML context is
            # parsed by the host before expression evaluation.
            processor.set_configuration_property(
                "http://saxon.sf.net/feature/allowedProtocols", "")
            xpath = processor.new_xpath_processor()
            xpath.set_language_version("3.1")
            for prefix, uri in request.get("namespaces", []):
                xpath.declare_namespace(prefix, uri)
            context = request.get("context")
            if context:
                context_xml = Path(context).read_text(encoding="utf-8")
                xpath.set_context(xdm_item=processor.parse_xml(xml_text=context_xml))
            result = xpath.evaluate(expression)
            payload = {
                "ok": True,
                "engine": "SaxonC-HE",
                "xpath_version": "3.1",
                "authority": "evaluation_only",
                "admission": "not_evaluated",
                "items": sequence_value(result, processor),
            }
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False,
                         separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
