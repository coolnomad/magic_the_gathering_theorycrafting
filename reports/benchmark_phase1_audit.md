# Benchmark Phase 1 audit — the frozen dataset, and a halt before model fitting

This is the report section 17 of `docs/MTG_Deck-Strength_Modeling_Benchmark.md`
requires: the consolidated record of Phase 1 (cards 003–006), and the point at
which the benchmark stops for operator review before any model is fit.

Nothing is fitted here. No holdout partition is opened. No metric is computed on
any partition. The deliverable is this report, the append-only checker built
alongside it (`tools/check_append_only.py`), and a `RESULT` entry in
`LABNOTEBOOK.md`.

Every number below was read from the frozen artifacts and their manifests, not
transcribed from the prose of the cards. Where a number appears, it was recomputed
from the parquet/CSV/JSON file named beside it. Artifact digests are pinned so a
later card can confirm the ground has not moved.

---

## 1. What Phase 1 produced

| Card | Concern | Primary artifact | SHA256 |
| --- | --- | --- | --- |
| 003 | Raw data audit | `reports/modeling_data_audit.json` | `c1b90900048e0fa0fe91624376015c8db1060185ccb4ed71c6ef0fea6192ab5c` |
| 004 | Game-level table | `data/processed/model_table.parquet` | `59576fbedd96458271766f84ccd86e5e821a0c7ee765a6cb59a078cd9810d4bb` |
| 004 | Card-identity representation | `data/processed/deck_identity.parquet` | `e09a92176cb0feb3732a50a50cfb3fa2f07d27dfcf0f4dc2394e748710d026d1` |
| 004 | Card-identity name map | `data/processed/card_identity_manifest.csv` | `73d18aee9367a6fba6cff778e1c0afc63e1cfdbd63a03387f36c785c5a351e77` |
| 005 | Historical-WR proxy `base_p` | `data/processed/skill_features.parquet` | `0f399d1fc4eb6090e66e08c5145027f162abdea92d14582293d0a572fc75d119` |
| 006 | Frozen split + folds | `data/processed/model_split.parquet` | `17c7cc7de643987ef2dcccfba27af8a11dc4ac16462e93ea2078aa10ee2e7479` |
| 006 | Split provenance / seal | `data/splits/split_manifest.json` | `fa5af944084d3862a56a03ddd1147f02661e1f16762ff3a3f3abc284af368922` |

The five `data/processed` artifacts are the ones pinned in
`data/processed/MANIFEST.sha256`; `sha256sum -c data/processed/MANIFEST.sha256`
verifies them from the repository root. The two JSON/report inputs are pinned
here by their own digest.

---

## 2. Observational unit, and the measurement that justified it

**Ratified unit: the game**, keyed by the injective 4-tuple
`(draft_id, game_time, match_number, game_number)` and hashed to `obs_id`.

The unit was not chosen by preference. The deck configuration is recorded per
game and it changes within a draft, measured on the raw file
(`reports/modeling_data_audit.json`, `within_draft`):

- **8191 of 43161 drafts (0.189778)** carry more than one deck configuration.
- **28397 of 241727 games (0.117475)** are played after a deck change.
- Distinct configurations per draft: 1 → 34970 drafts, 2 → 6636, 3 → 1314,
  4 → 210, 5 → 29, 6 → 2.

Averaging a draft's games would blend distinct decks in exactly those ~19% of
drafts. The game is therefore the unit at which "the deck that played this game"
is well defined (benchmark section 6). The split is nonetheless assigned by draft,
never by game row (section 4 below), so this choice does not create cross-partition
leakage.

---

## 3. Persistent player identifier, and what its absence implies

**No persistent player identifier exists in this dataset**
(`reports/modeling_data_audit.json`, `player_identifier.persistent_player_id_exists = false`;
echoed in `data/splits/split_manifest.json`, `persistent_player_id_exists = false`).
`rank` and `opp_rank` are six-level skill buckets, not player ids, and are
nominated nowhere as a substitute.

Consequence for leakage control: the benchmark's preferred **player-grouped
split is unavailable** (section 7 of the benchmark). The fallback used at card
006 is a **time-based external holdout** (the latest ≈20% of drafts by
`draft_time`). This is a **weaker** control: with no player id, the same player
can appear in both the development set and the holdout under different drafts.
The split manifest records this weakness explicitly and does not treat the
time-based holdout as equivalent to a player-grouped split. `rank` is used
nowhere as a grouping key, player id, or stratifier.

---

## 4. Final row counts

All counts recomputed from the parquet files named.

