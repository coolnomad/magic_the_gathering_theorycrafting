# Split and seal -- the frozen benchmark partition

Card 006. `deckbench.split` freezes the one train/test split every model in the benchmark will share, and `deckbench.holdout` makes the external holdout mechanically hard to read by accident. No feature is built, no model is fit, and no metric is computed here (benchmark sections 7, 17).

Source table: `data/processed/model_table.parquet`
Split output: `data/processed/model_split.parquet`
Split manifest: `data/splits/split_manifest.json`

## The grouping rule and why

The benchmark (section 7) prefers a player-grouped split so the same player cannot appear on both sides. The audit (`reports/modeling_data_audit.json`) records that **no persistent player identifier exists** in this dataset (`persistent_player_id_exists = false`), so that preferred control is unavailable. The chosen rule is therefore **`time_based_holdout`**: drafts are ordered by `draft_time` and the latest ~20 percent become the external holdout.

> **This is a weaker leakage control than player grouping.** With no player id, the same player can appear in both the development set and the holdout under different drafts. A time-based holdout is not treated as equivalent to a player-grouped split; it is the strongest available control given the data, and its weakness is recorded here and in the split manifest.

`rank` is a six-level skill bucket, not a player id (audit `player_identifier`). It is used **nowhere** in this card as a grouping key, a player identifier, or a stratifier; the split module reads only `obs_id, draft_id, draft_time`.

## Split by draft, never by game row

Every partition and every fold is assigned at the `draft_id` level, so no draft's games straddle a partition or fold boundary (benchmark section 7). Both properties are asserted by test: the intersection of draft ids across partitions is empty, and no `draft_id` spans two folds.

## Partition sizes

- Observations: **241561** across **43102** drafts.
- Development: **194215** rows / **34482** drafts (draft_time 2026-08-11 15:43:42 .. 2026-08-22 12:12:35).
- Holdout: **47346** rows / **8620** drafts (draft_time 2026-08-22 12:13:19 .. 2026-08-29 23:33:09).
- Holdout fraction: **0.2000** of drafts, **0.1960** of games.

Every observation is assigned exactly one partition; no row is unassigned and no row is in both.

## Cross-fitting folds

Every development observation carries one of **5** cross-fitting folds (benchmark section 3's T2 procedure). Fold membership is a deterministic hash of `(seed, draft_id)`, so every game of a draft shares a fold and no draft spans two folds. Holdout rows carry fold `-1` -- cross-fitting happens inside development only.

| fold | dev rows |
| --- | --- |
| 0 | 39280 |
| 1 | 39038 |
| 2 | 38902 |
| 3 | 38446 |
| 4 | 38549 |

## Determinism and the seed

The only randomness is the fold assignment, drawn from the declared seed **20260908** via a hash -- there is no RNG state to carry. Row order is the model table's own order. Two consecutive runs therefore produce a byte-identical `model_split.parquet`; `python -m deckbench.split --verify` rebuilds it in memory and checks it against the file on disk.

## Pinned twice, on purpose

The split parquet is pinned in two places that answer different questions. `data/splits/split_manifest.json` pins its SHA256 and is what the seal verifies before returning any holdout row -- if the split was regenerated after models were fit against it, the hash moves and the seal fails closed. `data/processed/MANIFEST.sha256` pins it alongside the four card-004/005 artifacts so every derived artifact is covered uniformly and a full rebuild is checked byte-for-byte.

## The seal

The external holdout is opened only through `deckbench.holdout.load_holdout`, which refuses to answer without a card id and a reason, verifies the split's hash against the manifest (failing closed on any mismatch), and appends one line to the append-only ledger `cycle/holdout_ledger.jsonl` every time it does answer -- before returning the rows, so an interrupted read is still recorded. A refused read appends nothing. A second read by the same card id is refused unless an explicit repeat flag is passed, and the ledger records the repeat. Ordinary development uses `deckbench.holdout.load_dev`, which returns development rows without a card id and without touching the ledger, so the ledger's signal stays high. Afterwards, how many times the holdout was opened is a countable fact rather than a recollection (benchmark sections 9, 12).
