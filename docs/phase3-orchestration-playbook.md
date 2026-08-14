# Phase 3 Orchestration Playbook (LLM Semantic Extraction)

How Phase 3 of the HOB knowledge-graph build was actually run, so it can be
re-run for a new set (FIN, etc.) with a thinner, mostly-automatic orchestrator.
Written after the HOB run (209 Oracle-bearing faces, 210 total).

The single most important idea: **the model work is done by Claude Code
sub-agents, and everything around it is deterministic Python.** The orchestrator's
job is to (a) generate self-contained task packets, (b) fan out agents against a
file-based contract, (c) run deterministic validate/reconcile/adjudicate steps,
(d) freeze. No Anthropic API is used (per the standing project preference).

---

## 1. Architecture: two planes

| Plane | Who | What it does | Where it lives |
|---|---|---|---|
| **Control plane** (deterministic) | Python, run via `hobkg` CLI | build task packets, validate output against schema, route candidates/rejections, reconcile extractor↔critic, adjudicate, finalize, freeze | `src/hobkg/phase3.py` |
| **Model plane** (stochastic) | Claude Code sub-agents (`Agent` tool) | read a task packet, emit structured JSON extraction; independently critique it | prompts in this doc; I/O on disk |

The two planes never share memory. They communicate **only through files** on a
fixed contract, which is what makes the whole thing resumable, auditable, and
safe to parallelize.

### The file contract

```
data/llm/
  shared_context.json          # stable across all faces (predicates, node types,
                               #   mechanic templates, known tokens) — the "system" context
  tasks/<safe_id>.json         # one self-contained input packet per Oracle-bearing face
  tasks_index.jsonl            # manifest: {face_id, card, file}
  batches/batch_NN.txt         # a list of task filenames — the unit of agent work
  extractions/<safe_id>.json   # extractor agent OUTPUT (one per face)
  critiques/<safe_id>.json     # critic agent OUTPUT (one per face)
data/review/
  llm_candidates.jsonl         # extractor outputs that passed validation
  llm_rejections.jsonl         # extractor outputs that FAILED validation (never repaired)
  llm_span_warnings.jsonl      # soft provenance drift (end-of-span overrun); audit only
  llm_accepted.jsonl           # extractor∩critic agreement (+ dispositions + reviewed_empty)
  llm_queued.jsonl             # extractor↔critic disagreements, awaiting adjudication
  llm_dispositions.jsonl       # per-item verdicts for the queue
  llm_unresolved.jsonl         # genuine ambiguity, excluded from the accepted graph
  llm_face_status.jsonl        # a status row for EVERY normalized face (denominator guard)
schema/llm_output.schema.json  # the output schema (generated from the predicate vocab)
```

`<safe_id>` = the face_id with every non-alphanumeric char replaced by `_`
(e.g. `face:bddd7e99-...:0` → `face_bddd7e99_..._0.json`). This is `phase3.safe_id()`.

---

## 2. The end-to-end sequence that was run

Every step is a single deterministic CLI call **or** a fan-out of identical
agents. `PYTHONPATH=src python -m hobkg.cli <cmd>`.

1. **Scaffold once** (already committed): `phase3.py`, `schema/llm_output.schema.json`,
   tests. Discipline: schemas + tests before any bulk extraction.
2. **`build-tasks`** → writes the 209 task packets + `shared_context.json` +
   `tasks_index.jsonl`, and (re)exports the output schema.
3. **Partition** the faces into batch manifests (`data/llm/batches/batch_NN.txt`,
   ~18 faces each → 12 batches for HOB). One agent per batch.
4. **Pilot first** (spec discipline): one extractor agent over a vertical slice
   (Recruit, Saga+Recruit-chapter, second-draw, Adventure, Storied), then
   `ingest` + one critic + `reconcile`, and eyeball the result. This caught the
   schema-strictness and span-drift problems before the full fan-out.
