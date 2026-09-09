# The estimator API — one learner, blind to its features

Card 009. `deckbench.estimator` is the single code path every model in the
benchmark is fit through. Section 8 of `docs/MTG_Deck-Strength_Modeling_Benchmark.md`
holds the learner family constant so a difference between two models is
attributable to the **representation** and not to the algorithm; section 10 names
the requirement that makes that hold — *the estimator should not know how the
representation was generated.* This card builds exactly that estimator.

No model is fit against real data here, no metric is computed, and the holdout is
never opened. This is the infrastructure the modeling cards (011 T0, 012 T1, 013
T2) call, and the holdout is opened once, for all of them, at card 014.

## The one entry point

```python
fit_and_predict(
    features,            # opaque 2-D float array: rows = development observations
    outcome,             # 1-D float array aligned to the rows
    *,
    groups,              # draft id per row
    obs_ids,             # observation id per row
    objective,           # "binary" (raw outcomes) or "regression" (bump targets)
    model_id, target, representation,   # LABELS for the run record — see below
    weights=None,
    seed=20260908,
    split_parquet=..., split_manifest=..., runs_dir=...,
) -> RunResult
```

The **fitting inputs** are the feature matrix, the outcome, the optional weights,
the row groups and ids, the objective, and the frozen split (read through
`deckbench.holdout.load_dev`). That is the whole set. `model_id`, `target` and
`representation` are **labels**: they are written to the run record (section 15
requires a representation name) and are handed to no function that touches the
matrix. The core search-and-fit routine receives only arrays, an objective, the
frozen folds and a seed — so it cannot behave differently for one representation
than another.

## Blind to provenance — the load-bearing property

The estimator takes the feature matrix as an **opaque array**. It never inspects
a column name, never imports the representation builders (`deckbench.identity`
and the future KG/script builders), and never reads a feature parquet itself. The
only parquet it reads is the split, and only through `load_dev`.

The test that enforces this passes a **real** feature matrix and a **random**
matrix of the same shape through the identical call and requires both to
complete and to emit a prediction per development row. It is easy to write an
estimator that "knows nothing about representations" while quietly special-casing
a column named `base_p`; a random matrix of the same shape would break such a
path, and this one it does not.

## One grid, declared once as data

`HYPERPARAMETER_GRID` is a module-level constant — the single grid searched for
every model fit through this path. It is never rebuilt per call; a test asserts
the very same object (by identity) is used across a binary and a regression fit.
Holding the grid fixed is what lets section 8's comparison attribute a
difference to the representation rather than to a search that happened to try
harder for one model.

The grid is kept deliberately small. The first benchmark asks whether a
representation *carries* information, not whether an exhaustive search can wring
it out (section 8); a specialized graph learner is explicitly out of scope.

## Folds come from the frozen split, never re-derived

The inner cross-validation uses exactly the folds recorded in
`data/processed/model_split.parquet`. The estimator reads them via `load_dev`,
aligns them to the passed rows by `obs_id`, and cross-checks that each row's
caller-supplied group matches the split's own `draft_id` (a disagreement means a
misaligned matrix and stops the fit). It never invents its own folds and never
accepts a caller-supplied fold vector — the frozen split is the only source. A
test asserts the fold vector the estimator used equals the one in the parquet.
Because those folds are assigned per draft upstream (card 006), no draft
contributes rows to more than one inner fold; this is inherited and asserted, not
re-established.

## Two objectives, selected by the caller

* `objective="binary"` → `binary:logistic`, native metric `logloss`, for raw
  game outcomes in {0, 1}.
* `objective="regression"` → `reg:squarederror`, native metric `rmse`, for
  continuous bump/residual targets (T1, T2).

Tuning watches the learner's **native training objective** (the metric above),
which is intrinsic to the learner and needs no external panel. That is the only
place a metric appears, and it is used solely to select an iteration count and a
grid point — it is **never emitted**. No R², log loss (as an output), Brier, AUC,
or calibration quantity is computed anywhere in this card, even as a convenience.
The evaluation panel is card 010, and it operates on emitted predictions; the two
cards are decoupled in both directions.

## What a fit emits

For every fit, three artifacts are written under `runs_dir` (default
`data/runs/`, gitignored):

* **Predictions** — `<model_id>_predictions.parquet`, keyed by `obs_id`, one
  **out-of-fold** prediction per development row (each row predicted by a booster
  trained on the folds that do not contain it). No holdout row is present; a test
  asserts the emitted id set is disjoint from the holdout partition. These
  out-of-fold predictions are the honest development output the residual and
  cross-fitting targets build on.
* **Run record** — `<model_id>_run.json`, carrying the model identifier, target
  formulation, representation name, feature count, development row count, the
  split SHA256, the seed, the **chosen** hyperparameters (the grid point that
  won, not the grid that was searched), the fitted iteration count, and the
  xgboost version. A record that cannot reproduce its own fit is not a record.
* **Final booster** — `<model_id>.xgb`, fit on all development rows with the
  chosen hyperparameters, for card 014 to score once against the holdout.

## The split's identity is verified before any fit

`verify_split_hash` reads `split_sha256` from `data/splits/split_manifest.json`
and compares it to the SHA256 of the split parquet on disk. A mismatch — the
split moved after it was frozen — fails the fit closed before any data is read,
so a model is never recorded against a split that changed under it. The verified
hash is the one written into the run record.

## The holdout is never touched

Development rows are read through `deckbench.holdout.load_dev`, the **unsealed**
path that requires no card id and writes no ledger line, so ordinary fitting does
not fill the holdout ledger with noise. The estimator never routes through the
sealed reader — its source contains no reference to it, asserted by test — and a
test confirms `cycle/holdout_ledger.jsonl` is byte-identical before and after a
full fit. The holdout partition is never read, sampled, or fit on by any route.

## Determinism

xgboost is run single-threaded (its multi-threaded histogram build is not
bit-reproducible) with the seed threaded through. Two fits on the same inputs
produce byte-identical predictions — asserted both on the arrays and on the
emitted parquet bytes. The seed is declared (`DEFAULT_SEED = 20260908`) and
recorded in every run record.

## Dependency handling

xgboost is imported lazily, inside the fit path, so the module stays importable
in a graph-only checkout. The first fit without it raises `MissingDependency`
naming the package and the `modeling` extra in `pyproject.toml`. It is declared
in the registry's tech stack and in that extra.

## Self-test

```
python -m deckbench.estimator --selftest
```

fits a small synthetic binary and regression model end to end in a temporary
directory, checks determinism, confirms no holdout row is emitted and the split
hash matches, and touches no tracked file.
