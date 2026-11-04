# PLAN

Working plan for the vocabulary and question layer. Every figure below was
measured on this checkout; nothing here is estimated.

## Status

**Autocomplete lane** — `micronaut/autocomplete_lane.py`
Four sources, four jobs, kept apart:

```
syllable.gml    which words qualify          (retrieval constraint)
n-grams         which continuations exist    (evidence)
wildcard.gml    which continuations exist    (evidence)
bias            how eligible ones rank       (logit adjustment)
```

`score = sigmoid(logit(base) + bias) * W*C*R`. A syllable match decides
eligibility and never raises a score. Filtering tests the next predicted word
only. `suggest(prompt, k, *, syllable=None, match_policy="exact", target_offset=0)`.

**Syllable graph** — `vendor/key-grammar-kit/data/syllable.gml`, `micronaut/syllable_graph.py`
One node per beat, shared across words: 9 words, 15 beats, `com` serves 6.
Order and spelling live on the `contains` edge (`position`, `surface`), because a
shared beat sits at a different position in each word. `next` edges are refused
as ambiguous. Coverage: 4 groups for 9 words.

**Match policy** — frozen to `exact`. `stress_insensitive`, `dialect_aware`,
`orthographic`, `phonetic_similarity` are declared in `PROPOSED_MATCH_POLICIES`
and raise `ValueError` at both graph and lane. `target_offset != 0` raises
`NotImplementedError`.

**Classic prior** — `vendor/key-grammar-kit/data/continuation-bias.gml`, `tools/build_continuation_bias.py`
4,000 `continuation_bias` nodes, 582,762 bytes, generated from definition-key
reuse over 18,830 definitions (6,562 distinct tokens, 4,504 used twice or more).
Regenerate; never hand-edit. Separate from `data/bias.gml`, which declares the
learning topology and whose loader refuses this node kind.

**Dictionary** — `micronaut/dictionary.py`
18,830 words, 99,274 relation rows, loads in 2.2s. `define(word)` returns the
stored text or `None`; nothing is generated. Relations are all
`@related_to` / `definition_unigram` / `lexical_evidence` at weight 1 — wording,
not meaning.

**Question engine** — `micronaut/question_engine.py`
`propose(gap, candidates)` ranks with `wcr.fold_score` unchanged and returns
`authority="proposal_only"`. The gap selects which question type is admissible;
WCR orders the wording inside it. `RESOLVED` yields no question.
`eliza_question_candidates` adds a bounded AIML/SRAI adapter: single `<srai>`
redirects, `<star/>`, cycle detection, unsupported tags refused, gap supplied by
the caller and never inferred.

**Semantic bindings** — `vendor/key-grammar-kit/data/grammar/kuhul-question-engine.kgf`, `micronaut/question_bindings.py`
The keys are identities and the edges are typed, using the construct the
grammar already validates: `edge <QNAME> -> <QNAME> type <IDENT>;`.

```
eliza:MEMORY_FAILURE      --matched_by-->    aiml:FORGETTING_PATTERN
aiml:FORGETTING_PATTERN   --redirects_to-->  srai:DIAGNOSE_MEMORY
srai:DIAGNOSE_MEMORY      --suggests_gap-->  cfpc:MEMORY_FAILURE_MECHANISM
srai:DIAGNOSE_MEMORY      --suggests_gap-->  cfpc:RETENTION_SCOPE
cfpc:*                    --specializes-->   cfpc:KNOWLEDGE_GAP
cfpc:MEMORY_FAILURE_MECHANISM --proposes-->  question:STORAGE_OR_RETRIEVAL
cfpc:RETENTION_SCOPE      --proposes-->      question:WHICH_SESSION
```

`suggests_gap` is weaker than "classifies": an AIML match proposes which gaps
might be open and CFPC decides which one the evidence supports.
`bound_question_candidates(bindings, intent_key, gap=...)` keeps only the
suggested gap whose declared type equals that verdict, so a verdict no declared
gap matches is refused rather than borrowing another gap's question. No Python
string matching selects a question.

