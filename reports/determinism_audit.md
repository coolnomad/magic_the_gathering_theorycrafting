# Determinism audit

*Card 013 — establish which derived artifacts are actually deterministic.*

`registry.md` requires that *frozen artifacts stay byte-identical and two serial builds
agree*. This report is produced by `tools/determinism_audit.py`, which regenerates every
derived artifact several times — each in a **fresh process** with a distinct
`PYTHONHASHSEED` — and compares the bytes the code writes, never git's stored blob (under
`* text=auto` a CRLF working copy differs from an LF blob by one byte per line, which is
not a determinism signal). Run it with `python tools/determinism_audit.py --report`; it
exits non-zero if any regenerated artifact is unstable.

## What was measured before any fix (2026-09-09)

**Confirmed unstable — the only genuine case: `data/review/llm_accepted.jsonl` and
`data/review/llm_queued.jsonl`.** Two fresh regenerations (`phase3.reconcile();
phase3.finalize_faces()`, the path the test suite exercises) under different hash seeds
produced files of *identical length* but *different bytes*: for `llm_queued.jsonl`,
37 records both runs, first differing byte at offset 178; for `llm_accepted.jsonl`,
211 records both runs, first differing byte at offset 1247. In both files the multiset of
records (lines) differed, which — at equal total length — is a record differing
internally, not records reordered. The cause is in `phase3.reconcile`: `agreed_edges`,
`disputed_edges`, `agreed_abilities` and `disputed_abilities` were built by iterating
Python `set` differences/intersections, whose order is randomized per process. The order
of elements *inside* each record's list therefore varied run to run.

**The fix** sorts those set-derived keys with a total key before building the lists
(edge keys are `(source, predicate, target)` string triples; ability keys use a None-safe
total order). Records are unchanged — only their internal element order is now fixed.
Verified: two serial regenerations are byte-identical across five hash seeds, and the
canonical (order-insensitive) multiset of records is identical to the committed version
(no record added, dropped or altered). The committed `llm_accepted.jsonl` /
`llm_queued.jsonl` were rewritten once to the now-deterministic ordering so the suite
leaves the tree clean.

**Corrected premise — `card_pair_projection_audit_repair.jsonl` is stable, and not by
luck.** The card recorded this file as sorted by nothing / "stable only by luck". Measured
here, its writer sorts every record by `(source_card, target_card, relation)`, and
`add_pair` de-duplicates on exactly that triple, so the key is *total* — no ties fall back
to insertion order — and its upstream iterations are `sorted(...)`. Three fresh
regenerations are byte-identical. This is the fourth mechanism in this area to be inferred
wrong from something other than a byte comparison; `audit_repair.py` needed no change.

## Live verdicts

The table below is regenerated on every `--report` run.

Seeds this run: [0, 1, 2]. Regenerated artifacts: 69; frozen verified: 8; deckbench verified: 5; not regenerable: 40.

### Regenerated derived artifacts