5. **Extractor fan-out**: N agents (2 waves of 6 for HOB), each processes one
   batch manifest and writes `extractions/<safe_id>.json` per face.
6. **`ingest`** → validates every extraction; routes to
   `llm_candidates`/`llm_rejections`; records soft `llm_span_warnings`.
7. **Critic fan-out**: N independent agents (fresh context), each reads the task
   packet + candidate and writes `critiques/<safe_id>.json`.
8. **`reconcile`** → accepts assertions on which extractor and critic agree +
   validate → `llm_accepted`; disagreements → `llm_queued`.
9. **Adjudicate** the queue: one agent reads extractor vs critic vs Oracle per
   queued face and writes `llm_dispositions.jsonl`
   (`accepted_extractor|accepted_critic|corrected|unresolved`). **Spot-check the
   verdicts** — the HOB run had two the agent rubber-stamped that were actually
   `unresolved`.
10. **`apply-dispositions`** → folds verdicts into `llm_accepted`; unresolved →
    `llm_unresolved`.
11. **`finalize-faces`** → emits `llm_face_status.jsonl` for **all** normalized
    faces and a `reviewed_empty` accepted record for any face with no Oracle text.
12. **Freeze**: canonical rebuild order is `reconcile → apply-dispositions →
    finalize-faces`; run tests; regenerate `reports/phase3_coverage.md`; commit.

For HOB, steps 5–11 also included a **closure loop**: two mechanics (Amass,
typecycling) that surfaced as `schema_extension_requests` were turned into Phase 2
templates, the 8 affected cards were re-extracted + re-critiqued (steps 5–8 on a
subset), then adjudication/finalize proceeded.

---

## 3. How the sub-agents were structured

All model work used the generic `Agent` tool (`subagent_type: general-purpose`,
which has Read/Write/Bash). Three agent roles, each with a fixed prompt template.

### 3.1 Extractor agent (one per batch)

- **Reads**: `schema/llm_output.schema.json`, `data/llm/shared_context.json`, and
  its `data/llm/batches/batch_NN.txt` → then each `data/llm/tasks/<file>`.
- **Writes**: `data/llm/extractions/<file>` — one JSON object per face.
- **Contract in the prompt**: the spec's DO/DON'T list (split abilities; identify
  trigger/cost/effect/condition/controller/optionality; resolve pronouns; cite
  exact Oracle char spans; controlled predicates only; provenance on every edge;
  no evaluative language; flag ambiguity in `unresolved`; propose a controlled-
  vocab extension only if nothing fits).
- **Returns to orchestrator**: a short summary (counts + any `unresolved` /
  extension requests). **Not** the JSON — that goes to disk. This keeps the
  orchestrator's context small regardless of set size.

### 3.2 Critic agent (one per batch, independent)

- **Reads**: the task packet + the extractor's `extractions/<file>`.
- **Writes**: `data/llm/critiques/<file>` — corrected JSON.
- **Key instruction that makes reconciliation work**: *keep correct assertions
  verbatim* — same edge `(source, predicate, target)` and same `ability_id` — so
  agreement is detectable; change only what is wrong or missing. Independence
  (fresh context, told to form its own judgment) is what satisfies the spec's
  "independent critic" requirement.

### 3.3 Adjudicator agent (one, for the queue)

- **Reads**: `llm_queued.jsonl` + per queued face the task/extraction/critique.
- **Writes**: `llm_dispositions.jsonl` with a verdict + rationale per disputed
  item, and the full objects to include.
- **Explicit instruction**: do not force everything to accepted; genuine
  ambiguity → `unresolved`. (It still over-accepted twice on HOB — always
  spot-check the borderline predicate/semantics calls yourself.)

### Why batches, not one-agent-per-face or one-agent-for-all

- One agent per face → hundreds of `Agent` calls, huge orchestration overhead.
- One agent for all 209 → context overflow, quality decay, no parallelism.
- ~18 faces/agent (~40–75k sub-agent tokens each) is the sweet spot: fits a
  sub-agent context comfortably, runs in parallel, and the file contract means a
  failed/partial batch is just a re-run of that manifest.