Two invariants are enforced at load: only a key of kind `gap` may carry a
`proposes` edge, and `specializes` is taxonomy that resolution never follows.
`tools/install_question_bindings.py` installs the declarations atomically and is
structurally idempotent — it parses, adds only what is missing, validates, then
replaces through a temporary file.

**Micronaut semantic registry** — `vendor/key-grammar-kit/data/micronauts/kuhul-micronaut-registry.json`, `data/schema/kuhul-micronaut-registry.v1.schema.json`
The registry and schema now exist. The registry contains seven declarative
descriptors (ELIZA, QUESTION_ENGINE, CFPC, SHEOGORATH, JYGGALAG, LEARNING,
ADVISOR), a shared six-phase descriptor table, and explicit non-grant rules.
All seven entries currently have empty `capabilities.registered` arrays and
declarative-proposal status; this is metadata, not an active runtime snapshot.
The Advisor route map is compiled separately from `advisor-bootstrap.json`.

**XJSON/XSL semantic frontend** — `kuhul.xjson.json`, `micronaut/xjson.py`,
`micronaut/xjson-bindings.xsl`, `micronaut/xjson_api.py`, and
`lib/kuhul-xjson.js`. The XJSON descriptor projects phase and Micronaut
bindings into a reversible XML-node representation for XSL and browser/JS
clients and declares the REST data-stream routes consumed by the API and
mirrored by `/bus`. XSL node-match rules describe typed projections across programs,
Micronauts, widgets, topology, vectors, media, database tables, and MML/GML
fields and graphs. Prompt context can request a semantic-field proposal through
the existing Qwen field generator plus Gemma embedding path. Proposals remain
under `field/distilled/proposals/`; they do not mutate the manifest or bypass
XCFE admission, verification, or commit.

**Shared model profiles** — `micronaut/models.toml`, `micronaut/model_kernel.py`
Named profiles now cover general generation, question generation, reply
formatting, Advisor, field distillation, and embeddings. `model_kernel`,
`model_questions`, and the bounded worker resolve profiles through this file.
Models contribute wording, depth/format guidance, and caller-bounded ranking
priors; they do not verify facts, register capabilities, or authorize calls.
The `reply_formatting` profile is configured, but `micronaut/main.py` currently
builds a formatting contract and marks model formatting as deferred rather
than calling that profile. Model-backed GML/MML distillation is a separate
candidate-data path, and ADVISOR model output remains a route proposal subject
to host control.

**Factory-to-autocomplete evidence handoff** — `mu-factory.py`,
`micronaut/autocomplete_refresh.py`, `micronaut/autocomplete_lane.py`
Factory writes source-evidence research records and appends a hash-pinned,
candidate-only refresh event. Autocomplete can load these records into a
separate evidence cache. This does not update dictionary continuation bias or
promote an unverified source into a temporal fact. A serving caller still has
to invoke the refresh method.

**Model questions** — `micronaut/model_questions.py`
The model is asked for questions that build context, never for replies. Only
interrogative sentences survive parsing; statements are discarded rather than
quoted, so a confident false claim cannot travel downstream wearing a question
mark. The model supplies wording only: `weight`, `confidence` and `relativity`
come from the caller, and a model saying "certainly" changes nothing.

`ask_model_questions` resolves the `question_generation` profile from
`micronaut/models.toml` through `model_kernel`; legacy `backend="local"` means
the configured default profile and is not passed as a runtime backend. The
profile uses `qwen3.5:4b` on Ollama by default, temperature 0.2, and a system
prompt that forbids answers. `request_questions(generate, ...)` takes the
generator as a parameter, so the parsing rules are tested without a model.

Checked against a real Gemma answer to "What is the moon?": one question
survives, and its false claim — "The moon's gravity holds Earth in orbit" — is
dropped because it is not a question.

