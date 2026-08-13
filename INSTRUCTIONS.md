# INSTRUCTIONS — Read This First

> **Any LLM (or human) working in this repository must read this file before doing anything else, and must follow the rules in it for the entire session.**

---

## 1. Mission

This repository exists to **develop a mechanistic theory of Limited Magic: The Gathering formats**.

- **Mechanistic** means: we are not satisfied with heuristics or lore ("this deck feels good"). We want *models* — explicit, falsifiable statements about *why* things work, grounded in the underlying game mechanics (mana, tempo, card advantage, board state, curve, archetype signals, pack/pick dynamics, etc.).
- **Limited** means: formats where you build a deck from a restricted, freshly-opened card pool (Draft and Sealed), as opposed to Constructed.
- **First emphasis: Draft.** Sealed and other Limited formats come later.

The end goal is a body of theory: definitions, hypotheses, models, and experiments that together explain and predict outcomes in Limited play.

---

## 2. The Three Persistent Artifacts

This repo maintains three living documents. **All three are APPEND-ONLY.** See the append-only rules in §3.

| File | Purpose |
|------|---------|
| [`LABNOTEBOOK.md`](./LABNOTEBOOK.md) | The scientific record: hypotheses, definitions, experiments, observations, results, decisions. This is where the *theory* is built. |
| [`CONVERSATION_LOG.md`](./CONVERSATION_LOG.md) | A verbatim transcript of every exchange between the user and any assistant working in this repo. |
| [`INSTRUCTIONS.md`](./INSTRUCTIONS.md) | This file — the rules of the repo. (Editable, but changes should be deliberate and logged in the lab notebook.) |

---

## 3. Append-Only Discipline (NON-NEGOTIABLE)

`LABNOTEBOOK.md` and `CONVERSATION_LOG.md` are **append-only**. This means:

1. **Never edit, reword, reorder, or delete any existing content** in these files. What was written stays written.
2. **New material is added only at the end** of the file (after the last existing entry).
3. **Corrections and retractions are new entries**, not edits. If a past hypothesis was wrong, write a *new* lab-notebook entry that references the old one (by its date/title) and explains the correction. The original stays intact — being wrong is part of the record.
4. **The only permitted edit is appending.** If you catch yourself using find-and-replace or deleting lines in these two files, stop.

Rationale: a mechanistic theory is only trustworthy if its full development — including dead ends and mistakes — is preserved. The history *is* the data.

---

## 4. Conversation Log Rules

Every turn, the assistant must append the exchange to [`CONVERSATION_LOG.md`](./CONVERSATION_LOG.md):

- Append the **user's message verbatim**, then the **assistant's response** (verbatim or a faithful, complete summary if the response was very long / mostly tool calls).
- Each message gets a header: `### [YYYY-MM-DD HH:MM] USER` or `### [YYYY-MM-DD HH:MM] ASSISTANT`.
- Do this as part of the same turn, before considering the turn complete.

> **Reliability note:** instruction-following is best-effort. For *guaranteed* capture of every turn, this should be enforced by a Claude Code hook (see §7). Until a hook is in place, the assistant appends manually each turn.

---

## 5. Lab Notebook Rules

`LABNOTEBOOK.md` is the heart of the project. Append a new entry whenever something worth recording happens: a new idea, a definition, an experiment, a result, a design decision, a question.

**Entry format:**

```
## [YYYY-MM-DD HH:MM] TYPE — Short Title

<body>

Refs: <links to other entries, files, or external sources, if any>
```

**Entry TYPEs:**

- `DEFINITION` — a term given a precise meaning (e.g. "tempo", "playable", "signal").
- `HYPOTHESIS` — a falsifiable claim about how Limited works.
- `EXPERIMENT` — a plan to test a hypothesis (what data, what method, what would confirm/refute).
- `OBSERVATION` — raw findings, data, or noticed patterns.
- `RESULT` — the outcome of an experiment, tied back to its hypothesis.
- `MODEL` — a formal or semi-formal model (equations, algorithms, diagrams).
- `DECISION` — a methodological or scope decision and its rationale.
- `QUESTION` — an open question to revisit.
- `CORRECTION` — a retraction/revision of an earlier entry (must reference it).

Keep entries self-contained and dated. Prefer many small entries over one giant one.

---

## 6. Working Principles

- **Falsifiability first.** A hypothesis that can't be tested doesn't belong in the theory; put it under `QUESTION` until you can frame a test.
- **Define before you build.** Ambiguous terms ("value", "bomb", "curve") get a `DEFINITION` entry before they're used load-bearingly.
- **Cite reality.** Ground claims in game rules, real draft/game data, or explicit reasoning — not vibes.
- **Preserve dead ends.** Wrong turns are recorded, not erased (§3).
- **Small, frequent commits.** Commit after meaningful changes with clear messages.

---

## 7. For Claude Code Specifically

- `CLAUDE.md` points here; read this whole file at session start.
- **Automatic conversation logging is configured** via hooks in `.claude/settings.json`:
  - `UserPromptSubmit` → `.claude/hooks/log_user.ps1` appends the user's prompt.
  - `Stop` → `.claude/hooks/log_assistant.ps1` appends the assistant's response (parsed from the session transcript; de-duplicated by message uuid).
  - These are Windows/PowerShell scripts. They fail silently (never block a turn) and locate `CONVERSATION_LOG.md` relative to themselves.
- **Caveat:** Claude Code only watches `.claude/` for settings changes if a settings file existed when the session started. After first adding/enabling these hooks, open `/hooks` once (or restart) to activate them; the turn in which they are created is not auto-logged and should be appended by hand.
- On a non-Windows machine, port the two scripts (e.g. to `jq`+shell) and update the `command`/`shell` fields accordingly.
