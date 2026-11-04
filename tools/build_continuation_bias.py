"""Regenerate the classic-vocabulary prior as a continuation bias graph.

Source: `english-dictionary.lexicon.key-grammar.jsonl`, an 18th-century lexicon.
For every `definition_keys` token, count how many distinct words use it. A token
appearing in many definitions is a conceptual primitive of the classic
vocabulary; that reuse is emitted as a bounded `continuation_bias` weight.

This is a prior about the classic vocabulary, not evidence about any particular
completion, and not a claim that two words mean the same thing. It is generated
from the lexicon and must never be hand-edited: rerun this script instead.

The output is a separate graph from `data/bias.gml`. That file declares the
learning topology (feature -> trainable parameter) and its loader refuses any
node kind but `ngram_feature`, `learned_parameter` and `corpus_prior`. Since the
two are different axes, folding this prior into it would break that loader.

No persistence, no admission, no mutation authority.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

MIN_COUNT = 2       # a token used once carries no reuse signal
BIAS_SCALE = 0.5    # keeps the logit adjustment modest next to the base score
MAX_NODES = 4000    # bound the artifact; the head of the distribution is what ranks


def collect(lexicon_path):
    counts = Counter()
    words = 0
    with Path(lexicon_path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            words += 1
            keys = row.get("definition_keys") or []
            if isinstance(keys, str):
                keys = keys.split()
            for token in keys:
                token = str(token).strip().casefold()
                if token and token.isalpha():
                    counts[token] += 1
    return counts, words


def build(counts):
    shared = [(token, count) for token, count in counts.items() if count >= MIN_COUNT]
    shared.sort(key=lambda row: (-row[1], row[0]))
    top = shared[:MAX_NODES]
    peak = top[0][1] if top else 1
    floor = math.log(1 + peak)
    rows = []
    for index, (token, count) in enumerate(top, start=1):
        weight = round(BIAS_SCALE * math.log(1 + count) / floor, 4)
        rows.append((index, token, weight, count))
    return rows, len(shared)


def render(rows, shared_count, words, lexicon_name):
    lines = [
        "graph [",
        '  comment "Classic-vocabulary continuation prior. Generated from the '
        '18th-century lexicon: weight = BIAS_SCALE * log(1+count) / log(1+peak), '
        'where count is the number of distinct words whose definition uses the '
        'token. A prior about reuse, not about meaning. Regenerate with '
        'tools/build_continuation_bias.py; never hand-edit."',
        "  directed 1",
        "  label \"Continuation_Bias_Classic\"",
        f'  generated_from "{lexicon_name}"',
        f"  bias_scale {BIAS_SCALE}",
        f"  min_count {MIN_COUNT}",
        f"  words {words}",
        f"  shared_tokens {shared_count}",
        f"  emitted {len(rows)}",
    ]
    for index, token, weight, count in rows:
        lines.extend([
            "",
            "  node [",
            f"    id {index}",
            f'    label "{token}"',
            '    kind "continuation_bias"',
            f"    weight {weight}",
            f"    evidence {count}",
            '    source "classic-lexicon"',
            "  ]",
        ])
    lines.append("]")
    return "\n".join(lines) + "\n"


def main():
    root = Path(__file__).resolve().parents[1]
    lexicon = root / "vendor/key-grammar-kit/english-dictionary.lexicon.key-grammar.jsonl"
    target = root / "vendor/key-grammar-kit/data/continuation-bias.gml"

    counts, words = collect(lexicon)
    rows, shared_count = build(counts)
    target.write_text(render(rows, shared_count, words, lexicon.name), encoding="utf-8")

    print(f"words          : {words}")
    print(f"distinct tokens: {len(counts)}")
    print(f"shared >= {MIN_COUNT}  : {shared_count}")
    print(f"emitted        : {len(rows)}")
    print(f"bytes          : {target.stat().st_size}")
    print("head:")
    for token, count in [(r[1], r[3]) for r in rows[:12]]:
        print(f"   {token:<14} {count}")
    tail = [(r[1], r[3]) for r in rows[-5:]]
    print("tail:", tail)


if __name__ == "__main__":
    main()