**Research evidence** — `micronauts-data/*.json`, `micronaut/research_evidence.py`, `cfpc-model.py`
Librarian-µ / Factory-µ write question-scoped records that declare their own
authority: `source_evidence_only; not_verified_fact`. The reader refuses any
record that claims more, and never upgrades the status.

It answers two questions: which sentence in which source states a quantity of a
query term, and whether two sources state different quantities.

The shipped `how-many-moons-does-saturn-have` record demonstrates why that
matters: NASA says 274 confirmed moons (March 2025), Wikipedia says 293 with
confirmed orbits (June 2026) and notes that no absolute number is definable
because the moon/moonlet boundary is undefined. Reporting the disagreement is
the correct output; a model that answers with one number is asserting something
the sources do not support.

`cfpc-model.py --record <path>` uses the record as classification evidence and
emits the conflicts alongside the proposals.

`how-many` is now a declared pattern: `data/cfpc/how-many.cfpc-pattern.v1.json`,
registered in the FAQ map, with a `count` intent in the resolver and `how many` /
`how much` prefixes in `match_pattern`. Its context template instructs the reader
to report both counts and choose neither. "How many moons does Saturn have?"
classifies as `KNOWLEDGE_GAP_NO_KEYS` (route `retrieval`) rather than
`QUERY_GAP`.

**Corrections** — `micronaut/correction.py`
A user correction is evidence: it costs confidence in what was said before and
it states something instead. `detect` reports whether an utterance corrects,
what it asserts, and the delta — a declared policy, not a measurement:

```
"No, Saturn has 293 moons."                      denial  -0.45  values=('293',)
"Actually the confirmed count changed in June..." hedged  -0.25  values=()
"No, fewer than that."                           denial  -0.35  values=()
"Saturn is a gas giant."                         not a correction
```

An explicit denial costs more than a hedge; naming a value costs more than
gesturing at one; the delta never rises above zero and never falls past -1.0.
Years are not quantities, so a timestamp does not count as naming a value.

`to_mml` renders the correction as MML carrying that delta as its bias, and
`mu-factory create` accepts it: status `candidate`, `toolGrants: []`,
`execution: False`, bias `-0.45`, memory types `correction` and `fact`. A verbal
correction therefore produces a factory candidate, not a fact — admission is
still the host's decision.

**Promotion gate** — `mu-factory.py`
Verified end to end in a throwaway tree: `create` → `admit` → refusals.
Admission flips the lifecycle marker only; `toolGrants` stays `[]` and
execution / verification / commit stay `False`. Tampered candidate, DTD, and
unknown phase are all refused.

## Invariants

- Question parsing, scoring, and semantic lookup do not themselves admit,
  verify, or commit. Factory evidence writes and refresh notifications remain
  explicitly candidate-only.
- A score orders candidates; it never authorises one.
- Capability admission is not execution admission.
- An empty match stays empty: no widening behind the caller's back.
- Declared policies and implemented policies must stay equal; proposals stay
  outside that equality.
- Stored data is quoted, never paraphrased.

## Open problems

**Definition segmentation.** 1,736 lexicon rows (9.2%) contain the next entry —
` V. a.`, ` N. f.`, `, or ` — and the true rate is higher. `car` carries
`ARRAS`, `HORSEMAN`, `CARBINE` from the columns that follow it. `definition_keys`
and the relation rows are derived from the same text, so contamination
propagates into any field built from them. Until this is split, definitions are
quotable but not usable as neighbours.

**Modern vocabulary has no definition or prior.** 823 of 1,552 neighborhood
words are defined. `gasoline`, `petroleum`, `licensed`, `algorithm`, `CSS`,
`JSON` are absent from an 18th-century lexicon, so they carry neither definition
nor classic prior. They exist only in the field layer.

**The prior's head is function words.** `to 0.5`, `in 0.4785`, `by 0.4398`,
`any`, `one`. That is a real reuse fact about the corpus and mostly inert for
content completions, but it is not a topical prior. `grow`, `tomato`,
`computer` score `0.0000` because no other definition uses them.

