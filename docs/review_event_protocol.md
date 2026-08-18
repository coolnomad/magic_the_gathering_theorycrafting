# Worker-Reviewer Handshake Protocol

This document is the role-neutral coordination contract for implementation and review agents in this repository. Both agents read the same protocol at startup, then follow the role assigned by the human owner. The authoritative state is committed Git history plus committed review documents; file signals are advisory conveniences for watchers.

This protocol does not declare any current phase complete.

## Roles and Authority

- Human owner: owns project goals, phase scope, final acceptance under unresolved uncertainty, and all decisions that change ontology, predicates, relation meaning, frozen artifacts, phase boundaries, or conflicting requirements.
- Worker/implementer: implements a bounded phase task or repair, validates it, documents material behavior, and commits only its own complete work.
- Reviewer: reviews one exact worker implementation commit against its parent and the governing phase/specification, validates independently, writes a structured review under `docs/`, and commits the review.

Agents may autonomously choose local implementation details, focused tests, report regeneration required by the phase, review-document numbering, and non-semantic wording improvements. Human approval is required before accepting or making ontology/predicate changes, changing relation meaning, changing frozen artifacts, expanding scope, resolving contradictory requirements, or accepting a phase while mandatory semantics remain uncertain.

## Exact-SHA Handshake

- Every review identifies the full `reviewed_commit` SHA and the full `parent_commit` SHA used for the diff.
- Every repair identifies both the review commit it addresses and the implementation SHA reviewed by that review.
- Agents act only on committed artifacts addressed to their assigned role and relevant to their current phase/SHA.
- Newer or unrelated commits must not silently retarget a review. If a newer worker commit appears before review starts, the reviewer records any skipped/superseded implementation SHAs and reviews the latest relevant worker commit. If a review already started, it finishes against the original `reviewed_commit`.
- A review is stale if its `reviewed_commit` is not the worker SHA currently awaiting review. Stale reviews are historical evidence only.
- A superseded implementation does not need a duplicate review unless the human owner requests one.

## Commit and Artifact Conventions

Use existing repository style rather than adding heavyweight machinery. Review documents for the HOB effect-semantics repair continue under:

```text
docs/hob_effect_semantics_repair_instructions_PHASE<N>_review_pt<K>.md
```

Older review naming conventions remain valid historical artifacts. New role-handshake commits should include mechanically readable trailers in the commit body when possible:

```text
Role: worker|reviewer
Phase: Phase <N>
Iteration: <phase-iteration-or-review-pt>
Reviewed-Commit: <full-sha>          # reviewer commits only
Addresses-Review: <full-sha>         # worker repair commits only
Addresses-Implementation: <full-sha> # worker repair commits only
Verdict: ACCEPT|REPAIR|REFINE_SPEC|REQUEST_DECISION|DEFER # reviewer commits only
```

Recommended commit subjects:

- Worker implementation: `Effect-semantics Phase <N><suffix>: <bounded change>`
- Worker repair: `Effect-semantics Phase <N><suffix> repair: address review <short-review-sha>`
- Reviewer: `Review Phase <N> pt<K>: <VERDICT> <short-reviewed-sha>`
- Specification-only decision: `Spec Phase <N>: <decision or clarification>`

Each new review document starts with a structured header:

```yaml
---
protocol: worker_reviewer_handshake_v1
role: reviewer
phase: Phase 4
iteration: pt1
reviewed_commit: 0123456789abcdef0123456789abcdef01234567
parent_commit: fedcba9876543210fedcba9876543210fedcba98
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 2
nonblocking_findings: 1
deferred_items: 0
---
```

`review_commit: PENDING_IN_THIS_COMMIT` is allowed because a file cannot know the commit SHA that will contain it before commit creation. After commit, the authoritative review commit is the Git commit containing the review document, recoverable with `git log -- <review-document>`.

Optional watcher signal files may be written under `docs/review_events/`, especially `docs/review_events/review_ready.json`, but they are not authoritative and must not replace the committed review document. A signal should include at least `schema_version`, `phase`, `reviewed_commit`, `review_commit`, `verdict`, `review_document`, `blocking_findings`, and `updated_at`.

## Review Outcomes

- `ACCEPT`: terminal for the reviewed implementation commit unless later human instruction reopens it. The worker stops for that bounded task or proceeds only if its next assigned task is in scope.
- `REPAIR`: blocking defect in implementation, generated artifacts, tests, provenance, determinism, or semantic fidelity. The worker produces a repair commit addressing the cited review and implementation SHAs.
- `REFINE_SPEC`: the governing specification is insufficient, contradictory, or too ambiguous for correct implementation/review. Implementation pauses until the spec is clarified.
- `REQUEST_DECISION`: a human decision is required, including ontology/predicate changes, frozen artifact changes, scope expansion, relation-meaning changes, conflicting requirements, or acceptance despite unresolved semantic uncertainty.
- `DEFER`: nonblocking work is explicitly moved to a named later phase or backlog. `DEFER` must not conceal a blocking defect for the current phase.

## State Machine

