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
- **Small, frequent commits.** Commit after meaningful changes with clear messages. Handshake commits additionally carry a machine-readable trailer block -- see section 8.

---

## 7. For Claude Code Specifically

- `CLAUDE.md` points here; read this whole file at session start.
- **Automatic conversation logging is configured** via hooks in `.claude/settings.json`:
  - `UserPromptSubmit` → `.claude/hooks/log_user.ps1` appends the user's prompt.
  - `Stop` → `.claude/hooks/log_assistant.ps1` appends the assistant's response (parsed from the session transcript; de-duplicated by message uuid).
  - These are Windows/PowerShell scripts. They fail silently (never block a turn) and locate `CONVERSATION_LOG.md` relative to themselves.
- **Caveat:** Claude Code only watches `.claude/` for settings changes if a settings file existed when the session started. After first adding/enabling these hooks, open `/hooks` once (or restart) to activate them; the turn in which they are created is not auto-logged and should be appended by hand.
- On a non-Windows machine, port the two scripts (e.g. to `jq`+shell) and update the `command`/`shell` fields accordingly.

---

## 8. Commit Trailers (machine-readable)

A commit that is part of the implement/review handshake carries a trailer block
that **git's own parser can read**. Putting the lines in the message is not the
same thing, and the difference is invisible until something tries to read them.

### The rules

1. **The trailer block is the last paragraph.** Nothing comes after it.
2. **`Co-Authored-By` goes inside that block**, not in a paragraph of its own.
   It is a trailer; git treats it as one; it belongs with the others.
3. **Keys.** `Role` (`worker` | `reviewer`), `Phase`, `Iteration`;
   `Reviewed-Commit` on reviewer commits; `Addresses-Review` and
   `Addresses-Implementation` on repair commits; `Verdict` on reviewer commits;
   `Validation`, repeatable, one per command.
4. **`Phase` is namespace-qualified.** Two numbering schemes are live in this
   repository -- the build spec's Phases 0-6 and the effect-semantics repair's
   Phases 1-4f, and both have a "Phase 4". Write `effect-4f` or `buildspec-6`,
   never a bare `Phase 4`.
5. **Verify after committing.** One command, below.

### Correct

    Effect-semantics <phase>: <what changed>

    <body paragraphs explaining the change>

    Role: worker
    Phase: effect-4f
    Iteration: repair2
    Addresses-Review: <sha>
    Validation: pytest (434 passed)
    Co-Authored-By: <name> <email>

### Wrong -- and this is what 36 of the 80 commits before `0315399` do

    ...
    Role: worker
    Phase: Phase 4
    Iteration: 4f-repair2

    Co-Authored-By: <name> <email>

The blank line makes `Co-Authored-By` its own paragraph. Git reads the last
paragraph and nothing else, so it reports that one trailer and the entire
handshake block is invisible. Measured on 2026-09-02: 36 of the last 80 commits
carried a complete, correct block; **zero were readable** by git or by
`ratchet.gitstate.trailers.parse_trailers`, which follows the same rule.

The discipline was being followed. The lab notebook entry for `0315399` even
records the trailers as present, which is true of the text and false of the
commit. Nothing would have caught the difference -- which is the whole argument
for a check.

### Verify

```
git log -1 --format='%(trailers:key=Role,valueonly,separator=;)'
```

Empty output on a handshake commit means the block is shadowed. Fix it with
`git commit --amend` before moving on.

`tests/test_commit_trailers.py` enforces this over every commit since the epoch
`0315399b8a28defb7d3c7a9117a7a339a38a03b5`. Commits before the epoch predate the
convention and are out of scope; they are not rewritten, because
`tests/fixtures/MANIFEST.json` and `src/ratchet/replay.py` in the orchestrator
both pin HOB SHAs and a history rewrite would invalidate them.
