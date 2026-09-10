---
project_id: hobkg
status: MILESTONE_BENCHMARK_P1
default_mode: managed
created_date: 2026-09-02
updated_date: 2026-09-10
cli: claude
timeout_minutes: 120
---
# Project Registry: MTG Limited Theory -- Knowledge Graph and Deck-Strength Benchmark

## Description

Two arms of one project: a mechanistic theory of Limited Magic: The Gathering,
Draft first. `project_id` stays `hobkg` because it is the store key; the scope
is wider than the name.

**Arm 1 -- the HOB knowledge graph.** A typed multigraph of cards, faces,
abilities, operations, conditions and gates for Magic: The Gathering -- The
Hobbit, plus the derived card-pair projections over it. Phases 0-6 of
`docs/hob-knowledge-graph-build-spec.md` are complete and frozen; the
effect-semantics overlay of `docs/hob_effect_semantics_repair_instructions.md`
reached Phase 4f. Cards 001-002 built layer 2, the per-card port derivation,
across all 210 faces. Layer 3 is a set-wide network view over those ports;
layer 4, the capacity projection, is not yet built.

**Arm 2 -- the deck-strength modeling benchmark.** What deck construction
contributes to win probability once player skill is accounted for, measured over
241,727 real Premier Draft games across 43,161 drafts. Two axes held against
frozen splits, one learner family and one metric panel: target formulation (T0
raw outcome, T1 bump against the historical skill proxy, T2 bump against a
cross-fitted learned skill model) crossed with deck representation (R0 skill
only, R1 card identity, R2 knowledge graph, R3 game script, R4/R5 combinations).
`docs/MTG_Deck-Strength_Modeling_Benchmark.md` governs it and supersedes
`docs/Model_Building.md` in full.

The arms meet at R2. Whether the graph carries predictive signal that raw card
identity does not is the load-bearing empirical test of the whole project.

Both arms run as task cards under a worker/reviewer handshake. Read
`docs/hob_orchestration_scope.md` before working any card, and `INSTRUCTIONS.md`
section 8 before writing a commit message -- the trailer block must be readable
by git's own parser, not merely present in the text.

Arm 2 carries a live caution. Its previous implementation was quarantined to
`attic/haiku-2026-09-07/` on 2026-09-07: the code did not follow its
specification, and every number it produced is untrusted. It was never run as a
card -- no pre-registration, no frozen split committed before fitting, no sealed
holdout. The rebuild is card-driven from the audit up, and no model is fit until
the benchmark's section 17 audit has been reviewed.

## Repo Path

`C:/GitHub/magic_the_gathering_theorycrafting`

## Tech Stack

- Python 3.11+
- pydantic 2
- jsonschema 4
- networkx
- pandas
- numpy
- pyarrow
- scikit-learn
- xgboost
- pytest

## Dependencies

- control_plane
- adaptive_orchestrator

## Success Criteria

- Every commit carries a handshake trailer block that git's own parser can read
- The declared epoch onward rebuilds as a ratchet cycle ledger, byte-identically
- A committed phase contract exists, with each semantic invariant mapped to a named test
- The verification command set is declared in configuration, not run by hand
- The two defect classes that recurred in the Phase 6 arc are registered with live guard tests
- Frozen artifacts stay byte-identical, and two serial builds agree
- The default check suite leaves the working tree clean; no test writes to a tracked data file
- Every modeling card declares its features, metrics and decision rule before the model is fit
- The external holdout is opened once per benchmark phase, and every read is recorded
- No modeling result is reported without the uncertainty on its incremental difference
- A null incremental result is reported as a limit of the representation, never as absence of a deck effect

## Default Checks

- python -m pytest -q
