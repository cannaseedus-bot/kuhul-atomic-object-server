# Daemon Bot starter AIML

`daemon-bot.aiml` is a standalone, generic teaching knowledge base. It covers
patterns, templates, wildcard captures, SRAI redirects, bot properties, and
session predicates. `daemon-bot-extended.aiml` adds condition branches, random
responses, silent think/set memory, and topic-scoped assistant/coder modes.
The separate daemon-bot-learn.aiml file adds an opt-in runtime teaching flow
using inline learn categories.

Configure an AIML 2.0 host to:

1. Read `daemon-bot.properties` into bot properties.
2. Apply `daemon-bot.substitutions` case-insensitively to whole words before matching.
3. Initialize each new session's `name` and `mood` predicates to empty strings.
4. Load `daemon-bot.aiml`, then `daemon-bot-extended.aiml`, and retain session
   predicates between replies. Resolve duplicate patterns by topic and host
   precedence; the extended file intentionally demonstrates topic overrides.

Properties and substitution file formats are host-specific; adapt these starter
formats to the chosen interpreter. Empty predicate defaults are required by the
two unknown-value conditions. Memory writes use `think` to suppress the output
of `set`. XML examples are text, not executed template elements.

Try `hi`, `hello friend`, `what about daemons`, `cats and dogs`, `my name is Alex`,
`what is my name`, `I am tired`, `how am I`, and `coder write a wildcard rule`.

`daemon.js` still reads JSON rules from `manifest.json` at runtime and does not
parse the XML directly. The base `daemon-bot.aiml` rules are compiled into
`manifest.aimlDaemon.patterns`, and `daemon-bot-extended.aiml` is mirrored in
`manifest.aimlDaemonExtensions.patterns`, so both are reachable through
`/api/daemon/reply`. `daemon-bot-learn.aiml` remains a separate teaching flow,
handled by the model-side learning API rather than the JSON engine.

The learn flow is session-scoped. Before injecting captured values into a new
category, the host must reject values containing angle brackets and apply a
pattern/template whitelist; otherwise a user can inject AIML markup. Standard
AIML has no portable single-category forget operation. Persisting learned XML
requires an explicit per-session store and should not use learnf blindly in a
multi-user service.

There is one bare `*` fallback, placed last for readability and ordered-match
hosts. Loading these rules alongside another knowledge base requires resolving
duplicate patterns and fallback rules in that host.

## Reply trace

Every reply from `daemon.js` carries a `trace` object (schema
`daemon-bot.reply-trace.v1`, contract
`vendor/key-grammar-kit/data/grammar/daemon-bot.trace.contracts.json`). The
server route `/api/daemon/reply` returns it beside `text`, `matched` and
`state`. It is observation only: it records what the engine did, never what it
was allowed to do.

The record names the raw and normalized input and the substitutions that
fired, the matched category and its specificity, the six-phase walk
(`Pop → Wo → Yax → Sek → Ch'en → Xul`) with one status per phase, the capture
slots, the SRAI hops as nested child traces, any XCFE dispatch, predicate reads
and writes, evaluated conditions, and the reply status. `admission.admitted`
and `commit.authorized` are always `false` here: the pattern engine has no XCFE
callback and no commit path. `Yax` is recorded as `skipped` because a
deterministic rule match has no generation stage.

`DaemonBotWidget.tsx` and the browser frame (`micronaut/xaiml/chat-frame.js`,
compiled to `chat-frame.compiled.js`) render the record under each reply as a
collapsed `<details class="bubble-trace">`. `daemon-bot.pipeline.json` declares
the same contract for the learning pipeline, and `chat.html` binds it with
`data-trace-contract`.