| artifact | job | runs | verdict | detail |
|---|---|---|---|---|
| `data/graph_global/audit_adjudication_queue.jsonl` | audit | 3 | **stable** |  |
| `data/graph_global/audit_candidates.jsonl` | audit | 3 | **stable** |  |
| `data/graph_global/audit_repair_edges.jsonl` | audit_repair | 3 | **stable** |  |
| `data/graph_global/audit_repair_nodes.jsonl` | audit_repair | 3 | **stable** |  |
| `data/graph_global/audit_repair_queue.jsonl` | audit | 3 | **stable** |  |
| `data/graph_global/audit_repair_suppressions.jsonl` | audit_repair | 3 | **stable** |  |
| `data/graph_global/audit_results.jsonl` | audit | 3 | **stable** |  |
| `data/graph_global/card_pair_projection.jsonl` | project | 3 | **stable** |  |
| `data/graph_global/card_pair_projection_audit.jsonl` | audit | 3 | **stable** |  |
| `data/graph_global/card_pair_projection_audit_repair.jsonl` | audit_repair | 3 | **stable** |  |
| `data/graph_global/card_pair_projection_completeness.jsonl` | completeness | 3 | **stable** |  |
| `data/graph_global/card_pair_projection_equip.jsonl` | equip | 3 | **stable** |  |
| `data/graph_global/card_pair_projection_lifecycle.jsonl` | lifecycle | 3 | **stable** |  |
| `data/graph_global/card_pair_projection_mechanism.jsonl` | complete_mechanisms | 3 | **stable** |  |
| `data/graph_global/card_pair_projection_repaired.jsonl` | graph_repair | 3 | **stable** |  |
| `data/graph_global/card_ports.jsonl` | ports | 3 | **stable** |  |
| `data/graph_global/completeness_conditions.jsonl` | completeness | 3 | **stable** |  |
| `data/graph_global/completeness_edges.jsonl` | completeness | 3 | **stable** |  |
| `data/graph_global/completeness_nodes.jsonl` | completeness | 3 | **stable** |  |
| `data/graph_global/coverage.json` | coverage | 3 | **stable** |  |
| `data/graph_global/equip_conditions.jsonl` | equip | 3 | **stable** |  |
| `data/graph_global/equip_dispositions.jsonl` | equip | 3 | **stable** |  |
| `data/graph_global/equip_edges.jsonl` | equip | 3 | **stable** |  |
| `data/graph_global/equip_nodes.jsonl` | equip | 3 | **stable** |  |
| `data/graph_global/legend_edges.jsonl` | modules | 3 | **stable** |  |
| `data/graph_global/legend_nodes.jsonl` | modules | 3 | **stable** |  |
| `data/graph_global/lifecycle_edges.jsonl` | lifecycle | 3 | **stable** |  |
| `data/graph_global/lifecycle_nodes.jsonl` | lifecycle | 3 | **stable** |  |
| `data/graph_global/mechanism_conditions.jsonl` | complete_mechanisms | 3 | **stable** |  |
| `data/graph_global/mechanism_edges.jsonl` | complete_mechanisms | 3 | **stable** |  |
| `data/graph_global/mechanism_modules.jsonl` | modules | 3 | **stable** |  |
| `data/graph_global/mechanism_nodes.jsonl` | complete_mechanisms | 3 | **stable** |  |
| `data/graph_global/pair_index.jsonl` | coverage | 3 | **stable** |  |
| `data/graph_global/repair_edges.jsonl` | graph_repair | 3 | **stable** |  |
| `data/graph_global/repair_nodes.jsonl` | graph_repair | 3 | **stable** |  |
| `data/graph_global/structural_validation_set.jsonl` | coverage | 3 | **stable** |  |
| `data/llm/audit` | audit | 3 | **stable** |  |
| `data/llm/shared_context.json` | phase3_build_tasks | 3 | **stable** |  |
| `data/llm/tasks` | phase3_build_tasks | 3 | **stable** |  |
| `data/llm/tasks_index.jsonl` | phase3_build_tasks | 3 | **stable** |  |
| `data/review/llm_accepted.jsonl` | phase3_review | 3 | **stable** |  |
| `data/review/llm_candidates.jsonl` | phase3_ingest | 3 | **stable** |  |
| `data/review/llm_face_status.jsonl` | phase3_review | 3 | **stable** |  |
| `data/review/llm_queued.jsonl` | phase3_review | 3 | **stable** |  |
| `data/review/llm_rejections.jsonl` | phase3_ingest | 3 | **stable** |  |
| `data/review/llm_span_warnings.jsonl` | phase3_ingest | 3 | **stable** |  |
| `data/review/llm_unresolved.jsonl` | phase3_apply_dispositions | 3 | **stable** |  |
| `reports/completeness.md` | completeness | 3 | **stable** |  |
| `reports/coverage.md` | coverage | 3 | **stable** |  |
| `reports/equip.md` | equip | 3 | **stable** |  |
| `reports/graph_repair.md` | graph_repair | 3 | **stable** |  |
| `reports/lifecycle.md` | lifecycle | 3 | **stable** |  |
| `reports/mechanism_modules.md` | modules | 3 | **stable** |  |
| `reports/mechanism_repair.md` | complete_mechanisms | 3 | **stable** |  |
| `reports/pair_audit.md` | audit | 3 | **stable** |  |
| `reports/pair_projection.md` | project | 3 | **stable** |  |
| `reports/structural_validation.md` | coverage | 3 | **stable** |  |
| `schema/card.schema.json` | schemas | 3 | **stable** |  |
| `schema/condition.schema.json` | schemas | 3 | **stable** |  |
| `schema/edge.schema.json` | schemas | 3 | **stable** |  |
| `schema/face.schema.json` | schemas | 3 | **stable** |  |
| `schema/gate.schema.json` | schemas | 3 | **stable** |  |
| `schema/llm_output.schema.json` | phase3_build_tasks | 3 | **stable** |  |
| `schema/mechanic_detection.schema.json` | schemas | 3 | **stable** |  |
| `schema/mechanical_extraction.schema.json` | schemas | 3 | **stable** |  |
| `schema/node.schema.json` | schemas | 3 | **stable** |  |
| `schema/structured_condition.schema.json` | schemas | 3 | **stable** |  |
| `schema/token.schema.json` | schemas | 3 | **stable** |  |
| `schema/unresolved_extraction.schema.json` | schemas | 3 | **stable** |  |

### Frozen base (verified byte-identical, not regenerated)