**No data promotion path.** `mu-factory` covers micronaut agents only. Field
rows, bias weights and definitions have no candidate/admit lifecycle, so
"promoted data" has no gate to pass through.

**ELIZA route is not integrated.** An ELIZA semantic track, registry descriptor,
and bounded AIML/SRAI question-engine adapter exist, but the concrete
`MY MODEL KEEPS FORGETTING *` / `DIAGNOSE MEMORY *` categories are absent from
the active daemon AIML banks. The adapter is not wired through the serving
route into CFPC and the question engine, so a descriptor does not establish a
callable ELIZA route.

**The semantic registry has a read-only XJSON projection, not an admission
consumer.** The XJSON loader/API exposes its seven descriptors and phase/lane
bindings to XSL and UI clients, but all entries remain declarative proposals
and all `capabilities.registered` arrays are empty. There is still no loader
that resolves those declarations against active Micronaut registrations and
reports drift. The Advisor semantic map is a compiled projection; the
bootstrap/runtime router remains the source of route behavior.

**Daemon asset utilization is uneven.** The active response path is
`daemon.js` through `lib/object-api.cjs`; the browser loads
`micronaut/xaiml/chat-frame.compiled.js`, whose source is
`micronaut/xaiml/chat-frame.js`. The active manifest supplies the AIML
patterns and `micronaut/xaiml/daemon-cli.xaiml`; the chat frame also resolves
the app descriptor, knowledge file, and model runtime frame. However,
these daemon files need different treatment:

| File / artifact | Status in the current runtime | Plan action |
|---|---|---|
| `daemon-bot.xjson` | Present, but no runtime consumer references it. | Missed wiring: consume it as a non-authoritative descriptor from the existing daemon UI/API path. |
| `daemon-bot.properties` | Present; no active loader was found. | Decide whether to load it or label it archival. |
| `daemon-bot.substitutions` | Present; `daemon.js` performs substitution handling separately rather than loading this file. | Missed wiring if this file is intended to configure matching; otherwise label it archival and avoid implying it is active. |
| `daemon-bot.pipeline.json` | Present and explicitly `analysis_only`; it does not run AIML. | Keep it non-runtime unless a separately contracted runner is needed. |
| `vendor/key-grammar-kit/data/intent-graph.gml` + `micronaut/intent_graph.py` | The adapter validates typed references, resolves the graph path from XJSON, and emits existing `QuestionCandidate` records. `daemon_eliza.run_pipeline` consumes it after CFPC and returns topology/proposal provenance; XJSON, XSL projection, JS helper, REST API, and `/bus` declare graph and question-candidate routes. | Remaining: run the API/CLI conformance checks. Ranking, verification, XCFE admission, and persistence stay downstream. |
| `micronaut/xaiml/chat-frame.js` and `chat-frame.compiled.js` | Source and compiled UI both exist; `chat.html` loads the compiled file. | Add source/compiled parity validation to prevent stale UI behavior. |
| `tools/check_daemon_asset_wiring.py` | Missing. | Add a checker for required daemon references, active-vs-archival classification, and chat-frame source/compiled parity. |

The remaining daemon assets are present and referenced through the active
manifest/chat path: `daemon.js`, `lib/object-api.cjs`,
`micronaut/xaiml/daemon-cli.xaiml`, `micronaut/xaiml/model-runtime-frame.json`,
`vendor/key-grammar-kit/data/apps/daemon-bot.asx-app.json`, and
`vendor/key-grammar-kit/data/apps/daemon-bot-knowledge.json`. The root AIML
banks are part of the manifest-backed pattern inventory/build path. Impact:
editing an unwired descriptor or legacy source can appear successful while
serving continues to use another representation. No new daemon data file is
needed; the concrete missing file is the wiring/parity checker, while the
XJSON/properties/substitutions items are existing files that were missed by
runtime integration or need an explicit archival decision.