| Quantity | Value | Source artifact |
| --- | --- | --- |
| Observations (games) | **241727** | all four `data/processed/*.parquet` (row counts agree) |
| Drafts | **43161** | `model_split.parquet` distinct `draft_id` (34529 dev + 8632 holdout) |
| Card-identity features | **193** | `deck_identity.parquet` (194 cols − `obs_id`); `card_identity_manifest.csv` 193 rows |
| Development rows | **194348** | `model_split.parquet` `partition == dev` |
| Development drafts | **34529** | `model_split.parquet` |
| Holdout rows | **47379** | `model_split.parquet` `partition == holdout` |
| Holdout drafts | **8632** | `model_split.parquet` |
| Holdout fraction | **0.2000 of drafts, 0.1960 of games** | `split_manifest.json` |
| Cross-fitting folds (dev) | **5** | `model_split.parquet` |
| Fold sizes (dev rows) | 0 → 39316, 1 → 39067, 2 → 38915, 3 → 38479, 4 → 38571 | `model_split.parquet` |
| Holdout fold marker | −1 (all holdout rows) | `model_split.parquet` |
| Split seed | **20260908** | `split_manifest.json` |
| Split rule | `time_based_holdout` | `split_manifest.json` |

The four processed tables share one `obs_id` set exactly (verified: the table,
identity, skill and split obs-id sets are pairwise equal), so every downstream
join is total in both directions with no unmatched rows.

---

## 5. What Phase 2 may assume

Each claim below rests on a named artifact and its SHA256. A Phase 2 card must
verify these digests before relying on the claim; a mismatch means the dataset
moved and any comparison built on it is void. This is the adjudicable record the
quarantined pipeline lacked.

1. **The modeling unit is the game, and there are 241727 of them.**
   `data/processed/model_table.parquet`
   (`59576fbedd96458271766f84ccd86e5e821a0c7ee765a6cb59a078cd9810d4bb`),
   241727 rows, one per `obs_id`.

2. **The card-identity representation is `D_ij = count(card j in deck i) / deck_size_i`,
   over 193 card features, one row per observation.**
   `data/processed/deck_identity.parquet`
   (`e09a92176cb0feb3732a50a50cfb3fa2f07d27dfcf0f4dc2394e748710d026d1`),
   241727 rows × 193 features; no feature column is the outcome.

3. **The 193 feature names round-trip to their verbatim source columns.**
   `data/processed/card_identity_manifest.csv`
   (`73d18aee9367a6fba6cff778e1c0afc63e1cfdbd63a03387f36c785c5a351e77`),
   193 rows, one-to-one `source_column ↔ feature_name`.

4. **`base_p` is available as the T1 fixed baseline for every observation that
   carries a historical win-rate bucket; 166 observations carry a null `base_p`.**
   `data/processed/skill_features.parquet`
   (`0f399d1fc4eb6090e66e08c5145027f162abdea92d14582293d0a572fc75d119`),
   columns `obs_id, base_p_raw, base_p`; 166 nulls in both `base_p` and `base_p_raw`.
   `base_p` is a reliability-shrunk historical win-rate proxy and a nuisance
   representation; it is **not** a measurement of player skill and is not to be
   described as one.

5. **The train/test split is frozen and shared by every model, assigned at draft
   granularity.** `data/processed/model_split.parquet`
   (`17c7cc7de643987ef2dcccfba27af8a11dc4ac16462e93ea2078aa10ee2e7479`):
   dev 194348 rows / 34529 drafts, holdout 47379 rows / 8632 drafts, 5 dev folds,
   holdout fold −1. **No draft spans two partitions (0) and no draft spans two
   folds (0)** — recomputed from the artifact.

6. **The split's identity and the holdout seal are pinned.**
   `data/splits/split_manifest.json`
   (`fa5af944084d3862a56a03ddd1147f02661e1f16762ff3a3f3abc284af368922`)
   records `split_sha256 = 17c7cc7d…`, matching claim 5. The holdout is opened
   only through `deckbench.holdout.load_holdout`, which verifies this hash and
   appends to `cycle/holdout_ledger.jsonl` on every read.

7. **No persistent player identifier exists; leakage control is time-based, not
   player-grouped.** `reports/modeling_data_audit.json`
   (`c1b90900048e0fa0fe91624376015c8db1060185ccb4ed71c6ef0fea6192ab5c`) and the
   split manifest (claim 6).

---

## 6. Leakage checks run, and their results

All checks recomputed from the artifacts for this report.