| State | Actor | Trigger | Next State | Guard |
| --- | --- | --- | --- | --- |
| Watching | Worker | Assigned phase/spec | Implementing | Worktree safety checked |
| Implementing | Worker | Validation complete | Implementation committed | Commit is complete and self-contained |
| Watching | Reviewer | New relevant worker commit | Reviewing | Commit has not already been reviewed |
| Reviewing | Reviewer | Review committed with `ACCEPT` | Accepted implementation | Review targets exact SHA |
| Reviewing | Reviewer | Review committed with `REPAIR` | Repair required | Blocking findings are cited |
| Reviewing | Reviewer | Review committed with `REFINE_SPEC` | Spec refinement required | Spec gap/conflict is cited |
| Reviewing | Reviewer | Review committed with `REQUEST_DECISION` | Decision pending | Human-only decision is cited |
| Reviewing | Reviewer | Review committed with `DEFER` | Deferred nonblocking work | Destination phase/backlog is named |
| Repair required | Worker | Repair committed | Watching for review | Repair cites review and implementation SHAs |
| Spec refinement required | Human/spec owner | Spec commit or instruction | Watching | New authority is explicit |
| Decision pending | Human owner | Decision recorded | Watching or closed | Decision identifies affected phase/SHA |
| Accepted implementation | Reviewer/human | Phase evidence complete | Phase closed | See phase-closure rules |
| Any active loop | Either | More than five repair cycles by default | Decision pending | Human owner may raise/lower limit |

Watcher rules:

- The reviewer must not review reviewer commits or review documents as implementation commits.
- The worker must not treat its own worker commits as review instructions.
- Do not create duplicate reviews for the same `reviewed_commit` unless a prior review is explicitly superseded or the human owner requests re-review.
- Do not act on partial or uncommitted files. Review committed Git objects using `git show`, `git diff <parent>..<commit>`, and generated artifacts committed or reproducibly rebuilt from that commit.
- Do not review a moving working tree as though it were a commit.
- Stop and request a decision after the bounded retry limit, recommended default five repair cycles for one phase/iteration.

## Validation and Review Standard

The worker runs relevant tests/checks before committing and records the commands and results in the commit body, phase report, lab notebook, or other phase-appropriate artifact. Validation should include deterministic rebuild checks when determinism is claimed.

The reviewer independently inspects the committed diff, runs appropriate verification, and evaluates semantic correctness, specification compliance, regressions, provenance, determinism, frozen-artifact constraints, and test adequacy. Passing tests is evidence, not acceptance by itself.

Findings should cite concrete files, symbols, tests, graph records, Oracle examples, reports, or commands. Reviews should distinguish implementation defects, specification gaps, architecture findings, new work, decision requests, deferred items, and optional improvements.

## Repository Safety

Agents may share a worktree, but separate Git worktrees are safer and preferred for long-running worker/reviewer sessions. In any mode:

- Inspect committed objects by SHA.
- Do not overwrite, reset, stash, clean, amend, rebase, or rewrite another role's commits or uncommitted changes.
- Do not incorporate another role's uncommitted files into your own commit.
- Commit only complete artifacts for your role.
- If a required committed artifact is absent or a commit is still being assembled, wait.
- If the worktree is dirty, identify which files are yours before staging, and stage paths explicitly.

## Phase Closure

Acceptance of one repair or implementation commit is not the same as closure of the whole phase. A phase may be declared closed only when the governing phase acceptance cases are satisfied, the latest relevant implementation has an `ACCEPT` review, frozen-artifact status is verified when applicable, required reports/provenance are current, deferred items are explicitly nonblocking and assigned, and no mandatory semantic uncertainty remains unresolved.

The reviewer may recommend phase closure when those conditions are met. The human owner may approve closure, reopen a phase, or require additional evidence.

## Examples

Implementation commit:

```text
Effect-semantics Phase 4a: draw and life records

Role: worker
Phase: Phase 4
Iteration: 4a
Implements: docs/hob_effect_semantics_repair_instructions.md#phase-4
Validation: pytest tests/test_effect_records.py
Validation: python scripts/build_effect_records.py
```

Structured review:

```yaml
---
protocol: worker_reviewer_handshake_v1
role: reviewer
phase: Phase 4
iteration: pt1
reviewed_commit: 1111111111111111111111111111111111111111
parent_commit: 0000000000000000000000000000000000000000
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 1
nonblocking_findings: 0
deferred_items: 0
---
```

Repair response commit:

```text
Effect-semantics Phase 4a repair: address review 2222222

Role: worker
Phase: Phase 4
Iteration: 4a-repair1
Addresses-Review: 2222222222222222222222222222222222222222
Addresses-Implementation: 1111111111111111111111111111111111111111
Validation: pytest tests/test_effect_records.py
```

## Startup Checklists

Worker:

- Read this protocol and the governing phase/specification.
- Identify the assigned phase, current implementation target, and latest relevant review verdict.
- Confirm no human-only decision is pending.
- Inspect worktree status and avoid staging unrelated files.
- Implement only the bounded task or cited repair, validate, and commit with role/SHA trailers.

Reviewer:

- Read this protocol, the governing phase/specification, existing chronological reviews, recent lab notebook entries, and relevant reports.
- Identify the latest relevant worker implementation commit and its parent.
- Confirm the commit has not already been reviewed and is not superseded.
- Review committed objects, verify frozen artifacts/tests/rebuilds as applicable, and inspect generated records directly.
- Write a new structured review document under `docs/`, commit only that review, and optionally update advisory signal files after the commit.
