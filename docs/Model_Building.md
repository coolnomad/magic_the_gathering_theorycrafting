> # ⚠ SUPERSEDED — 2026-09-07
>
> **This document no longer governs.** It is replaced in full by
> [`MTG_Deck-Strength_Modeling_Benchmark.md`](./MTG_Deck-Strength_Modeling_Benchmark.md).
> Do not implement against it, and do not treat any instruction here as current
> even where the benchmark is silent.
>
> It is kept, unedited below this banner, because the repository preserves dead
> ends rather than erasing them (`INSTRUCTIONS.md` §6). Two things in it remain
> historically load-bearing and are carried forward by the benchmark:
>
> * the correction that `data/processed/identity_matrix_*` is a 43,160 × 6
>   **rank-bucket** matrix and not a deck representation;
> * the reliability-shrunk historical skill proxy (`hist_w` map, λ = 5, logit-space
>   shrinkage toward μ), which the benchmark reuses as T1's fixed baseline.
>
> Where the two documents disagree — the observational unit (this one says draft,
> the benchmark prefers game), the outcome (grouped binomial vs. the T0/T1/T2
> target axis), and the model ladder (M0–M4 vs. the target × representation
> matrix) — **the benchmark wins**.
>
> Note also that commit `a0d01ce` describes the benchmark as *subsuming* this
> document and retaining it as a secondary replication benchmark. That was wrong;
> the owner's decision is supersession. See the `DECISION` entry of 2026-09-07 in
> `LABNOTEBOOK.md`.

---

We are rebuilding the MTG Premier Draft deck-strength model.

Important correction: the files currently called `identity_matrix_*` are NOT the deck identity representation. They are a 43,160 × 6 rank-bucket indicator matrix. Do not use those as the deck representation.

The identity representation used in the previous causal analysis was:

* one row per draft
* one column per card
* value = count of that card in the final deck divided by total deck size

The raw Premier Draft data should contain columns corresponding to cards in the final deck, analogous to the old R pipeline's `deck_*` columns.

## Objective

Build a reproducible modeling pipeline comparing increasingly rich deck representations while holding the outcome, skill adjustment, splits, learner family, and evaluation procedure fixed.

For now build:

M0 = skill only

M1 = skill + card identity representation

Leave clean interfaces/placeholders for:

M2 = skill + KG representation

M3 = skill + identity + KG representation

Later:

M4 = skill + identity + KG + game-script representation

Do NOT build the KG representation yet unless it already exists in the repo.

## Step 1 — Audit the source data

Inspect the formatted Premier Draft CSV and identify:

* draft identifier
* event wins
* event losses
* user historical game win-rate bucket
* user historical games-played bucket
* rank bucket
* final deck card-count columns
* timestamp if available
* actual player/user identifier if available

Report exact column names.

Important distinction:

`rank` is NOT player identity.

If there is no actual user/player identifier, say so explicitly. Do not pretend the six rank categories are six players.

## Step 2 — Build the true card-identity matrix

For each draft i and card j:

D_ij = count(card j in deck i) / deck_size_i

where

deck_size_i = sum_j count(card j in deck i)

Create:

`data/processed/draft_model_table.parquet`

containing at minimum:

* draft_id
* wins
* losses
* games = wins + losses
* raw historical WR bucket
* historical games bucket
* rank
* timestamp/player ID if available
* deck_size

Create:

`data/processed/deck_identity.parquet`

with:

* draft_id
* one normalized fraction column per card

Also save a card manifest:

`data/processed/card_identity_manifest.csv`

with:

* source column
* clean card feature name
* total count across drafts
* fraction of drafts containing card

Verify:

* all card fractions are >= 0
* row sums of card fractions are approximately 1
* no zero-size decks remain
* number of identity rows equals number of metadata rows

Do not silently discard sideboard/non-deck columns. Determine which source fields actually represent the final played deck and document the rule.

## Step 3 — Skill proxy

Reproduce the old reliability-adjusted historical skill estimate initially so the representation experiment is isolated from changes in skill estimation.

Use:

base_p_raw = user historical game win-rate bucket

Use games-played bucket as reliability information.

Start with the same shrinkage scheme as the existing R code if the input buckets match:

hist_w_map:
1 -> 1
5 -> 2
10 -> 3
50 -> 6
100 -> 8
500 -> 12
1000 -> 14

mu = mean(base_p_raw)
lambda = 5

base_p =
invlogit(
[hist_w * logit(base_p_raw) + lambda * logit(mu)]
/
[hist_w + lambda]
)

Clip probabilities away from exactly 0 and 1.

Save both `base_p_raw` and `base_p`.

This is an interim nuisance representation. Do not call it true skill.