**Intent assets overlap but are not one registry.** Intent-related files
include `micronaut/xaiml/greeting-intents.json` (manifest-referenced and
consumed by the chat-frame greeting projection),
`vendor/key-grammar-kit/data/cfpc/what-is.intent-resolver.v1.json` (loaded by
`micronaut/cfpc_classifier.py`), CFPC pattern documents under
`vendor/key-grammar-kit/data/cfpc/` (classifier data with structural validation),
`vendor/key-grammar-kit/data/tracks/CFPC-u.semantic-tracks.v1.json` and
`intent-unresolved.semantic-tracks.v1.json` (declarative track profiles), plus
the question-engine KGF/bindings and `micronaut/question_engine.py`. They cover
surface greetings, intent classification, gap routing, and question proposals.
`vendor/key-grammar-kit/data/intent-graph.gml` adds field/bigram/wildcard
question topology; `micronaut/intent_graph.py` validates and adapts it into
the existing `QuestionCandidate` type. `daemon_eliza.py` uses the descriptor-
selected graph after CFPC classification, and the XJSON API exposes read-only
graph data and candidate generation. No checker reconciles the distinct intent
sources yet. The graph remains a topology adapter, not a second generic intent
resolver or a replacement for the classifier/question engine.

**Phase data is not yet a shared Python/XSLT source.** The phase descriptor
table exists in the semantic registry and in the feed stylesheet. The Python
feed wrapper invokes XSLT and checks emitted phase fields, but ordinary Python
Micronaut routing does not load the same phase map. Updating one copy can leave
the other stale. XPath 3.1 `map {}` syntax is not directly a Python data API.

**ELIZA evidence recording is wired; model-call provenance remains open.**
`micronaut/jrom_tables.py` reads the JROM controller and key-table manifests,
records ELIZA traces and field proposals under their `evidence_only` policies,
and writes matching hash-chained events to both `jrom_event` and the configured
JSONL stream. The writer does not create tables, run XCFE admission, or commit
learning state. Ch'en event spelling is canonical; the replay validator keeps
accepting legacy `Chen` records. The writer validates the JSONL prefix against
SQLite and catches the stream up from committed event rows. Model calls still
do not emit JROM records containing profile/backend/model identity and
request/result provenance.

**Micronaut table and program projections are declarative.**
`data/host/manifests/micronauts.tables.json` is now included by the JROM table
controller and maps through `key.tables.json` as read-only declaration data.
`data/micronaut/micronaut.programs.xsl` projects the canonical v0.1 program JSON
to typed XML nodes with `projection_only`, `admission=not_evaluated`, and
`dispatch=not_invoked` markers. No synchronizer seeds these tables yet, and
neither the XSLT projection nor a stored row establishes runtime registration.

**Micronaut model references and JROM are not connected.** `models.toml` has
named profiles, but the semantic registry has no `model_profile_ref` per
Micronaut. Micronauts should reference profile IDs; JROM is an append-only
provenance/replay journal, not a model resolver. The current model call paths do
not emit JROM records containing profile/backend/model identity and
request/result provenance. Credentials must remain outside the registry and
journal.

**Model profile adoption is incomplete.** `tools/distill.py` and
`field/field-distill.py` still own model/endpoint defaults instead of resolving
their task profiles from `models.toml`. The embeddings profile is declared but
the field distiller does not consume it. Per-agent daemon manifests also carry
their own model profiles. A conformance check is needed before these sources
can be safely consolidated.

**Model depth/format is partly declarative.** `main.py` builds depth guidance
and evidence constraints, but does not invoke the `reply_formatting` profile
or validate generated text against the allowed source values. In
`cfpc-model.py`, W/C/R are caller-provided placeholders, not learned model
measurements. The model may contribute wording or ranking features, but no
calibrated model-derived bias contract currently joins GML/MML, CFPC, and
ADVISOR.

**Temporal facts do not yet refresh from verified evidence.** Online worker
records enter the candidate-only autocomplete inbox. There is no end-to-end
source-evidence → independent verification → temporal fact revision → verified
autocomplete refresh path. The Saturn observations remain unverified; the
latest candidate must not be treated as the current answer.