| artifact | job | runs | verdict | detail |
|---|---|---|---|---|
| `data/graph/conditions.jsonl` | (frozen) | 0 | **stable** | byte-identical to frozen_manifest.json |
| `data/graph/edges.jsonl` | (frozen) | 0 | **stable** | byte-identical to frozen_manifest.json |
| `data/graph/gates.jsonl` | (frozen) | 0 | **stable** | byte-identical to frozen_manifest.json |
| `data/graph/nodes.jsonl` | (frozen) | 0 | **stable** | byte-identical to frozen_manifest.json |
| `data/graph_global/conditions.jsonl` | (frozen) | 0 | **stable** | byte-identical to frozen_manifest.json |
| `data/graph_global/edges.jsonl` | (frozen) | 0 | **stable** | byte-identical to frozen_manifest.json |
| `data/graph_global/frozen_manifest.json` | (frozen) | 0 | **stable** | frozen manifest; not regenerated |
| `data/graph_global/nodes.jsonl` | (frozen) | 0 | **stable** | byte-identical to frozen_manifest.json |

### Modeling arm — data/processed (verified against MANIFEST.sha256)

| artifact | job | runs | verdict | detail |
|---|---|---|---|---|
| `data/processed/card_identity_manifest.csv` | (deckbench) | 0 | **verified_manifest** | matches MANIFEST.sha256 (verified, not regenerated here) |
| `data/processed/deck_identity.parquet` | (deckbench) | 0 | **verified_manifest** | matches MANIFEST.sha256 (verified, not regenerated here) |
| `data/processed/model_split.parquet` | (deckbench) | 0 | **verified_manifest** | matches MANIFEST.sha256 (verified, not regenerated here) |
| `data/processed/model_table.parquet` | (deckbench) | 0 | **verified_manifest** | matches MANIFEST.sha256 (verified, not regenerated here) |
| `data/processed/skill_features.parquet` | (deckbench) | 0 | **verified_manifest** | matches MANIFEST.sha256 (verified, not regenerated here) |

### Derived files with no regeneration recipe here

| artifact | job | runs | verdict | detail |
|---|---|---|---|---|
| `data/graph_global/assembly_review.jsonl` | (none) | 0 | **not_regenerable** | written by `assemble` with the frozen base; not regenerated here (would touch the frozen base) |
| `data/graph_global/card_communities.jsonl` | (none) | 0 | **not_regenerable** | network/community projection; regenerable via the network layer, not wired into this harness |
| `data/graph_global/card_pair_projection_effect.jsonl` | (none) | 0 | **not_regenerable** | effect-semantics overlay (Phase 4f); regenerable via the effect-* commands, not wired into this harness |
| `data/graph_global/effect_census.jsonl` | (none) | 0 | **not_regenerable** | effect-semantics overlay (Phase 4f); regenerable via the effect-* commands, not wired into this harness |
| `data/graph_global/effect_records.jsonl` | (none) | 0 | **not_regenerable** | effect-semantics overlay (Phase 4f); regenerable via the effect-* commands, not wired into this harness |
| `data/review/human_audit_items.jsonl` | (none) | 0 | **not_regenerable** | hand-authored or agent-produced input; no deterministic producer |
| `data/review/human_audit_verdicts.jsonl` | (none) | 0 | **not_regenerable** | hand-authored or agent-produced input; no deterministic producer |
| `data/review/llm_dispositions.jsonl` | (none) | 0 | **not_regenerable** | hand-authored or agent-produced input; no deterministic producer |
| `data/review/unresolved.jsonl` | (none) | 0 | **not_regenerable** | hand-authored or agent-produced input; no deterministic producer |
| `reports/assembly.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/benchmark_phase1_audit.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/card_002_dashboard.html` | (none) | 0 | **not_regenerable** | network/community projection; regenerable via the network layer, not wired into this harness |
| `reports/effect_census.md` | (none) | 0 | **not_regenerable** | effect-semantics overlay (Phase 4f); regenerable via the effect-* commands, not wired into this harness |
| `reports/effect_reconciliation.md` | (none) | 0 | **not_regenerable** | effect-semantics overlay (Phase 4f); regenerable via the effect-* commands, not wired into this harness |
| `reports/effect_semantics.md` | (none) | 0 | **not_regenerable** | effect-semantics overlay (Phase 4f); regenerable via the effect-* commands, not wired into this harness |
| `reports/estimator_api.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/evaluation_panel.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/graph_coverage.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/harmonization_sweep.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/harmonization_sweep_final.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/harmonization_sweep_v2.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/human_audit_findings.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/human_audit_worksheet.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/kg_manual_review.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/manual_gold_set_review.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/model_table_build.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/modeling_data_audit.json` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/modeling_data_audit.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/mu_fidelity_correction.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/phase1_refreeze.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/phase3_coverage.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/sac_extract_portability.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/sac_schema_portability.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/set_network.html` | (none) | 0 | **not_regenerable** | network/community projection; regenerable via the network layer, not wired into this harness |
| `reports/skill_proxy.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/split_and_seal.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/suite_stability.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/t0_development_fits.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/unresolved.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |
| `reports/vocabulary_pilot.md` | (none) | 0 | **not_regenerable** | narrative / one-off report, not a rebuildable data artifact |

### Summary

All regenerated artifacts are byte-stable across the seeds tried; the frozen base and modeling-arm artifacts match their pinned hashes.
