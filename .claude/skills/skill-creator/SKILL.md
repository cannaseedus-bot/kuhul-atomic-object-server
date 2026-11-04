---
name: skill-creator
description: Create a new Claude skill (SKILL.md) paired with a mu-factory.py micronaut agent candidate. The two are linked by name so the agent can be invoked when the skill runs. Usage: /skill-creator <name>
---

You are creating a paired skill + micronaut agent. The skill is the Claude-side interface; the micronaut is the K'UHUL-side agent. They share an id.

$ARGUMENTS is the skill name (e.g. `summarize-lane`, `validate-kgf`). If $ARGUMENTS is empty, ask the user for a name before proceeding.

## Step 1 — Gather requirements

Ask the user (in a single message, not separate questions):
- **Purpose:** What should this skill do? One sentence.
- **Capabilities:** Which of these does it need? `read` / `compute` / `network` / `write` / `execute`
- **Behaviors:** Which modes fit? (`critic`, `scientist`, `investigator`, `programmer`, `teacher`, `analyst` — or describe a custom one)
- **Learning:** Should the agent learn from feedback? (`yes` → `candidate_only` strategy; `no` → omit learning block)

Defaults if the user skips a field: capabilities = `read compute`, behaviors = `analyst` at weight 0.75, no learning.

## Step 2 — Write the SKILL.md

Create `.claude/skills/<name>/SKILL.md`:

```yaml
---
name: <name>
description: <one-line purpose from Step 1>
---

<Instructions derived from the user's purpose. Be specific.>
```

## Step 3 — Write the MML spec

Write the MML to `examples/<name>.mml.xml`. Constraints from mu-factory.py:

- `id` must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$` — use the skill name as-is
- `<program>` requires both `language` and `entry` — use `language="kuhul"` and `entry="<name>.run"`
- `<behavior><mode>` weights must be in [0, 1]
- `<vector><bias>` values must be in [-1, 1]
- `<tool permission>` must be one of: `read`, `compute`, `network`, `write`, `execute`
- Valid phases: `Pop`, `Wo`, `Yax`, `Sek`, `Ch'en`, `Xul`
- Omit blocks that have no entries (empty `<tools/>` is valid but empty `<capabilities/>` with no children will error)

Standard phase set for a skill-paired agent:
```xml
<phases>
  <phase ref="Wo"    action="bind_intent"/>
  <phase ref="Yax"   action="select_strategy"/>
  <phase ref="Sek"   action="evaluate_gate"/>
  <phase ref="Ch'en" action="verify_output"/>
  <phase ref="Xul"   action="return_result"/>
</phases>
```

Add or remove phases based on the skill's nature. Adapt action names to what the agent actually does.

Example MML for a read-only analyst agent:
```xml
<micronaut id="my-skill" name="My-Skill-µ" type="programmable-agent" version="1.0.0">
  <program language="kuhul" entry="my-skill.run"/>
  <behavior>
    <mode ref="analyst" weight="0.80"/>
  </behavior>
  <vector>
    <bias name="accuracy" value="0.85"/>
  </vector>
  <field type="semantic" topology="gml" traversal="weighted" track="My-Skill-µ"/>
  <capabilities>
    <invoke ref="field.read"/>
  </capabilities>
  <tools>
    <tool ref="field.reader" permission="read"/>
  </tools>
  <phases>
    <phase ref="Wo"    action="bind_intent"/>
    <phase ref="Yax"   action="select_strategy"/>
    <phase ref="Sek"   action="evaluate_gate"/>
    <phase ref="Ch'en" action="verify_output"/>
    <phase ref="Xul"   action="return_result"/>
  </phases>
</micronaut>
```

## Step 4 — Create the candidate

```bash
python mu-factory.py create examples/<name>.mml.xml
```

If this fails, read the error — common causes:
- `id` has invalid characters (use only letters, digits, `_`, `-`)
- A required attribute is missing from `<program>`
- A phase ref is misspelled (case-sensitive: `Ch'en` not `Chen` as a phase ref — but mu-factory.py accepts both)
- A tool permission is not one of the five allowed values

On success, mu-factory.py prints the candidate path:
`micronaut/generated/candidates/agents/<name>/`

## Step 5 — Review gate (do not skip)

Show the user:
1. The candidate path
2. The SKILL.md you wrote
3. A summary of what the MML declares (capabilities, tools, phases)

Tell the user: **"Review `agent.json` and `micronaut.mml.json` in the candidate directory. When you're ready, say 'admit' to promote it to the live agent registry."**

Do NOT run `admit` until the user explicitly says to.

## Step 6 — Admit (on explicit instruction only)

```bash
python mu-factory.py admit micronaut/generated/candidates/agents/<name>
```

On success, the agent is live at `micronaut/agents/<name>/`. Tell the user the agent is now registered and can be invoked alongside the `/<name>` skill.

## Pairing note

The skill (`.claude/skills/<name>/SKILL.md`) is the Claude-side interface. The admitted micronaut (`micronaut/agents/<name>/`) is the K'UHUL-side agent. They share the same id so the daemon can route skill invocations to the agent. If the skill needs to call the agent at runtime, the orchestrator endpoint is `/api/daemon/agents/<name>/reply`.
