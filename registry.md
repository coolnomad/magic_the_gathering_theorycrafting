---
project_id: hobkg
status: PLANNED
default_mode: managed
created_date: 2026-09-02
updated_date: 2026-09-02
cli: claude
timeout_minutes: 120
---
# Project Registry: HOB Mechanistic Knowledge Graph

## Description

A mechanistic knowledge graph for Magic: The Gathering -- The Hobbit (HOB): a typed
multigraph of cards, faces, abilities, operations, conditions and gates, plus the
derived card-pair projections over it.

This registry brings the project under `ratchet`, the adaptive epistemic
development orchestrator. The build itself long predates that: phases 0-6 of
`docs/hob-knowledge-graph-build-spec.md` are complete and frozen, and the
effect-semantics overlay of `docs/hob_effect_semantics_repair_instructions.md`
has reached Phase 4f. What changes is how the remaining work is governed  -- 
implement, verify, review, classify, route -- rather than what the work is.

Read `docs/hob_orchestration_scope.md` before working any card. The trailer
defect in section 2 is the first thing to fix and the reason this registry
exists at all.

## Repo Path

`C:/GitHub/magic_the_gathering_theorycrafting`

## Tech Stack

- Python 3.11+
- pydantic 2
- jsonschema 4
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

## Default Checks

- python -m pytest -q