## Step 4 — Outcome

Do NOT use `bump_obs` as the primary outcome.

We want to estimate the per-game win probability directly:

p_i = P(game win | skill, deck)

Each draft gives:

wins_i
losses_i
games_i = wins_i + losses_i

Use the grouped binomial likelihood.

For XGBoost, implement this efficiently as weighted Bernoulli/logistic learning:

label_i = wins_i / games_i
weight_i = games_i
objective = binary:logistic

This is equivalent to maximizing the binomial log-likelihood up to constants when each row represents repeated Bernoulli trials with common p_i.

Do not expand each draft into individual game rows unless needed for validation.

## Step 5 — Frozen split

Create ONE split object before model fitting and reuse it for every model.

Preferred order:

1. If actual player ID exists:

   * split by player so the same player does not cross train/test
   * within development data use grouped CV

2. If player ID does not exist but timestamp exists:

   * use earlier drafts for development and latest ~20% as external holdout
   * use time-aware or blocked CV inside development data

3. If neither exists:

   * use a seeded draft-level split
   * mark this explicitly as a weaker leakage-control design

Do NOT use rank bucket as player ID.

Save:

`data/processed/model_split.parquet`

with:

* draft_id
* split = dev/holdout
* cv_fold for dev observations

Every future representation must use these exact same rows and folds.

## Step 6 — Fit M0

Features:

X0 = [base_p]

Fit XGBoost binary logistic with weighted rows.

Use nested or at minimum inner CV on dev data to choose hyperparameters / n_estimators.

Evaluate untouched holdout.

Save:

* model
* predictions
* hyperparameters
* metrics

## Step 7 — Fit M1

Features:

X1 = [base_p, normalized card identity fractions]

Use exactly the same:

* development rows
* holdout rows
* CV folds
* outcome
* weights
* tuning grid
* metric functions

as M0.

This comparison measures incremental deck-composition signal over skill.

## Step 8 — Metrics

Primary prediction metrics should include:

1. weighted log loss
2. weighted Brier score
3. weighted calibration intercept/slope if practical
4. weighted R² / pseudo-R² clearly labeled
5. RMSE between predicted p and observed run win fraction as a secondary descriptive metric

For R², compute:

R2 = 1 - sum_i games_i * (y_i - p_hat_i)^2 /
sum_i games_i * (y_i - weighted_mean(y))^2

where y_i = wins_i / games_i.

Do NOT describe this as a theoretical ceiling.

Also calculate M0 vs M1 incremental performance:

delta_logloss
delta_brier
delta_R2

Bootstrap the holdout by draft, or by player if player IDs exist, to get uncertainty on the metric differences.

## Step 9 — Output comparison table

Produce:

`results/model_comparison.csv`

with rows:

M0_skill
M1_skill_identity

and columns such as:

* n_dev
* n_holdout
* logloss
* brier
* weighted_R2
* rmse
* calibration_slope
* best_iteration

Also print a concise console summary.

## Step 10 — Representation API

Build the code so that future feature matrices can be plugged into the same estimator.

For example:

`build_skill_features(df)`
`build_identity_features(df, identity_matrix)`
`build_kg_features(df, kg)`
`build_gamescript_features(df, kg)`

and a common function:

`fit_and_evaluate_model(model_name, feature_matrix, metadata, split)`

The estimator should not know how the representation was generated.

The eventual experiment is:

M0 = S
M1 = S + D_identity
M2 = S + Z_KG
M3 = S + D_identity + Z_KG
M4 = S + D_identity + Z_KG + Z_gamescript

## Step 11 — Validation checks

Before interpreting M1, verify:

* identity rows match draft IDs exactly
* no outcome information entered feature generation
* skill buckets are pre-draft/history variables, not current-event outcomes
* no card feature is derived from wins/losses
* card names/features are stable across rows
* train and holdout have reasonable support for common cards
* predictions remain in [0,1]

## Deliverables

Create a clean module/script structure, preferably:

`src/data/build_model_table.py`
`src/features/identity.py`
`src/features/skill.py`
`src/modeling/splits.py`
`src/modeling/metrics.py`
`src/modeling/train_xgb.py`
`scripts/01_build_model_data.py`
`scripts/02_fit_m0_m1.py`

and write:

`results/M0_M1_REPORT.md`

The report should include:

1. exact input schema discovered
2. correction of the mistaken 6-column rank matrix
3. final sample size
4. number of card identity features
5. split methodology
6. skill-proxy methodology
7. M0 results
8. M1 results
9. M1 - M0 incremental performance
10. any leakage/support concerns

Do not proceed to causal card-effect estimation yet. First establish that the deck representation improves conditional outcome prediction.
