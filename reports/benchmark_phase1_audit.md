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

**This report was re-frozen at card 008.** The operator reviewed it, decided the
two open questions of section 7, and card 008 applied those decisions and
re-derived every artifact. All counts and digests below reflect the re-frozen
dataset; the amendment immediately following records what changed. The full
change log is `reports/phase1_refreeze.md`.

---

## 0. Amendment — the operator decisions applied (card 008)

Section 7 of the original report put two questions to the operator. Both were
answered at the phase-1 review, and card 008 applies them by re-deriving the
dataset from the raw CSV under a new **modeling population** definition. No model
is fit, no metric is computed, and the holdout is not opened
(`cycle/holdout_ledger.jsonl` stays byte-identical, 0 bytes).

1. **The 166 null-skill games are excluded from the modeling population.** They
   have no historical win-rate bucket and so cannot be scored by R0. Measured
   from the raw file, they belong to **59 drafts, every one entirely null** (no
   partial draft), so excluding games and excluding drafts are one operation. The
   exclusion is applied once, in `deckbench.table`, and every downstream table
   inherits that population. The split is **recomputed** on the smaller
   population, not filtered.

2. **The games-played bucket set is taken from the data.** The inherited `1000`
   `hist_w` entry never occurs in this dataset and was removed; the accepted set
   is now derived from the data and the weights remain the inherited assumption.
   Card 005's structurally-absent-null carve-out is deleted — a null win-rate
   bucket in the population now stops the run.

| Quantity | Before (card 007) | After (card 008) |
| --- | --- | --- |
| Observations (games) | 241,727 | **241,561** |
| Drafts | 43,161 | **43,102** |
| Null-skill games / drafts excluded | 0 / 0 | **166 / 59** |
| Development rows / drafts | 194,348 / 34,529 | **194,215 / 34,482** |
| Holdout rows / drafts | 47,379 / 8,632 | **47,346 / 8,620** |
| Dev fold sizes | 39316 / 39067 / 38915 / 38479 / 38571 | **39280 / 39038 / 38902 / 38446 / 38549** |
| `mu` | 0.546211 | **0.546211** (unchanged by construction) |
| Games-played buckets | {1,5,10,50,100,500,1000} | **{1,5,10,50,100,500}** |

The **halt of section 8 is now satisfied for the phase-1 dataset**: the operator
reviewed this report and the dataset is re-frozen under their decisions. Phase 2
authorization still depends on the operator writing Phase 2 acceptance criteria;
nothing here begins Phase 2.

---

## 0.1 Amendment — `mu` computed per draft (card 014)

Card 014 changed the skill proxy's shrinkage target `mu` from a **per-game** mean
of `base_p_raw` to a **per-draft** mean (one value per distinct draft), to match
the R implementation being reproduced
(`scripts/R/04_real_inference_refactored.R`: `x` is built at draft level, and
`mu <- mean(x$base_p_raw)` at line 324 is a per-draft mean). This is a **fidelity
correction, not an improvement** — a per-game mean over-samples strong players,
who play more games under the 7-wins/3-losses run structure, and pulls the target
upward. Full write-up: `reports/mu_fidelity_correction.md`.

| Quantity | Before (card 008) | After (card 014) |
| --- | --- | --- |
| `mu` | 0.546211 (per game) | **0.533339** (per draft) |
| `skill_features.parquet` SHA256 | `4ac7ee8e…` | **`8e86df3a…`** |
| `base_p_raw` | — | **unchanged for every row** |
| `base_p` | — | moves down by ≤ 0.011 (largest where `hist_w` is small) |
| Modeling population | 241,561 games / 43,102 drafts | **unchanged** |
| Frozen split (`model_split.parquet`) | `ad7f8596…` | **unchanged** (keyed on draft/time) |

Only `skill_features.parquet` moved among the manifest members; the other three
are byte-identical. Card 011's T0 fits (`data/runs/T0_R0*`, `data/runs/T0_R1*`)
were **refitted** through `deckbench.estimator.fit_and_predict` unchanged (same
seed 20260908, same frozen split, `split_sha256` still `ad7f8596…`), because R0
is `[base_p]` and R1 contains it. No model was fit against any partition here and
the holdout was not opened; `cycle/holdout_ledger.jsonl` stays byte-identical
(0 bytes). Section 5's pinned skill-proxy SHA and section 7 items 4 and 6 below
are updated accordingly.