**Semantic grammar cannot be regenerated.** `tools/semantic_grammar.py` is not
in this checkout, so cue additions and the `Chen` spelling migration cannot be
compiled into `kuhul.semantic-grammar.json`.

**Wildcard patterns are trailing-star only.** `AutocompleteLane` handles
`"how to *"` but not `"* to grow"` or `"grow * indoors"`.

## Next steps

1. Check in the XJSON/XSL frontend and prompt-to-field proposal bridge against
   the source registry, active phase runtime, and browser/PowerShell RPC routes.
   The proposal endpoint must remain bounded and candidate-only.
2. Establish the shared phase source: load the registry phase descriptors from
   Python and expose the same data to XSLT, then check the six names/codes
   against K'UHUL runtime phase constants.
3. Add a registry loader that compares declared entries and capabilities with
   actual Micronaut registrations; keep unregistered proposals ineligible.
4. Add `model_profile_ref` to Micronaut descriptors and validate every
   reference against `micronaut/models.toml`; then migrate the distillers.
5. Instrument the model-call boundary with JROM provenance events that record
   profile/backend/model and request/result hashes without credentials. The
   ELIZA evidence-table recorder is separate and does not satisfy this model
   provenance requirement.
6. Add the `MY MODEL KEEPS FORGETTING *` and `DIAGNOSE MEMORY *` categories to
   the active daemon AIML set, then drive `eliza_question_candidates` through
   the serving path into CFPC.
7. Verify the intent-graph/XJSON/API/daemon chain; then close the remaining
   daemon utilization gaps by consuming `daemon-bot.xjson` as a
   non-authoritative descriptor in the existing chat/API path; either load
   `daemon-bot.properties` and `daemon-bot.substitutions` from that path or
   mark them archival and remove runtime claims that imply they are active;
   add `tools/check_daemon_asset_wiring.py` to check those references and that
   `chat-frame.compiled.js` matches `chat-frame.js`. Keep
   `daemon-bot.pipeline.json` analysis-only unless a separate runner contract
   is added.
8. Wire `reply_formatting` to source-bounded output generation and deterministic
   validation; keep depth/format and WCR contributions as proposal inputs.
9. Build the verified temporal-fact refresh lifecycle from source evidence
   through verification and authorized update; do not promote the latest
   candidate by recency alone.
10. Segment lexicon definitions at the next headword; re-measure the 1,736
   flagged rows before and after.
11. Decide how modern vocabulary enters the field: authored rows, model rows
   promoted from `neighborhood.jsonl`, or both with declared precedence.
12. Design a data promotion path with the same shape as `mu-factory`: candidate
   directory, marker file, recompute-and-compare, grants stay empty.
13. Wire `question_engine` and the adapter into the execution field
   (`fold:PROPOSE`, `fold:RANK_PROPOSALS`) so they are declared, not just
   imported.
14. Widen wildcard matching beyond trailing star, or declare the limitation in
   the KGF.
15. Add an idempotent, source-hash-checked projection loader for Micronaut
    declaration/program/route rows; preserve read-only status and keep runtime
    registration and XCFE admission independent.

## Verify

```
python -m unittest discover -s micronaut -t . -p "test_*.py" -q
python vendor/key-grammar-kit/tools/check_2d_key_graph_execution_field.py
python tools/build_continuation_bias.py
python tools/install_question_bindings.py
python -m unittest micronaut.test_question_bindings -q
```

Last recorded baseline: 237 tests, 236 pass, 1 pre-existing import error in
`test_glyph_buffer_engine` (it imports a bare module name, so discovery from the
root cannot resolve it; it passed when run directly). KGF checker:
`PASS | 10 KGF programs`. These are historical results and have not been
rerun after the latest model-profile and autocomplete-refresh edits; this plan
update only parsed the model/registry metadata and checked the checkpoint.