- **No feature column derives from the outcome.** `deck_identity.parquet` does
  not contain a `won` column (verified absent). `skill_features.parquet` holds
  only `obs_id, base_p_raw, base_p`, derived from `user_game_win_rate_bucket`
  and `user_n_games_bucket`; `won` is never read in its construction.
  `model_split.parquet` holds only `obs_id, draft_id, partition, fold`, derived
  from `draft_id` and `draft_time`. **The outcome `won` appears only in
  `model_table.parquet`, as a carried metadata column — in no feature table.**
- **Split by draft, not by game row.** No `draft_id` appears in more than one
  partition (0), and no `draft_id` appears in more than one fold (0). Games from
  one draft cannot straddle train/test or a cross-fitting boundary.
- **Cross-fitting is internal to development.** Every holdout row carries fold
  −1; folds 0–4 exist only in the development partition.
- **The join surface is total.** The `obs_id` sets of the table, identity, skill
  and split artifacts are pairwise equal, so no feature is silently dropped or
  duplicated across a join.
- **The holdout was not opened by this card.** `cycle/holdout_ledger.jsonl` is
  empty (0 bytes) and byte-identical before and after this card runs; no read of
  `deckbench.holdout.load_holdout` occurred.

---

## 7. Unresolved questions and unverified assumptions

Each item is a finding, stated as an uncertainty, with the consequence of its
being wrong. None is resolved here by assumption.

1. **Declared vs observed column count disagree.** The raw-file manifest declares
   1165 columns; the file has **985** (`reports/modeling_data_audit.json`,
   `declared_vs_observed_match.columns = false`; declared drafts and rows *do*
   match). *Consequence if trusted blindly:* any Phase 2 step that reads the
   declared width, or expects 1165 columns, is off by 180 and may misalign
   columns. The observed 985 (193 × 5 card families + 20 non-card) is the
   authority; the declared count is not.

2. **Time-based holdout is a weaker leakage control than player grouping**
   (section 3). *Consequence if wrong:* if the same players recur across the
   time boundary in a way that matters, generalization estimates on the holdout
   will be optimistic. There is no player id with which to bound this risk.

3. **166 observations have a null historical win-rate bucket** (near-new players,
   all in the lowest games-played buckets: 66 at bucket 1, 100 at bucket 5;
   `reports/skill_proxy.md`, recomputed as 166 nulls in `skill_features.parquet`).
   They were **not imputed** — kept null, excluded from the `mu` estimation
   population. *Consequence:* their T1 baseline `base_p` is undefined; whether to
   keep them with a null proxy or exclude them from the modeling set is an
   operator decision this report puts in front of the review, not one Phase 2
   should make silently.

4. **15680 rows carry a deck size other than the modal 40** (max observed 60;
   rows below the legal minimum: 0; `reports/modeling_data_audit.json`,
   `deck_size`). The identity representation divides by each row's *actual* deck
   size, so the fractions remain well formed. *Consequence:* "deck size" is not
   constant across observations; whether Phase 2 restricts to 40-card decks, or
   models all sizes, is an open modeling choice, not a data defect.

5. **Within-draft deck changes are common enough that the unit is load-bearing**
   (19.0% of drafts, 11.7% of games; section 2). *Consequence if ignored:* a
   Phase 2 fit that quietly aggregates to draft level would blend distinct decks
   in those drafts and misattribute their outcomes.

6. **`mu` is a per-game mean** of `base_p_raw` (= 0.546211 over 241561
   bucket-bearing rows; `reports/skill_proxy.md`), so drafts with more games
   weight the shrinkage target more. Because the historical bucket is constant
   within a draft, this is the only weighting choice that arises; it is recorded
   rather than hidden. *Consequence if unexamined:* the shrinkage target carries
   a per-game (not per-player) weighting that a Phase 2 reader should know about.

7. **`hist_w` reliability map is inherited, not derived** (seven entries,
   λ = 5; `reports/skill_proxy.md`). Every games-played bucket observed in this
   file is present in the map; an unmapped bucket fails the run rather than being
   defaulted. *Consequence:* the map is an assumption carried from the prior R
   implementation; if a future set of the data introduces a new games bucket, the
   proxy build halts by design and the map must be extended deliberately.

---

## 8. Halt

**Phase 2 is not authorized to begin until the operator has reviewed this report.**

Section 16 of the benchmark orders the work — data audit, then target benchmark,
then representation benchmark, then causal estimation — and section 17 requires a
stop for review before model fitting. Phase 2's shape depends on what Phase 1
measured (the game/draft distinction of section 2 is real, not negligible), so
writing Phase 2 acceptance criteria before this report exists would mean writing
them against unmeasured facts. That is the failure the quarantined pipeline made.

No model is fit, no metric is computed on any partition, and no predictive
quantity is reported in this document. The dataset is frozen and pinned; the
next step is the operator's review.