---

## 1. What Phase 1 produced (re-frozen at card 008)

| Card | Concern | Primary artifact | SHA256 |
| --- | --- | --- | --- |
| 003 | Raw data audit | `reports/modeling_data_audit.json` | `c1b90900048e0fa0fe91624376015c8db1060185ccb4ed71c6ef0fea6192ab5c` |
| 004 / 008 | Game-level table | `data/processed/model_table.parquet` | `d9b4f5c2dbec67d9feeaca900a958bfbf5560f8e43df5dab6be08c42d4998750` |
| 004 / 008 | Card-identity representation | `data/processed/deck_identity.parquet` | `2cf659d1cb154c2482655a72ed6085f3554968276b8bb8f48996159f01885c7c` |
| 004 / 008 | Card-identity name map | `data/processed/card_identity_manifest.csv` | `8967247542e54ac258b3f38c72887ae6425e5a870d13706a093262d966ba34b9` |
| 005 / 008 / 014 | Historical-WR proxy `base_p` | `data/processed/skill_features.parquet` | `8e86df3a6212cef78bc506ddac2fcb243ce41cf715b045070f97ad8f32897470` |
| 006 / 008 | Frozen split + folds | `data/processed/model_split.parquet` | `ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4` |
| 006 / 008 | Split provenance / seal | `data/splits/split_manifest.json` | `6e69f9aa00911e3dce1e7c879e39a9f4e51e1fbd338ab94d619b764f16254163` |

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

The counts in this section are the audit's measurements over the **raw file**
(241727 games, 43161 drafts); they justified the unit before the population was
defined. The modeling population after the card-008 null-skill exclusion is
241561 games across 43102 drafts (section 4).

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

## 4. Final row counts (re-frozen at card 008)

All counts recomputed from the parquet files named; the population is
post-exclusion (the 166 null-skill games in 59 drafts are gone).

| Quantity | Value | Source artifact |
| --- | --- | --- |
| Observations (games) | **241561** | all four `data/processed/*.parquet` (row counts agree) |
| Drafts | **43102** | `model_split.parquet` distinct `draft_id` (34482 dev + 8620 holdout) |
| Null-skill games / drafts excluded | **166 / 59** | `model_table_build.md` (derived from the raw file) |
| Card-identity features | **193** | `deck_identity.parquet` (194 cols − `obs_id`); `card_identity_manifest.csv` 193 rows |
| Development rows | **194215** | `model_split.parquet` `partition == dev` |
| Development drafts | **34482** | `model_split.parquet` |
| Holdout rows | **47346** | `model_split.parquet` `partition == holdout` |
| Holdout drafts | **8620** | `model_split.parquet` |
| Holdout fraction | **0.199991 of drafts, 0.196000 of games** | `split_manifest.json` |
| Cross-fitting folds (dev) | **5** | `model_split.parquet` |
| Fold sizes (dev rows) | 0 → 39280, 1 → 39038, 2 → 38902, 3 → 38446, 4 → 38549 | `model_split.parquet` |
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

1. **The modeling unit is the game, and there are 241561 of them** (the raw file
   has 241727; the 166 null-skill games are excluded from the population).
   `data/processed/model_table.parquet`
   (`d9b4f5c2dbec67d9feeaca900a958bfbf5560f8e43df5dab6be08c42d4998750`),
   241561 rows, one per `obs_id`.

2. **The card-identity representation is `D_ij = count(card j in deck i) / deck_size_i`,
   over 193 card features, one row per observation.**
   `data/processed/deck_identity.parquet`
   (`2cf659d1cb154c2482655a72ed6085f3554968276b8bb8f48996159f01885c7c`),
   241561 rows × 193 features; no feature column is the outcome.

3. **The 193 feature names round-trip to their verbatim source columns.**
   `data/processed/card_identity_manifest.csv`
   (`8967247542e54ac258b3f38c72887ae6425e5a870d13706a093262d966ba34b9`),
   193 rows, one-to-one `source_column ↔ feature_name`.

4. **`base_p` is available as the T1 fixed baseline for every observation in the
   population; there are no null values.** `data/processed/skill_features.parquet`
   (`8e86df3a6212cef78bc506ddac2fcb243ce41cf715b045070f97ad8f32897470`,
   re-emitted at card 014 with `mu` per draft; see § 0.1),
   columns `obs_id, base_p_raw, base_p`; **0 nulls** in either column (the 166
   null-bucket games were excluded from the population at card 008, so a null
   here now fails the build). `base_p` is a reliability-shrunk historical
   win-rate proxy and a nuisance representation; it is **not** a measurement of
   player skill and is not to be described as one.

