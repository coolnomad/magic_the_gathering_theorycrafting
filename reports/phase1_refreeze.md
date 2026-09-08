# Phase-1 re-freeze — applying the operator decisions (card 008)

Section 7 of `reports/benchmark_phase1_audit.md` put two questions to the
operator at the phase-1 review. Both were answered, and card 008 applies them by
re-deriving the frozen dataset from the raw CSV under the new population
definition. Nothing is fitted, no metric is computed, and the external holdout
is not opened (`cycle/holdout_ledger.jsonl` is byte-identical, 0 bytes, before
and after).

## The two decisions

1. **Exclude the null-skill games from the modeling population.** The 166 games
   with an empty historical win-rate bucket cannot be scored by R0 (whose only
   feature is `base_p`), so an exclusion was always coming; the operator decided
   it lands at the point the population is defined rather than being carried into
   Phase 2. Measured from the raw file at run time: those 166 games belong to
   **59 drafts, every one of them entirely null** — no draft is partially
   affected — so excluding games and excluding drafts are the same operation and
   no tie-break rule is needed. The build **fails** if it ever finds a partially
   affected draft.

2. **Take the games-played buckets from what the data contains.** The inherited
   `hist_w` map carried a `1000` key that never occurs in this dataset. It was
   removed. The set of buckets the run accepts is now derived from the data; the
   weight attached to each remains the inherited modeling assumption, declared as
   data in `HIST_W_MAP`, and a bucket observed with no declared weight still
   fails the run.

## Where the exclusion is applied

The exclusion is applied **once**, in `deckbench.table`, at the point the
modeling population is defined. Every downstream table inherits that population
rather than filtering independently:

- `deckbench.identity` reads `deckbench.table.population_obs_ids()` and keeps
  only those rows.
- `deckbench.skill` reads the already-excluded `model_table.parquet`.
- `deckbench.split` reads the already-excluded `model_table.parquet` and is
  **recomputed** from scratch on the smaller population — not filtered — so the
  holdout fraction and the five fold sizes are correct on the new population
  rather than inherited from the old.

The exclusion criterion is a pre-draft covariate (the historical win-rate
bucket); `won` is never consulted, and a test asserts the excluded set is
unchanged when every outcome is flipped.

## The card-005 carve-out is removed

Card 005 permitted a structurally-absent historical win-rate bucket as a counted
null, because failing on it would have made that card's own output
unsatisfiable. With those games excluded from the population, the branch is
unreachable, and unreachable safety behaviour is worse than none. It is
**deleted**: `deckbench.skill` now fails the run on any null win-rate bucket in
the population, restoring the original intent that a null in the population is a
defect. The tests that covered the carve-out are removed or rewritten to assert
the stricter rule.

## Before and after

| Quantity | Before (card 007 freeze) | After (card 008 re-freeze) |
| --- | --- | --- |
| Observations (games) | 241,727 | **241,561** |
| Drafts | 43,161 | **43,102** |
| Null-skill games excluded | 0 (kept null) | **166** |
| Null-skill drafts excluded | 0 | **59** (all wholly null) |
| Development rows | 194,348 | **194,215** |
| Development drafts | 34,529 | **34,482** |
| Holdout rows | 47,379 | **47,346** |
| Holdout drafts | 8,632 | **8,620** |
| Holdout fraction (drafts) | 0.199995 | **0.199991** |
| Holdout fraction (games) | 0.196002 | **0.196000** |
| Dev fold sizes | 39316 / 39067 / 38915 / 38479 / 38571 | **39280 / 39038 / 38902 / 38446 / 38549** |
| Holdout time range (end) | 2026-08-29 23:39:41 | **2026-08-29 23:33:09** |
| `mu` (mean `base_p_raw`) | 0.546211 | **0.546211** (unchanged) |
| Games-played bucket set | {1, 5, 10, 50, 100, 500, 1000} | **{1, 5, 10, 50, 100, 500}** |
| `HIST_W_MAP` entries | 7 | **6** |
| Split seed | 20260908 | 20260908 (unchanged) |

`mu` is unchanged **by construction**, not by coincidence: card 005 already
computed `mu` over the rows that carried a bucket — the same 241,561 rows that
now constitute the whole population — so removing the 166 null-bucket games
removed exactly the rows that were never in the mean. The holdout time range
shrinks at the end because the previously-latest draft was one of the null-skill
drafts now excluded.

## Re-frozen artifact digests (SHA256)

| Artifact | Before | After |
| --- | --- | --- |
| `data/processed/model_table.parquet` | `59576fbe…` | `d9b4f5c2dbec67d9feeaca900a958bfbf5560f8e43df5dab6be08c42d4998750` |
| `data/processed/deck_identity.parquet` | `e09a9217…` | `2cf659d1cb154c2482655a72ed6085f3554968276b8bb8f48996159f01885c7c` |
| `data/processed/card_identity_manifest.csv` | `73d18aee…` | `8967247542e54ac258b3f38c72887ae6425e5a870d13706a093262d966ba34b9` |
| `data/processed/skill_features.parquet` | `0f399d1f…` | `4ac7ee8e5fe4551dc5b70c46df623ea69c487ef96b8c9f5ddb730ee5626889bc` |
| `data/processed/model_split.parquet` | `17c7cc7d…` | `ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4` |
| `data/splits/split_manifest.json` | `fa5af944…` | `6e69f9aa00911e3dce1e7c879e39a9f4e51e1fbd338ab94d619b764f16254163` |

`reports/modeling_data_audit.json` (card 003) is a read-only input; it is
unchanged (`c1b90900048e0fa0fe91624376015c8db1060185ccb4ed71c6ef0fea6192ab5c`).
The five `data/processed` artifacts are pinned in
`data/processed/MANIFEST.sha256` (repository-root-relative paths);
`sha256sum -c data/processed/MANIFEST.sha256` verifies them from the repository
root. Two consecutive full re-derivations produce byte-identical artifacts, and
`python -m deckbench.split --verify` confirms the split is byte-reproducible and
both of its pins are current.

## What this card does not do

It does not begin Phase 2, fit any model, compute any metric on any partition,
or open the external holdout. It re-freezes the phase-1 dataset under the
operator's decisions so that Phase 2 inherits one coherent population with no
null-handling policy left to invent.