---

## 4. Deterministic CLI reference

```
python -m hobkg.cli build-tasks          # packets + shared_context + schema
python -m hobkg.cli build-prompt <face>  # (optional) print the full extractor prompt
python -m hobkg.cli ingest               # validate extractions -> candidates/rejections
python -m hobkg.cli reconcile            # extractor∩critic -> accepted; diffs -> queued
python -m hobkg.cli apply-dispositions   # fold llm_dispositions.jsonl into accepted
python -m hobkg.cli finalize-faces       # status for all 210 faces + reviewed_empty
python -m hobkg.cli validate             # reload + re-validate all emitted jsonl
```

Validation (hard, in `phase3.validate_output`): JSON-Schema conformance +
controlled-predicate vocabulary (enum) + provenance present on every edge +
Oracle-span **start** validity + no evaluative/value-judgment language. Soft
(recorded, non-blocking): span **end** overrun. **Invalid output is never
silently repaired** — it is rejected or queued (spec discipline #8).

---

## 5. Failure modes we hit (pre-empt these in the harness)

| Symptom | Root cause | Fix baked into the pipeline |
|---|---|---|
| 33/114 rejected on first `ingest` | schema `additionalProperties:false` rejected spec-named descriptive keys (`controller`, `duration`, `note`) | ability/edge objects allow extra descriptive keys; hard guards stay (required fields, predicate enum, provenance, no-eval, top-level strictness) |
| span "out of bounds" rejections | agents miscount the em-dash `—` / bullet `•` as multiple chars | span-**end** overrun is a soft warning, not a reject; the critic recomputes spans; `0` overruns survive into the accepted graph |
| abilities marked "disputed" for no reason | reconcile keyed ability agreement on the span, which the critic legitimately corrects | key ability agreement on stable `ability_id` (+kind), never the span |
| fabricated edges (`REFERENCES_RULE→rule:adventure` citing type-line text) | extractor over-reached | critic drops them → they land in the queue → adjudicated out |
| a new mechanic (Amass, typecycling) with no predicate | it isn't in the template set | surfaced as `schema_extension_requests`; resolved by adding a **template** (INSTANTIATES), not a new primitive predicate |
| denominator silently 209 not 210 | one face has no Oracle text (vanilla creature) | `finalize-faces` emits `reviewed_empty` + a status row for every face |
| adjudicator over-accepts | agent bias toward "critic is right" | orchestrator spot-checks borderline predicate/semantics verdicts |

---

## 6. Streamlining the next run (the orchestrator harness)

### 6.1 Kill the manual command approvals (your main pain point)

Every deterministic step in this pipeline is a **safe, read-or-local-write**
command with no external side effects. Pre-authorize them in
`.claude/settings.json` so the orchestrator runs unattended. Two ways:

- **Fastest**: run the **`/fewer-permission-prompts`** skill — it scans this
  session's transcript and writes a tailored allowlist to project settings.
- **Manual**: add a `permissions.allow` block. The commands worth allowlisting
  (all idempotent / no outbound effects):

```jsonc
// .claude/settings.json (illustrative — confirm exact tool-rule syntax for your
// harness; use /fewer-permission-prompts to generate precise entries)
{
  "permissions": {
    "allow": [
      "Bash(python -m hobkg.cli:*)",        // build-tasks/ingest/reconcile/...
      "Bash(python -m pytest:*)",
      "Bash(python -:*)",                    // read-only inspection scripts
      "Bash(git add:*)", "Bash(git status:*)", "Bash(git diff:*)",
      "Bash(git commit:*)", "Bash(git log:*)",
      "PowerShell(python -m hobkg.cli:*)",
      "PowerShell(git add:*)", "PowerShell(git status:*)", "PowerShell(git commit:*)"
    ]
  }
}
```

Deliberately **not** on the allowlist: `git push` (outward-facing — keep it
explicit), anything that deletes files, and the raw source-fetch step
(`Invoke-WebRequest`/Scryfall) which you want to run consciously and freeze.

> Note: agent spawns (`Agent`) and file `Write`/`Edit` are already the
> orchestrator's own tools; the prompts you approve are the fan-out. The friction
> was almost entirely the `Bash`/`PowerShell` deterministic calls above.

### 6.2 Make the fan-out programmatic

The HOB run issued the extractor/critic agents by hand (6 per message, 2 waves).
For a hands-off harness, drive the fan-out from a loop instead of manual messages:

- **Best fit**: the **`Workflow` tool** (multi-agent orchestration). A workflow
  script can `pipeline()` each batch through *extract → ingest-gate → critic* with
  no barrier, run the deterministic CLI between phases, and stop for your review
  at the adjudication gate. This is the natural home for "12 batches × 2 passes"
  and it keeps your main context clean. (It requires explicit opt-in — say
  "use a workflow" / "ultracode".)
- **Simpler**: keep the current `Agent`-per-batch shape but generate the N prompts
  from one template string + the batch list, and send them in as few messages as
  the concurrency cap allows.

Either way the prompts should be **template files** parameterized by
`{batch_file}` (extractor/critic) rather than pasted prose, so they don't drift
between batches.

### 6.3 Idempotency & resume (already true — rely on it)

- Every CLI step fully rewrites its outputs from inputs; safe to re-run.
- Extraction/critique are per-file; a crashed batch is re-run by pointing an
  agent at the same `batch_NN.txt`.
- `apply-dispositions` dedups; the canonical freeze order is deterministic.
- Task packets, `shared_context.json`, `tasks_index.jsonl` are **gitignored**
  (regenerable); the model **outputs** (`extractions/`, `critiques/`,
  `data/review/llm_*`) are committed as the record.

### 6.4 Quality gates the harness should enforce automatically

1. `ingest` rejections must be **0** before proceeding (else fix schema/prompt, re-run).
2. Run a **pilot** batch and require human sign-off before the full fan-out.
3. After `reconcile`, **halt at the queue** for adjudication sign-off — never
   auto-accept disagreements.
4. `finalize-faces` must report `normalized_faces == extracted + reviewed_empty`
   with a reason on every empty.
5. `apply-dispositions` must return `validation_errors: []`.

---

## 7. "Run it for a new set" checklist

Assuming Phase 0–2 exist for the set (frozen sources + normalized faces + Phase 2
templates), and the new set's mechanics have templates or are represented with
existing predicates:

1. `build-tasks` (regenerates packets + shared_context from that set's normalized data).
2. Partition into `batch_NN.txt` (~18 faces/batch).
3. Pilot batch → `ingest` → pilot critic → `reconcile` → eyeball.
4. Extractor fan-out → `ingest` (require 0 rejections).
5. Critic fan-out → `reconcile`.
6. Adjudicate the queue → spot-check → `apply-dispositions`.
7. If any mechanic surfaced as a schema-extension request, add a **template**
   (INSTANTIATES) — not a new primitive predicate — and re-expand the affected cards.
8. `finalize-faces` (disposition every normalized face).
9. Tests + coverage report + freeze commit.

The controlled-predicate vocabulary and the "template not predicate" rule are
set-independent; only the mechanic templates and the source data change per set.

---

## 8. Concrete numbers from the HOB run (for calibration)

- 210 normalized faces, 209 Oracle-bearing; 12 extractor batches + 12 critic
  batches + 1 pilot each + 1 re-expand + 1 re-critic + 1 adjudicator ≈ **29 agents**.
- Sub-agent token cost ≈ 40–125k each (larger for the critic/adjudicator passes).
- Result: 0 rejections; 417 accepted abilities; 1001 accepted edges; 40 disputed
  items → 38 accepted_critic + 2 unresolved; 0 span overruns in the accepted graph.
- Wall-clock was dominated by agent latency (minutes per batch), fully parallel.