5. **The train/test split is frozen and shared by every model, assigned at draft
   granularity.** `data/processed/model_split.parquet`
   (`ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4`):
   dev 194215 rows / 34482 drafts, holdout 47346 rows / 8620 drafts, 5 dev folds,
   holdout fold −1. **No draft spans two partitions (0) and no draft spans two
   folds (0)** — recomputed from the artifact.

6. **The split's identity and the holdout seal are pinned.**
   `data/splits/split_manifest.json`
   (`6e69f9aa00911e3dce1e7c879e39a9f4e51e1fbd338ab94d619b764f16254163`)
   records `split_sha256 = ad7f8596…`, matching claim 5. The holdout is opened
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

3. **RESOLVED at card 008 — the 166 null-win-rate games are excluded from the
   modeling population.** They were near-new players (66 at games-played bucket 1,
   100 at bucket 5) with no historical win rate, so R0 cannot score them. The
   operator decided the exclusion lands at the population definition rather than
   being carried into Phase 2. Measured from the raw file, all 166 belong to 59
   **wholly-null** drafts, so games and drafts are excluded as one operation
   (241727 → 241561 games, 43161 → 43102 drafts). `skill_features.parquet` now
   carries **0 nulls**, and a null win-rate bucket in the population fails the
   build. There is no longer a null-handling policy for Phase 2 to invent.

4. **RESOLVED at card 014 — the 15680 non-modal deck sizes are ordinary
   41-card decks, not a data anomaly.** Of the 15,680 rows with a deck size other
   than the modal 40 (max observed 60; rows below the legal minimum: 0;
   `reports/modeling_data_audit.json`, `deck_size`), **13,424 are 41-card decks —
   5.55% of all rows** — which is an unremarkable Limited deckbuilding choice
   (running one extra card). Everything from 42 upward totals **2,256 rows,
   0.93%**, and 60-card decks number **five**. The identity representation divides
   by each row's *actual* deck size, so the fractions remain well formed at every
   size. This is a normal distribution of deck sizes, not a defect; the item is
   **closed**. Whether a later phase restricts to 40-card decks or models all
   sizes remains an ordinary modeling choice, but there is nothing here to
   characterise further.

5. **Within-draft deck changes are common enough that the unit is load-bearing**
   (19.0% of drafts, 11.7% of games; section 2). *Consequence if ignored:* a
   Phase 2 fit that quietly aggregates to draft level would blend distinct decks
   in those drafts and misattribute their outcomes.

6. **RESOLVED at card 014 — `mu` is now a per-draft mean.** `mu` was a per-game
   mean of `base_p_raw` (= 0.546211), so drafts with more games weighted the
   shrinkage target more. Card 014 changed it to a **per-draft** mean
   (= **0.533339**; one value per draft) to match the R implementation being
   reproduced (`scripts/R/04_real_inference_refactored.R` line 324; see § 0.1 and
   `reports/mu_fidelity_correction.md`). Because the historical bucket is constant
   within a draft, the per-draft value is well defined and the earlier per-game
   weighting is gone. This is a fidelity correction, not a change to skill
   estimation. (The per-game value was itself unchanged by the card-008 re-freeze,
   since the excluded null games never carried a bucket and so were never in the
   mean.)

7. **`hist_w` reliability map is inherited, not derived** (six entries after
   card 008, λ = 5; `reports/skill_proxy.md`). The inherited `1000` entry, which
   this dataset never contains, was removed; the map's keys are now exactly the
   games-played buckets the population presents, and the accepted set is derived
   from the data. An unmapped bucket fails the run rather than being defaulted.
   *Consequence:* the weights are an assumption carried from the prior R
   implementation; if a future set introduces a new games bucket, the proxy build
   halts by design and the map must be extended deliberately.

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
quantity is reported in this document. The dataset is frozen and pinned.

**Update (card 008):** the operator's review has since happened — its two
decisions are recorded in section 0 and applied by card 008, which re-froze the
dataset. The dataset is now coherent with those decisions and carries no
outstanding null-handling policy. Phase 2 still begins only when the operator
sets its acceptance criteria; card 008 does not start it.
