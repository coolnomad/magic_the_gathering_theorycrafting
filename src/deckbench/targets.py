"""T0 (card 011), T1 (card 015) and T2 (card 016): development fits for R0 and R1.

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md``. This module fits the
first three rows of the benchmark's target axis against the two representations
phase 1 can already supply:

* **R0 -- skill only.** One feature, ``base_p`` (the reliability-shrunk
  historical win-rate proxy of card 005). This is also M0, the benchmark's own
  skill-only baseline; ``base_p`` is a nuisance representation and is **never**
  described as skill.
* **R1 -- skill plus card identity.** ``base_p`` plus the 193 normalized
  card-fraction columns of card 004, so 194 features.

Three target formulations share that assembly, differing only in what the
estimator is asked to predict and under which objective:

* **T0 -- raw outcome (card 011).** The target is the game outcome ``won`` in
  {0, 1}, fitted with the **binary** objective. The estimator's prediction is a
  win probability directly.
* **T1 -- bump against the fixed proxy (card 015).** The target is the residual
  ``B_i = won_i - base_p_i``, fitted with the **regression** objective. A win
  probability is *reconstructed* as ``p_i = base_p_i + B_hat_i`` and clipped into
  the unit interval for scoring. T1 exists to test whether removing the dominant
  skill component makes deck signal easier to recover -- that is H2 in section 14,
  a hypothesis and not an assumption. This card produces one row of the table the
  question needs; it does not answer it and must not try.
* **T2 -- bump against a cross-fitted learned baseline (card 016).** The target is
  the residual ``B_i = won_i - m_hat_-i(S_i)``, fitted with the **regression**
  objective, where ``m_hat_-i`` is a *learned* estimate of ``E[Y|S]`` predicted
  **out of fold** -- exactly ``T0_R0``'s stored out-of-fold predictions. No
  observation ever helped train the baseline it is residualized against. The
  probability is *reconstructed* as ``p_i = m_hat_-i(S_i) + B_hat_i`` on
  development rows and clipped for scoring; card 017 reconstructs on the holdout
  with the full-data ``m_hat(S)`` (``T0_R0.xgb``), where holdout rows never
  trained it and it is honest by construction. ``m_hat`` is a baseline, **never**
  a measurement of a player. T2 is the third row H2 needs; producing it is not
  testing the ordering.

What this module does, and deliberately does not do:

* It **assembles** each representation from the frozen phase-1 tables only --
  ``skill_features.parquet`` for ``base_p``, ``deck_identity.parquet`` for the
  card fractions, ``model_table.parquet`` for the outcome -- joined on ``obs_id``
  and restricted to the development partition (read through
  :func:`deckbench.holdout.load_dev`). The join must be total: a development
  ``obs_id`` missing from any table stops the run. No row is imputed, dropped, or
  reweighted; the population was settled at card 008. **T0, T1 and T2 fit the same
  two matrices** -- only the target and the objective change (and, for T2, the
  baseline vector that forms the residual) -- so a difference between the target
  rows comes from the formulation and nothing else.
* For T2 it **reuses ``T0_R0``'s artifacts and refits nothing.** The baseline
  ``m_hat_-i`` is read from ``T0_R0``'s out-of-fold predictions parquet, joined on
  ``obs_id`` (the join must be total); before it is used, ``T0_R0``'s run record
  is validated (target, representation, objective, feature count, seed and split
  hash) so the residual is never formed against the wrong baseline. The full-data
  ``m_hat`` (``T0_R0.xgb``) is left for card 017.
* It **fits nothing itself.** Every fit goes through
  :func:`deckbench.estimator.fit_and_predict`; this module constructs no learner,
  no grid, and no folds of its own. The one place it touches xgboost directly is
  the timing probe, which uses the estimator's own grid point, base parameters,
  and frozen fold vector to *measure* -- it does not fit a recorded model.
* It **de-risks by order.** R0 (one feature, seconds) is fitted and its run
  record written to disk *before* any R1 fitting begins, so the real path --
  split-hash verification, fold alignment, out-of-fold prediction, run record --
  is proven end to end where failure costs nothing.
* Before each full R1 grid search it runs a **timing probe**: a single grid point
  on a single fold, whose measured seconds project the full search. If the
  projection exceeds :data:`R1_FIT_BUDGET_SECONDS` the build stops after R0,
  records the projection and the reason, and reports R1 as not attempted rather
  than starting a search it cannot finish.
* For T1 and T2 it **reconstructs and measures.** ``p = base + B_hat`` (with
  ``base`` the fixed proxy for T1, the out-of-fold ``m_hat_-i`` for T2) has no
  arithmetic guarantee of landing inside [0, 1]; the reconstruction is clipped to
  the panel's declared clip bound and **the number of rows clipped at each end is
  counted and reported**. How often the additive decomposition escapes the unit
  interval is direct evidence about section 2, not a detail to suppress.
* It applies the **card-010 panel** to each fitted model's out-of-fold
  development predictions and records the metrics -- as a diagnostic only. These
  are development metrics, contaminated by the same folds that selected the
  hyperparameters; **no comparison between R0 and R1, and none among T0, T1 and
  T2, is concluded from them.** The benchmark's answer is card 017's to give once,
  on the untouched holdout.
* It **never opens the holdout.** No holdout row is read, and
  ``cycle/holdout_ledger.jsonl`` is untouched.

Run it with::

    python -m deckbench.targets --fit        # fit T0 R0/R1, write the T0 report
    python -m deckbench.targets --fit-t1      # fit T1 R0/R1, write the T1 report
    python -m deckbench.targets --fit-t2      # fit T2 R0/R1, write the T2 report
    python -m deckbench.targets --verify      # check the artifacts every fit produced
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from numpy.typing import NDArray

from deckbench import estimator, evaluation
from deckbench.holdout import load_dev

if TYPE_CHECKING:
    from collections.abc import Sequence

FloatArray = NDArray[np.float64]

# Paths, anchored to the same repository root the estimator uses.
REPO_ROOT = estimator.REPO_ROOT
PROCESSED_DIR = estimator.PROCESSED_DIR
RUNS_DIR = estimator.RUNS_DIR
SPLIT_PARQUET = estimator.SPLIT_PARQUET
SPLIT_MANIFEST = estimator.SPLIT_MANIFEST
MODEL_TABLE_PARQUET = PROCESSED_DIR / "model_table.parquet"
SKILL_FEATURES_PARQUET = PROCESSED_DIR / "skill_features.parquet"
DECK_IDENTITY_PARQUET = PROCESSED_DIR / "deck_identity.parquet"
LEDGER_PATH = REPO_ROOT / "cycle" / "holdout_ledger.jsonl"
REPORT_MD = REPO_ROOT / "reports" / "t0_development_fits.md"
REPORT_T1_MD = REPO_ROOT / "reports" / "t1_development_fits.md"
REPORT_T2_MD = REPO_ROOT / "reports" / "t2_development_fits.md"

# The three target formulations this module implements. T0 (card 011) predicts
# the raw Bernoulli outcome; T1 (card 015) predicts the continuous residual bump
# against the fixed proxy; T2 (card 016) predicts the residual bump against a
# cross-fitted learned baseline. ``TARGET`` is retained as the T0 name; the
# card-011 code paths default to it.
TARGET_T0 = "T0"
TARGET_T1 = "T1"
TARGET_T2 = "T2"
TARGET = TARGET_T0
TARGETS = (TARGET_T0, TARGET_T1, TARGET_T2)

# The targets that reconstruct a probability from a bump and therefore write a
# reconstruction artifact ``verify`` must inspect. T0 predicts a probability
# directly and writes none.
RECONSTRUCTION_TARGETS = (TARGET_T1, TARGET_T2)

# The T2 baseline artifact. ``m(S) = E[Y|S]`` fitted on R0 with the binary
# objective and predicted out of fold is exactly what card 011 produced as
# ``T0_R0``: its predictions parquet is the out-of-fold ``m_hat_-i(S_i)`` T2's
# residual is formed against, and its booster is the full-data ``m_hat(S)`` card
# 017 reconstructs the holdout with. This card reuses both and refits neither.
BASELINE_MODEL_ID = "T0_R0"

# Column names in the frozen tables.
OBS_ID_COL = "obs_id"
BASE_P_COL = "base_p"
OUTCOME_COL = "won"
PARTITION_COL = "partition"
HOLDOUT = "holdout"

# The raw outcome is stored as a string; it is read as a Bernoulli {0, 1}. The
# mapping is exact and total -- any other value stops the run rather than being
# coerced to a class.
WON_MAP: dict[str, float] = {"True": 1.0, "False": 0.0}

# The two representations phase 1 can supply.
R0 = "R0"
R1 = "R1"

# Run-record model ids, keyed by target then representation. :func:`verify` walks
# every entry, so T0, T1 and T2 artifacts are all inspected. Card 011 shipped a
# flat ``{R0, R1}`` dict that named only the T0 models, which left ``verify``
# blind to anything T1 produced.
MODEL_IDS: dict[str, dict[str, str]] = {
    TARGET_T0: {R0: "T0_R0", R1: "T0_R1"},
    TARGET_T1: {R0: "T1_R0", R1: "T1_R1"},
    TARGET_T2: {R0: "T2_R0", R1: "T2_R1"},
}

# The estimator objective each target is fitted under. T0 predicts the Bernoulli
# outcome; T1 and T2 predict a continuous residual. Fitting a residual with a
# logistic objective is a category error the learner will not catch, because the
# target still looks like a float -- so the objective is selected here, by target,
# and ``verify`` checks the recorded objective matches.
TARGET_OBJECTIVE: dict[str, str] = {
    TARGET_T0: estimator.BINARY,
    TARGET_T1: estimator.REGRESSION,
    TARGET_T2: estimator.REGRESSION,
}

# The feature counts the frozen phase-1 dataset yields, used by ``verify`` to
# check the tracked run records: R0 is base_p alone; R1 is base_p plus the 193
# card fractions. ``assemble`` itself checks internal consistency against the
# actual number of identity columns rather than this constant, so it stays
# correct on a synthetic fixture with a different card count.
N_FEATURES: dict[str, int] = {R0: 1, R1: 194}

# The executor budget for the R1 grid search. The registry allows the executor
# 120 minutes for the whole card; this reserves 90 of them for the R1 fit alone,
# leaving margin for R0, the probe, the panel, the report and the checks. If the
# probe's projection exceeds this, the build stops after R0 and records why rather
# than starting a search it may not finish. Declared as data so the threshold is
# visible and changeable in one place.
R1_FIT_BUDGET_SECONDS: float = 5400.0

# The reconstruction artifact's columns (T1 and T2): the raw bump prediction, the
# base it is added to, the reconstructed probability before clipping, and the
# reconstructed probability after clipping into the unit interval. The base column
# is named ``base_p`` for T1 (the fixed proxy) and :data:`BASELINE_COL` for T2
# (the cross-fitted ``m_hat_-i``), so the artifact never mislabels which quantity
# the bump was added to.
BUMP_COL = "bump_prediction"
BASELINE_COL = "baseline"
RECON_RAW_COL = "reconstructed_raw"
RECON_PROB_COL = "reconstructed_prob"


class JoinNotTotal(ValueError):
    """Raised when a development obs_id is absent from a frozen feature table.

    The join between the split's development rows and a representation table must
    be total: a missing id means the population moved under the representation, so
    the run stops rather than fitting a partial matrix.
    """


class UnexpectedOutcomeValue(ValueError):
    """Raised when the raw outcome column carries a value outside :data:`WON_MAP`."""


class RepresentationUnknown(ValueError):
    """Raised when a representation other than R0 or R1 is requested."""


class TargetUnknown(ValueError):
    """Raised when a target other than T0, T1 or T2 is requested."""


class FeatureCountMismatch(ValueError):
    """Raised when an assembled matrix does not carry the expected feature count."""


class BaselineRecordInvalid(ValueError):
    """Raised when the T2 baseline (``T0_R0``) does not describe what T2 needs.

    Before T2 residualizes against ``T0_R0``'s out-of-fold predictions, that fit's
    run record is validated: it must be the T0 raw-outcome model on R0, fitted
    under the binary objective with one feature, the card's seed, and the split
    hash pinned in the manifest. Any mismatch stops the run rather than silently
    forming the residual against the wrong baseline.
    """


# --------------------------------------------------------------------------
# The data inputs, bundled so tests can wire a synthetic fixture in one place.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Sources:
    """The frozen phase-1 artifacts each fit is assembled from.

    Defaults are the real frozen paths; a test overrides them to point at a small
    synthetic fixture. Nothing here is re-derived -- these are read, joined on
    ``obs_id`` and restricted to the development partition.
    """

    split_parquet: Path = SPLIT_PARQUET
    split_manifest: Path = SPLIT_MANIFEST
    skill_parquet: Path = SKILL_FEATURES_PARQUET
    identity_parquet: Path = DECK_IDENTITY_PARQUET
    model_table: Path = MODEL_TABLE_PARQUET


# The frozen phase-1 inputs, as a shared immutable default. ``Sources`` is a
# frozen dataclass, so one singleton is safe to reuse as a call default.
DEFAULT_SOURCES = Sources()


# --------------------------------------------------------------------------
# Assembly -- from the frozen tables only, joined on obs_id, dev rows only.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Assembled:
    """One representation's development matrix, aligned to the split's dev order.

    ``base_p`` is carried explicitly, in the same row order as ``features``,
    regardless of representation: R0's single feature is exactly ``base_p``, and
    R1 has it as column 0, but T1 needs the proxy as a standalone vector to form
    the residual target and to reconstruct a probability, so it is kept separate
    rather than fished back out of the feature matrix.
    """

    representation: str
    obs_ids: list[str]
    groups: list[str]
    outcome: FloatArray
    base_p: FloatArray
    features: FloatArray
    feature_names: list[str]


def _dev_order(split_parquet: Path) -> tuple[list[str], list[str]]:
    """Development ``obs_id`` and ``draft_id``, in the frozen split's row order.

    Read through :func:`deckbench.holdout.load_dev`, the unsealed path: no card
    id, no ledger line, no holdout row. This order fixes the row order of every
    assembled matrix, so R0 and R1 predict the same rows in the same sequence.
    """
    dev = load_dev(split_parquet)
    return dev.column("obs_id").to_pylist(), dev.column("draft_id").to_pylist()


def _base_p_by_obs(skill_parquet: Path) -> dict[str, float]:
    """Map ``obs_id`` to ``base_p`` from the frozen skill-proxy table."""
    tbl = pq.read_table(skill_parquet, columns=[OBS_ID_COL, BASE_P_COL])
    keys: list[str] = tbl.column(OBS_ID_COL).to_pylist()
    vals: list[float] = tbl.column(BASE_P_COL).to_pylist()
    return {k: float(v) for k, v in zip(keys, vals, strict=True)}


def _outcome_by_obs(model_table: Path) -> dict[str, float]:
    """Map ``obs_id`` to the raw outcome as a {0, 1} float, or fail on an odd value.

    Reads only ``obs_id`` and ``won`` from the model table. The mapping is exact
    and total; nothing is imputed. A value outside :data:`WON_MAP` stops the run.
    """
    tbl = pq.read_table(model_table, columns=[OBS_ID_COL, OUTCOME_COL])
    keys: list[str] = tbl.column(OBS_ID_COL).to_pylist()
    raw: list[str] = tbl.column(OUTCOME_COL).to_pylist()
    out: dict[str, float] = {}
    for obs_id, value in zip(keys, raw, strict=True):
        if value not in WON_MAP:
            raise UnexpectedOutcomeValue(
                f"observation {obs_id!r} has outcome {value!r}, not one of "
                f"{sorted(WON_MAP)}; the raw outcome is never imputed or coerced."
            )
        out[obs_id] = WON_MAP[value]
    return out


def _identity_matrix(order: Sequence[str], identity_parquet: Path) -> tuple[FloatArray, list[str]]:
    """The card-fraction columns, reordered to ``order``. The join must be total."""
    tbl = pq.read_table(identity_parquet)
    names = [c for c in tbl.column_names if c != OBS_ID_COL]
    ids: list[str] = tbl.column(OBS_ID_COL).to_pylist()
    position = {obs_id: i for i, obs_id in enumerate(ids)}
    missing = [obs_id for obs_id in order if obs_id not in position]
    if missing:
        raise JoinNotTotal(
            f"{len(missing)} development obs_id(s) are absent from "
            f"{identity_parquet.name}; the first is {missing[0]!r}. The identity "
            "join is not total and the run stops."
        )
    columns = [
        np.asarray(tbl.column(name).to_numpy(zero_copy_only=False), dtype=np.float64)
        for name in names
    ]
    full = np.column_stack(columns)
    idx = np.asarray([position[obs_id] for obs_id in order], dtype=np.int64)
    return full[idx], names


def _require_total(order: Sequence[str], mapping: dict[str, float], source: str) -> None:
    missing = [obs_id for obs_id in order if obs_id not in mapping]
    if missing:
        raise JoinNotTotal(
            f"{len(missing)} development obs_id(s) are absent from {source}; the "
            f"first is {missing[0]!r}. The join is not total and the run stops."
        )


def assemble(representation: str, sources: Sources = DEFAULT_SOURCES) -> Assembled:
    """Assemble one representation's development matrix from the frozen tables.

    R0 is ``base_p`` alone; R1 is ``base_p`` plus the card fractions. Every join
    is on ``obs_id`` and must be total over the development partition. No row is
    imputed, dropped, or reweighted -- the population is inherited from card 008.
    The assembled feature count is checked for internal consistency: R0 is exactly
    one column, R1 is exactly one column plus every identity column. The result is
    target-agnostic; T0 and T1 both fit exactly this matrix.
    """
    if representation not in (R0, R1):
        raise RepresentationUnknown(
            f"representation {representation!r} is not supported by this module; "
            f"choose one of {(R0, R1)}."
        )
    obs_ids, groups = _dev_order(sources.split_parquet)
    base_p_map = _base_p_by_obs(sources.skill_parquet)
    outcome_map = _outcome_by_obs(sources.model_table)
    _require_total(obs_ids, base_p_map, f"{sources.skill_parquet.name} base_p")
    _require_total(obs_ids, outcome_map, f"{sources.model_table.name} won")

    base_p = np.asarray([base_p_map[o] for o in obs_ids], dtype=np.float64)
    outcome = np.asarray([outcome_map[o] for o in obs_ids], dtype=np.float64)

    if representation == R0:
        features: FloatArray = base_p.reshape(-1, 1)
        feature_names = [BASE_P_COL]
        expected = 1
    else:
        cards, card_names = _identity_matrix(obs_ids, sources.identity_parquet)
        features = np.column_stack([base_p, cards])
        feature_names = [BASE_P_COL, *card_names]
        expected = 1 + len(card_names)

    if features.shape[1] != expected:
        raise FeatureCountMismatch(
            f"{representation} assembled {features.shape[1]} feature columns; "
            f"expected {expected}."
        )
    return Assembled(
        representation=representation,
        obs_ids=obs_ids,
        groups=groups,
        outcome=outcome,
        base_p=base_p,
        features=features,
        feature_names=feature_names,
    )


# --------------------------------------------------------------------------
# The T2 learned baseline -- reused from T0_R0, validated, never refitted.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Baseline:
    """The cross-fitted learned baseline ``m_hat_-i`` T2 residualizes against.

    ``by_obs`` maps every development ``obs_id`` to ``T0_R0``'s stored out-of-fold
    prediction -- the estimate of ``E[Y|S]`` for that row from a booster trained
    without that row's fold. ``predictions_path`` and ``model_path`` name the
    consumed artifacts, and ``run_record`` carries ``T0_R0``'s validated record
    (its chosen hyperparameters make the baseline reproducible from the record
    alone). The full-data ``m_hat`` booster at ``model_path`` is **not** used here;
    it is card 017's, for reconstructing holdout rows it never trained on.
    """

    by_obs: dict[str, float]
    predictions_path: Path
    model_path: Path
    run_record: dict[str, object]

    def aligned(self, order: Sequence[str]) -> FloatArray:
        """The baseline vector in ``order``'s row order; fail if the join is not total."""
        missing = [obs_id for obs_id in order if obs_id not in self.by_obs]
        if missing:
            raise JoinNotTotal(
                f"{len(missing)} development obs_id(s) are absent from the T2 "
                f"baseline predictions; the first is {missing[0]!r}. The baseline "
                "join is not total and the run stops."
            )
        return np.asarray([self.by_obs[obs_id] for obs_id in order], dtype=np.float64)


def load_baseline(
    runs_dir: Path = RUNS_DIR,
    expected_split_sha: str | None = None,
    expected_seed: int = estimator.DEFAULT_SEED,
) -> Baseline:
    """Load and validate ``T0_R0``'s out-of-fold predictions as the T2 baseline.

    ``T0_R0`` is the learned skill baseline ``m(S) = E[Y|S]`` fitted on R0 with the
    binary objective; its stored predictions are the out-of-fold ``m_hat_-i(S_i)``.
    The run record is validated **before** the predictions are used -- target,
    representation, objective, feature count, seed and split hash must all match --
    so the residual is never formed against the wrong baseline. This refits
    nothing; it reuses the artifacts card 011 already produced. Pass
    ``expected_split_sha`` (the manifest hash) to bind the baseline to the same
    frozen split every fit verifies against.
    """
    record_path = runs_dir / f"{BASELINE_MODEL_ID}_run.json"
    if not record_path.exists():
        raise BaselineRecordInvalid(
            f"the T2 baseline run record {record_path} is missing; fit T0_R0 "
            "(`python -m deckbench.targets --fit`) before fitting T2."
        )
    record = json.loads(record_path.read_text(encoding="utf-8"))

    problems: list[str] = []
    if record.get("target") != TARGET_T0:
        problems.append(f"target is {record.get('target')!r}, expected {TARGET_T0!r}")
    if record.get("representation") != R0:
        problems.append(f"representation is {record.get('representation')!r}, expected {R0!r}")
    if record.get("objective") != estimator.BINARY:
        problems.append(
            f"objective is {record.get('objective')!r}, expected {estimator.BINARY!r}"
        )
    if record.get("n_features") != 1:
        problems.append(f"n_features is {record.get('n_features')!r}, expected 1")
    if record.get("seed") != expected_seed:
        problems.append(f"seed is {record.get('seed')!r}, expected {expected_seed}")
    if expected_split_sha is not None and record.get("split_sha256") != expected_split_sha:
        problems.append("split_sha256 does not match the manifest")
    if problems:
        raise BaselineRecordInvalid(
            f"{BASELINE_MODEL_ID} run record is not the baseline T2 requires: "
            + "; ".join(problems)
            + ". Refusing to residualize against the wrong baseline."
        )

    predictions_path = runs_dir / f"{BASELINE_MODEL_ID}_predictions.parquet"
    if not predictions_path.exists():
        raise BaselineRecordInvalid(
            f"the T2 baseline predictions {predictions_path} are missing; refit "
            "T0_R0 before fitting T2."
        )
    tbl = pq.read_table(predictions_path)
    ids: list[str] = tbl.column(OBS_ID_COL).to_pylist()
    vals: list[float] = tbl.column("prediction").to_pylist()
    by_obs = {obs_id: float(value) for obs_id, value in zip(ids, vals, strict=True)}
    return Baseline(
        by_obs=by_obs,
        predictions_path=predictions_path,
        model_path=runs_dir / f"{BASELINE_MODEL_ID}.xgb",
        run_record=record,
    )


def bump_target(assembled: Assembled) -> FloatArray:
    """The T1 residual target, ``won - base_p``, per development row.

    This is genuinely a residual, not the raw outcome relabelled: it takes both
    signs (a win above the proxy is positive, a loss below it negative) and is not
    bounded to [0, 1]. It is fitted with the regression objective and is never
    clipped -- clipping the target would discard exactly the observations the
    formulation exists to model.
    """
    return assembled.outcome - assembled.base_p


def _target_and_objective(
    target: str, assembled: Assembled, baseline: FloatArray | None = None
) -> tuple[FloatArray, str]:
    """The values a target asks the estimator to predict, and the objective for it.

    T0 predicts the raw outcome under the binary objective. T1 predicts
    ``won - base_p`` under the regression objective. T2 predicts
    ``won - m_hat_-i`` under the regression objective, where ``baseline`` is the
    cross-fitted ``m_hat_-i`` aligned to ``assembled``'s rows -- it is required for
    T2 and ignored otherwise.
    """
    if target == TARGET_T0:
        return assembled.outcome, estimator.BINARY
    if target == TARGET_T1:
        return bump_target(assembled), estimator.REGRESSION
    if target == TARGET_T2:
        if baseline is None:
            raise TargetUnknown(
                "T2 requires a cross-fitted baseline vector (m_hat_-i); none was "
                "supplied. Load it with load_baseline and pass baseline=."
            )
        return assembled.outcome - baseline, estimator.REGRESSION
    raise TargetUnknown(
        f"target {target!r} is not supported by this module; choose one of {TARGETS}."
    )


# --------------------------------------------------------------------------
# The fit -- always through the card-009 estimator.
# --------------------------------------------------------------------------


def fit_representation(
    assembled: Assembled,
    sources: Sources = DEFAULT_SOURCES,
    runs_dir: Path = RUNS_DIR,
    *,
    target: str = TARGET_T0,
    baseline: FloatArray | None = None,
) -> estimator.RunResult:
    """Fit one (target, representation) through :func:`estimator.fit_and_predict`.

    This module never constructs a learner, grid or folds; it hands the estimator
    an opaque matrix, the target's values and objective, the draft groups, the
    obs ids, and the run-record labels. For T0 the values are the raw outcome and
    the objective is binary; for T1 the values are the residual bump against the
    fixed proxy and the objective is regression; for T2 the values are the residual
    bump against the cross-fitted ``baseline`` (``m_hat_-i``) and the objective is
    regression. The estimator verifies the split hash, aligns the frozen folds,
    emits out-of-fold development predictions and writes the run record.
    """
    values, objective = _target_and_objective(target, assembled, baseline)
    return estimator.fit_and_predict(
        assembled.features,
        values,
        groups=assembled.groups,
        obs_ids=assembled.obs_ids,
        objective=objective,
        model_id=MODEL_IDS[target][assembled.representation],
        target=target,
        representation=assembled.representation,
        split_parquet=sources.split_parquet,
        split_manifest=sources.split_manifest,
        runs_dir=runs_dir,
    )


# --------------------------------------------------------------------------
# The timing probe -- one grid point, one fold; project the full search.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    """A single-fit timing measurement and the projected full-search total.

    ``probe_seconds`` is the wall time of one grid point on one fold at the
    capped iteration count (no early stopping, so the probe is a rough,
    conservative guide). ``n_fits`` is the number of single-booster fits the
    full search performs -- the grid crossed with the folds for cross-validation,
    the out-of-fold predictions, and the final refit -- and
    ``projected_seconds`` is ``probe_seconds * n_fits``.
    """

    probe_seconds: float
    n_fits: int
    projected_seconds: float


def timing_probe(
    assembled: Assembled,
    split_parquet: Path = SPLIT_PARQUET,
    *,
    target: str = TARGET_T0,
    baseline: FloatArray | None = None,
) -> Probe:
    """Fit one estimator grid point on one frozen fold; project the full search.

    Uses the estimator's own grid point, base parameters, the target's objective
    and the fold vector it would use, so the measurement reflects the real path
    rather than a hand-rolled learner. It fits a throwaway booster (not recorded)
    purely to time it. The projection assumes the search cost scales with the
    number of single-booster fits: ``len(grid) * k`` cross-validation fits, ``k``
    out-of-fold fits, and one final refit. ``baseline`` is required for T2 (it sets
    the residual the probe fits) and ignored otherwise.
    """
    values, objective = _target_and_objective(target, assembled, baseline)
    fold_vector = estimator._aligned_folds(assembled.obs_ids, assembled.groups, split_parquet)
    fold_pairs = estimator._fold_index_pairs(fold_vector)
    train_idx, _test_idx = fold_pairs[0]
    xgb = estimator._import_xgboost()
    params = {
        **estimator._base_params(objective, estimator.DEFAULT_SEED),
        **estimator.HYPERPARAMETER_GRID[0],
    }
    dtrain = xgb.DMatrix(assembled.features[train_idx], label=values[train_idx])
    start = time.perf_counter()
    xgb.train(params, dtrain, num_boost_round=estimator.MAX_BOOST_ROUND)
    probe_seconds = time.perf_counter() - start

    n_grid = len(estimator.HYPERPARAMETER_GRID)
    k_folds = len(fold_pairs)
    n_fits = n_grid * k_folds + k_folds + 1
    return Probe(
        probe_seconds=probe_seconds,
        n_fits=n_fits,
        projected_seconds=probe_seconds * n_fits,
    )


# --------------------------------------------------------------------------
# The card-010 panel, applied to development out-of-fold predictions.
# --------------------------------------------------------------------------


def development_metrics(outcome: FloatArray, predictions: FloatArray) -> dict[str, float]:
    """The card-010 Bernoulli panel plus the calibration line, for one model.

    Applied to out-of-fold *development* predictions (for T1, to the reconstructed
    and clipped probability against the raw ``won`` outcome). Diagnostic only:
    these rows are the same ones whose folds selected the hyperparameters, so the
    numbers are contaminated and no comparison is concluded from them.
    """
    metrics = dict(
        evaluation.evaluate_metrics(
            outcome, predictions, outcome_type=evaluation.OUTCOME_BERNOULLI
        )
    )
    line = evaluation.calibration_intercept_slope(outcome, predictions)
    metrics["cal_intercept"] = line.intercept
    metrics["cal_slope"] = line.slope
    return metrics


def bump_metrics(bump: FloatArray, predictions: FloatArray) -> dict[str, float]:
    """The card-010 continuous panel, for the T1 bump fit's out-of-fold output.

    The continuous view scores the residual prediction directly (RMSE, MAE and the
    section-9 weighted R-squared). It is diagnostic for the fit and is **not**
    comparable with any T0 metric: T0 fits a probability and T1 fits a residual,
    and only the reconstructed probability is common ground between them.
    """
    return dict(
        evaluation.evaluate_metrics(
            bump, predictions, outcome_type=evaluation.OUTCOME_CONTINUOUS
        )
    )


# --------------------------------------------------------------------------
# Reconstruction -- base + B_hat, clipped, with the escapes counted. The base is
# the fixed proxy for T1 and the cross-fitted m_hat_-i for T2.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconstructionStats:
    """How the reconstructed probability behaved before clipping.

    ``n_clipped_low``/``n_clipped_high`` count the rows whose raw reconstruction
    fell below the clip bound or above its complement -- the rows the additive
    decomposition ``base + B_hat`` pushed outside [0, 1]. ``raw_min``/``raw_max``
    bracket the raw reconstruction so the size of the escape is visible even when
    the count is zero.
    """

    n_rows: int
    n_clipped_low: int
    n_clipped_high: int
    clip_low: float
    clip_high: float
    raw_min: float
    raw_max: float

    @property
    def n_clipped(self) -> int:
        return self.n_clipped_low + self.n_clipped_high

    @property
    def clipped_fraction(self) -> float:
        return self.n_clipped / self.n_rows if self.n_rows else 0.0


def _write_reconstruction(
    path: Path,
    obs_ids: Sequence[str],
    bump: FloatArray,
    base: FloatArray,
    raw: FloatArray,
    clipped: FloatArray,
    *,
    base_col: str = BASE_P_COL,
) -> None:
    """Write a reconstruction artifact: the bump and the reconstructed prob.

    Keyed by ``obs_id``, one row per development observation, carrying the raw bump
    prediction, the ``base`` it was added to (``base_p`` for T1, the cross-fitted
    ``m_hat_-i`` for T2 -- named by ``base_col`` so the artifact never mislabels
    it), and the reconstructed probability before and after the clip. Gitignored
    under ``data/runs`` and regenerable from the frozen split and the run's
    booster.
    """
    table = pa.table(
        {
            OBS_ID_COL: pa.array(list(obs_ids), type=pa.string()),
            BUMP_COL: pa.array(bump.tolist(), type=pa.float64()),
            base_col: pa.array(base.tolist(), type=pa.float64()),
            RECON_RAW_COL: pa.array(raw.tolist(), type=pa.float64()),
            RECON_PROB_COL: pa.array(clipped.tolist(), type=pa.float64()),
        }
    )
    pq.write_table(table, path, compression="snappy")


# --------------------------------------------------------------------------
# T0 build -- R0 first and complete, then probe, then R1 if in budget.
# --------------------------------------------------------------------------


@dataclass
class BuildResult:
    """Everything the T0 report needs from one build."""

    r0_elapsed_seconds: float
    r0_metrics: dict[str, float]
    r0_record: dict[str, object]
    probe: Probe
    budget_seconds: float
    r1_attempted: bool
    r1_elapsed_seconds: float | None
    r1_metrics: dict[str, float] | None
    r1_record: dict[str, object] | None
    r1_skip_reason: str | None


def build(
    sources: Sources = DEFAULT_SOURCES,
    runs_dir: Path = RUNS_DIR,
    budget_seconds: float = R1_FIT_BUDGET_SECONDS,
    report_path: Path = REPORT_MD,
    write_report_file: bool = True,
) -> BuildResult:
    """Fit T0 R0, probe R1, fit R1 if the projection is within budget, write report.

    R0 is fitted and its run record written before R1 assembly or fitting begins.
    The R1 grid search runs only if the timing probe's projection is within
    ``budget_seconds``; otherwise R1 is reported as not attempted with the
    projection and reason recorded.
    """
    # R0 first, completely. One feature, seconds; proves the real path cheaply.
    a0 = assemble(R0, sources)
    start = time.perf_counter()
    r0 = fit_representation(a0, sources, runs_dir, target=TARGET_T0)
    r0_elapsed = time.perf_counter() - start
    r0_metrics = development_metrics(a0.outcome, r0.predictions)

    # R1 assembly and the timing probe -- measure before committing to the search.
    a1 = assemble(R1, sources)
    probe = timing_probe(a1, sources.split_parquet, target=TARGET_T0)

    r1_attempted = probe.projected_seconds <= budget_seconds
    r1_elapsed: float | None = None
    r1_metrics: dict[str, float] | None = None
    r1_record: dict[str, object] | None = None
    r1_skip_reason: str | None = None
    if r1_attempted:
        start = time.perf_counter()
        r1 = fit_representation(a1, sources, runs_dir, target=TARGET_T0)
        r1_elapsed = time.perf_counter() - start
        r1_metrics = development_metrics(a1.outcome, r1.predictions)
        r1_record = r1.run_record
    else:
        r1_skip_reason = _skip_reason(probe, budget_seconds)

    result = BuildResult(
        r0_elapsed_seconds=r0_elapsed,
        r0_metrics=r0_metrics,
        r0_record=r0.run_record,
        probe=probe,
        budget_seconds=budget_seconds,
        r1_attempted=r1_attempted,
        r1_elapsed_seconds=r1_elapsed,
        r1_metrics=r1_metrics,
        r1_record=r1_record,
        r1_skip_reason=r1_skip_reason,
    )
    if write_report_file:
        write_report(result, report_path)
    return result


def _skip_reason(probe: Probe, budget_seconds: float) -> str:
    return (
        f"the timing probe projects the full R1 grid search at "
        f"{probe.projected_seconds:.0f}s ({probe.projected_seconds / 60:.1f} "
        f"min), which exceeds the executor budget of {budget_seconds:.0f}s "
        f"({budget_seconds / 60:.1f} min). The build stops after R0 rather "
        "than starting a search it cannot finish."
    )


# --------------------------------------------------------------------------
# T1 build -- same order, plus reconstruction, clipping counts, dual metrics.
# --------------------------------------------------------------------------


@dataclass
class T1ModelResult:
    """One T1 model's fit: the record, both metric views, and the clip stats."""

    representation: str
    elapsed_seconds: float
    record: dict[str, object]
    continuous_metrics: dict[str, float]
    reconstructed_metrics: dict[str, float]
    recon_stats: ReconstructionStats


@dataclass
class T1BuildResult:
    """Everything the T1 report needs from one build."""

    r0: T1ModelResult
    probe: Probe
    budget_seconds: float
    r1_attempted: bool
    r1: T1ModelResult | None
    r1_skip_reason: str | None


def _fit_t1_model(assembled: Assembled, sources: Sources, runs_dir: Path) -> T1ModelResult:
    """Fit one T1 model, reconstruct its probability, and score it both ways.

    The estimator fits the residual bump with the regression objective and emits
    the out-of-fold ``B_hat``. The continuous view scores that bump directly. The
    probability is reconstructed as ``base_p + B_hat``, clipped into the unit
    interval with the panel's declared clip bound (with the escapes counted at
    each end), scored against the raw ``won`` outcome under the Bernoulli panel,
    and written -- alongside the raw bump -- to the reconstruction artifact.
    """
    start = time.perf_counter()
    run = fit_representation(assembled, sources, runs_dir, target=TARGET_T1)
    elapsed = time.perf_counter() - start

    bump = bump_target(assembled)
    continuous = bump_metrics(bump, run.predictions)

    clip_low = evaluation.PROBABILITY_CLIP
    clip_high = 1.0 - clip_low
    raw = assembled.base_p + run.predictions
    clipped = np.clip(raw, clip_low, clip_high)
    n_low = int(np.count_nonzero(raw < clip_low))
    n_high = int(np.count_nonzero(raw > clip_high))
    reconstructed = development_metrics(assembled.outcome, clipped)

    model_id = MODEL_IDS[TARGET_T1][assembled.representation]
    _write_reconstruction(
        runs_dir / f"{model_id}_reconstruction.parquet",
        run.obs_ids,
        run.predictions,
        assembled.base_p,
        raw,
        clipped,
    )
    stats = ReconstructionStats(
        n_rows=len(run.obs_ids),
        n_clipped_low=n_low,
        n_clipped_high=n_high,
        clip_low=clip_low,
        clip_high=clip_high,
        raw_min=float(np.min(raw)),
        raw_max=float(np.max(raw)),
    )
    return T1ModelResult(
        representation=assembled.representation,
        elapsed_seconds=elapsed,
        record=run.run_record,
        continuous_metrics=continuous,
        reconstructed_metrics=reconstructed,
        recon_stats=stats,
    )


def build_t1(
    sources: Sources = DEFAULT_SOURCES,
    runs_dir: Path = RUNS_DIR,
    budget_seconds: float = R1_FIT_BUDGET_SECONDS,
    report_path: Path = REPORT_T1_MD,
    write_report_file: bool = True,
) -> T1BuildResult:
    """Fit T1 R0, probe R1, fit R1 if the projection is within budget, write report.

    Same de-risking order as :func:`build`: R0 is fitted, reconstructed and its
    run record written before R1 assembly or fitting begins. The R1 grid search
    runs only if the timing probe's projection is within ``budget_seconds``;
    otherwise R1 is reported as not attempted with the projection and reason
    recorded. No comparison between R0 and R1, and none between T0 and T1, is
    drawn anywhere here.
    """
    a0 = assemble(R0, sources)
    r0 = _fit_t1_model(a0, sources, runs_dir)

    a1 = assemble(R1, sources)
    probe = timing_probe(a1, sources.split_parquet, target=TARGET_T1)

    r1_attempted = probe.projected_seconds <= budget_seconds
    r1: T1ModelResult | None = None
    r1_skip_reason: str | None = None
    if r1_attempted:
        r1 = _fit_t1_model(a1, sources, runs_dir)
    else:
        r1_skip_reason = _skip_reason(probe, budget_seconds)

    result = T1BuildResult(
        r0=r0,
        probe=probe,
        budget_seconds=budget_seconds,
        r1_attempted=r1_attempted,
        r1=r1,
        r1_skip_reason=r1_skip_reason,
    )
    if write_report_file:
        write_t1_report(result, report_path)
    return result


# --------------------------------------------------------------------------
# T2 build -- same order as T1, but the base is the cross-fitted m_hat_-i.
# --------------------------------------------------------------------------


@dataclass
class T2ModelResult:
    """One T2 model's fit: the record, both metric views, clip and bump stats.

    ``bump_mean``/``bump_std``/``bump_min``/``bump_max`` summarize the out-of-fold
    ``B_hat`` predictions. For ``T2_R0`` they are the cross-fitting diagnostic:
    ``E[B|S]`` is approximately zero by construction, so they should sit near zero,
    and a large systematic departure indicates leakage or baseline misfit rather
    than recovered signal.
    """

    representation: str
    elapsed_seconds: float
    record: dict[str, object]
    continuous_metrics: dict[str, float]
    reconstructed_metrics: dict[str, float]
    recon_stats: ReconstructionStats
    bump_mean: float
    bump_std: float
    bump_min: float
    bump_max: float


@dataclass
class T2BuildResult:
    """Everything the T2 report needs from one build, plus the baseline consumed."""

    r0: T2ModelResult
    probe: Probe
    budget_seconds: float
    r1_attempted: bool
    r1: T2ModelResult | None
    r1_skip_reason: str | None
    baseline: Baseline


def _fit_t2_model(
    assembled: Assembled, baseline: Baseline, sources: Sources, runs_dir: Path
) -> T2ModelResult:
    """Fit one T2 model against the cross-fitted baseline; score it both ways.

    The residual fitted is ``won - m_hat_-i``, with ``m_hat_-i`` the out-of-fold
    baseline aligned to this matrix's rows. The estimator fits it with the
    regression objective and emits the out-of-fold ``B_hat``. The continuous view
    scores that bump directly. The **development** probability is reconstructed as
    ``m_hat_-i + B_hat`` -- the out-of-fold baseline, not the full-data refit, so
    the development numbers stay comparable with T0's and T1's -- clipped into the
    unit interval (escapes counted at each end), scored against the raw ``won``
    outcome under the Bernoulli panel, and written alongside the raw bump to the
    reconstruction artifact.
    """
    baseline_vec = baseline.aligned(assembled.obs_ids)
    start = time.perf_counter()
    run = fit_representation(
        assembled, sources, runs_dir, target=TARGET_T2, baseline=baseline_vec
    )
    elapsed = time.perf_counter() - start

    bump = assembled.outcome - baseline_vec
    continuous = bump_metrics(bump, run.predictions)

    clip_low = evaluation.PROBABILITY_CLIP
    clip_high = 1.0 - clip_low
    raw = baseline_vec + run.predictions
    clipped = np.clip(raw, clip_low, clip_high)
    n_low = int(np.count_nonzero(raw < clip_low))
    n_high = int(np.count_nonzero(raw > clip_high))
    reconstructed = development_metrics(assembled.outcome, clipped)

    model_id = MODEL_IDS[TARGET_T2][assembled.representation]
    _write_reconstruction(
        runs_dir / f"{model_id}_reconstruction.parquet",
        run.obs_ids,
        run.predictions,
        baseline_vec,
        raw,
        clipped,
        base_col=BASELINE_COL,
    )
    stats = ReconstructionStats(
        n_rows=len(run.obs_ids),
        n_clipped_low=n_low,
        n_clipped_high=n_high,
        clip_low=clip_low,
        clip_high=clip_high,
        raw_min=float(np.min(raw)),
        raw_max=float(np.max(raw)),
    )
    preds = run.predictions
    return T2ModelResult(
        representation=assembled.representation,
        elapsed_seconds=elapsed,
        record=run.run_record,
        continuous_metrics=continuous,
        reconstructed_metrics=reconstructed,
        recon_stats=stats,
        bump_mean=float(np.mean(preds)),
        bump_std=float(np.std(preds)),
        bump_min=float(np.min(preds)),
        bump_max=float(np.max(preds)),
    )


def build_t2(
    sources: Sources = DEFAULT_SOURCES,
    runs_dir: Path = RUNS_DIR,
    budget_seconds: float = R1_FIT_BUDGET_SECONDS,
    report_path: Path = REPORT_T2_MD,
    write_report_file: bool = True,
) -> T2BuildResult:
    """Fit T2 R0, probe R1, fit R1 if within budget, write the T2 report.

    The learned baseline ``m_hat_-i`` is loaded and validated from ``T0_R0`` once,
    before any fitting -- a bad baseline record stops the run rather than
    residualizing against the wrong quantity. Same de-risking order as
    :func:`build_t1`: R0 is fitted, reconstructed and its run record written before
    R1 assembly or fitting begins. No comparison between R0 and R1, and none among
    T0, T1 and T2, is drawn anywhere here.
    """
    expected_split_sha = estimator.verify_split_hash(
        sources.split_parquet, sources.split_manifest
    )
    baseline = load_baseline(runs_dir, expected_split_sha, estimator.DEFAULT_SEED)

    a0 = assemble(R0, sources)
    r0 = _fit_t2_model(a0, baseline, sources, runs_dir)

    a1 = assemble(R1, sources)
    probe = timing_probe(
        a1, sources.split_parquet, target=TARGET_T2, baseline=baseline.aligned(a1.obs_ids)
    )

    r1_attempted = probe.projected_seconds <= budget_seconds
    r1: T2ModelResult | None = None
    r1_skip_reason: str | None = None
    if r1_attempted:
        r1 = _fit_t2_model(a1, baseline, sources, runs_dir)
    else:
        r1_skip_reason = _skip_reason(probe, budget_seconds)

    result = T2BuildResult(
        r0=r0,
        probe=probe,
        budget_seconds=budget_seconds,
        r1_attempted=r1_attempted,
        r1=r1,
        r1_skip_reason=r1_skip_reason,
        baseline=baseline,
    )
    if write_report_file:
        write_t2_report(result, report_path)
    return result


# --------------------------------------------------------------------------
# The T0 report.
# --------------------------------------------------------------------------

_METRIC_ORDER: tuple[str, ...] = (
    evaluation.LOG_LOSS,
    evaluation.BRIER,
    evaluation.BRIER_SKILL_SCORE,
    evaluation.RMSE,
    evaluation.MAE,
    evaluation.AUC,
    "cal_intercept",
    "cal_slope",
)

_CONTINUOUS_METRIC_ORDER: tuple[str, ...] = (
    evaluation.RMSE,
    evaluation.MAE,
    evaluation.R2,
)


def _metric_row(label: str, metrics: dict[str, float]) -> str:
    cells = [f"{metrics[m]:.6f}" for m in _METRIC_ORDER]
    return "| " + label + " | " + " | ".join(cells) + " |"


def _continuous_metric_row(label: str, metrics: dict[str, float]) -> str:
    cells = [f"{metrics[m]:.6f}" for m in _CONTINUOUS_METRIC_ORDER]
    return "| " + label + " | " + " | ".join(cells) + " |"


def _report_lines(result: BuildResult) -> list[str]:
    r0_rec = result.r0_record
    probe = result.probe
    header = "| Model | " + " | ".join(_METRIC_ORDER) + " |"
    divider = "| " + " | ".join(["---"] * (len(_METRIC_ORDER) + 1)) + " |"
    metric_rows = [header, divider, _metric_row("T0 / R0 (skill only)", result.r0_metrics)]
    if result.r1_metrics is not None:
        metric_rows.append(_metric_row("T0 / R1 (skill + identity)", result.r1_metrics))

    lines: list[str] = [
        "# T0 raw outcome -- development fits for R0 and R1 (card 011)",
        "",
        "The first row of the benchmark matrix, and the first real fits in the "
        "project. Target formulation **T0** (the raw game outcome `won` in "
        "{0, 1}) against the two representations phase 1 can supply: **R0** "
        "(skill only) and **R1** (skill + card identity). Both are fitted through "
        "`deckbench.estimator.fit_and_predict`; this card constructs no learner, "
        "grid, or folds of its own, and never opens the holdout.",
        "",
        "> **`base_p` is not skill.** R0's single feature is the reliability-shrunk "
        "historical win-rate proxy `base_p`, a nuisance representation reproduced "
        "from the inherited implementation (card 005). It is not a measurement of "
        "player skill and is not described as one here.",
        "",
        "## Regeneration history",
        "",
        "These fits have been regenerated twice since card 011 first produced "
        "them. Neither regeneration changed the learner, the grid, the folds, the "
        "seed, or the population, and neither opened the holdout. Both are "
        "recorded here because the numbers below moved each time, and a metric "
        "that moves without a stated reason is not attributable.",
        "",
        "1. **Card 014 -- skill-proxy fidelity correction.** The proxy's shrinkage "
        "target `mu` changed from a per-game mean to a per-draft mean, to match "
        "the R implementation being reproduced "
        "(`scripts/R/04_real_inference_refactored.R` line 324; `mu` 0.546211 -> "
        "0.533339). R0 is `[base_p]` and R1 contains it, so both consumed the "
        "changed column and were refitted. See `reports/mu_fidelity_correction.md`.",
        "",
        "2. **xgboost version change (two environments, not a bad record).** "
        "Cards 011 and 014 were executed by the compact orchestrator, which runs "
        "in its own virtualenv carrying xgboost **3.4.1**; an interactive session "
        "in this repo runs a different interpreter carrying **3.1.2**. Their T0 "
        "fits therefore ran under 3.4.1 and recorded it correctly. Refitting "
        "under 3.1.2 did **not** reproduce them: R0 selected a different grid "
        "point (`max_depth` 3 -> 4, `subsample` and `colsample_bytree` 1.0 -> "
        "0.8) and 367 -> 136 rounds, and the panel metrics moved in the fifth "
        "decimal. The artifacts described below are the 3.1.2 ones, matching the "
        "`xgboost==3.1.2` pin and the T1 and T2 rows, so every model card 017 "
        "compares was built by one version. An earlier revision of this section "
        "called the 3.4.1 record false provenance; that was a misreading -- "
        "`Booster.save_raw()` reports the *reading* library's version, not the "
        "writer's. See the LABNOTEBOOK entry [2026-09-10 18:40].",
        "",
        "## Fit order and elapsed time",
        "",
        "R0 was fitted **first and completely**, and its run record written to "
        "disk, **before any R1 assembly or fitting began**. R0 is one feature and "
        "finishes in seconds; fitting it first proves the real path -- split-hash "
        "verification, fold alignment, out-of-fold prediction, run record -- at a "
        "point where failure costs nothing. R0 is also M0, the benchmark's own "
        "skill-only baseline, so it is not a throwaway warm-up.",
        "",
        f"- **R0 fit** ({MODEL_IDS[TARGET_T0][R0]}): **{result.r0_elapsed_seconds:.1f} s**, "
        f"{r0_rec['n_dev_rows']} development rows x {r0_rec['n_features']} feature.",
    ]
    if result.r1_attempted and result.r1_record is not None:
        assert result.r1_elapsed_seconds is not None
        lines.append(
            f"- **R1 fit** ({MODEL_IDS[TARGET_T0][R1]}): "
            f"**{result.r1_elapsed_seconds:.1f} s**, "
            f"{result.r1_record['n_dev_rows']} development rows x "
            f"{result.r1_record['n_features']} features."
        )
    else:
        lines.append("- **R1 fit**: not attempted (see the timing probe below).")

    lines += [
        "",
        "## Timing probe and the budget decision",
        "",
        "Before the full R1 grid search, a probe fits a **single grid point on a "
        "single fold** at the capped iteration count (no early stopping). The full "
        "search performs `len(grid) * k` cross-validation fits, `k` out-of-fold "
        "fits, and one final refit.",
        "",
        f"- Probe (one grid point, one fold): **{probe.probe_seconds:.1f} s**",
        f"- Single-booster fits in the full search: **{probe.n_fits}** "
        f"({len(estimator.HYPERPARAMETER_GRID)} grid x 5 folds + 5 out-of-fold + "
        "1 refit)",
        f"- Projected full-search total: **{probe.projected_seconds:.1f} s** "
        f"({probe.projected_seconds / 60:.1f} min)",
        f"- Executor budget for R1: **{result.budget_seconds:.0f} s** "
        f"({result.budget_seconds / 60:.1f} min)",
        "",
    ]
    if result.r1_attempted:
        assert result.r1_elapsed_seconds is not None
        r1_elapsed = result.r1_elapsed_seconds
        direction = "under" if r1_elapsed <= probe.projected_seconds else "over"
        lines.append(
            "The projection was within budget, so the full R1 grid search was "
            f"run. The measured R1 fit came in at {r1_elapsed:.1f} s, {direction} "
            f"the {probe.projected_seconds:.1f} s projection. The probe is only a "
            "rough guide, not a precise predictor: it times one grid point on one "
            "fold at the capped iteration count with no early stopping, whereas "
            "the real search runs all grid points (each early-stopped on the "
            "native metric, some to more rounds or a deeper tree than the "
            "probe's) plus a final refit on all development rows. The two need "
            "not agree closely; both are far inside the budget, which is the only "
            "decision the probe exists to make."
        )
    else:
        assert result.r1_skip_reason is not None
        lines.append(result.r1_skip_reason)

    lines += [
        "",
        "## Development metrics (diagnostic only -- no comparison concluded)",
        "",
        "The card-010 panel applied to each model's **out-of-fold development** "
        "predictions, with `outcome_type = \"bernoulli\"`.",
        "",
        *metric_rows,
        "",
        "**These are development metrics, and they are diagnostic only.** They are "
        "computed on the same development rows whose folds selected each model's "
        "hyperparameters, so they are contaminated and cannot stand in for an "
        "honest generalization estimate. They are reported here only so that a "
        "first look confirms the pipeline produces sane probabilities in the unit "
        "interval rather than, say, 0.5 everywhere.",
        "",
        "**No comparison between R0 and R1 is concluded from these numbers, in "
        "either direction.** Whether card identity adds information beyond the "
        "skill proxy is not a question development metrics can answer; the "
        "benchmark's design puts that answer on the untouched external holdout, "
        "opened exactly once at card 014, scored through this same panel with the "
        "paired cluster bootstrap carrying the uncertainty on the difference. "
        "Section 13 also forbids reading any null incremental result as an absence "
        "of a deck effect. So: look, record, and draw nothing.",
        "",
        "## Provenance",
        "",
        f"- Split SHA256 (verified before each fit): `{r0_rec['split_sha256']}`",
        f"- Seed: **{r0_rec['seed']}**; xgboost **{r0_rec['xgboost_version']}** "
        f"(compiled library; Python package "
        f"**{r0_rec.get('xgboost_python_version', 'not recorded')}**), "
        "single-threaded (byte-identical determinism).",
        f"- R0 chosen hyperparameters: `{r0_rec['chosen_hyperparameters']}`, "
        f"{r0_rec['num_boost_round']} boosting rounds.",
    ]
    if result.r1_record is not None:
        lines.append(
            f"- R1 chosen hyperparameters: "
            f"`{result.r1_record['chosen_hyperparameters']}`, "
            f"{result.r1_record['num_boost_round']} boosting rounds."
        )
    lines += [
        "- Run records are tracked in git (`data/runs/*_run.json`); the prediction "
        "parquets and fitted boosters are gitignored and regenerable from the "
        "frozen split and the representation tables.",
        "- The holdout partition was not read; `cycle/holdout_ledger.jsonl` is "
        "byte-identical (0 bytes) before and after this card.",
        "",
    ]
    return lines


def write_report(result: BuildResult, report_path: Path = REPORT_MD) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(_report_lines(result)), encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# The T1 report.
# --------------------------------------------------------------------------


def _t1_fit_line(label: str, model_id: str, model: T1ModelResult) -> str:
    n_features = model.record["n_features"]
    unit = "feature" if n_features == 1 else "features"
    return (
        f"- **{label} fit** ({model_id}): **{model.elapsed_seconds:.1f} s**, "
        f"{model.record['n_dev_rows']} development rows x {n_features} {unit}."
    )


def _t1_clip_line(label: str, model: T1ModelResult) -> str:
    s = model.recon_stats
    return (
        f"- **{label}**: {s.n_clipped} of {s.n_rows} rows clipped "
        f"({s.clipped_fraction * 100:.4f}%) -- {s.n_clipped_low} below the lower "
        f"bound, {s.n_clipped_high} above the upper. Raw reconstruction ranged "
        f"[{s.raw_min:.6f}, {s.raw_max:.6f}] before clipping to "
        f"[{s.clip_low:.0e}, 1 - {s.clip_low:.0e}]."
    )


def _t1_report_lines(result: T1BuildResult) -> list[str]:
    r0 = result.r0
    r0_rec = r0.record
    probe = result.probe

    recon_header = "| Model | " + " | ".join(_METRIC_ORDER) + " |"
    recon_divider = "| " + " | ".join(["---"] * (len(_METRIC_ORDER) + 1)) + " |"
    recon_rows = [
        recon_header,
        recon_divider,
        _metric_row("T1 / R0 (skill only)", r0.reconstructed_metrics),
    ]
    cont_header = "| Model | " + " | ".join(_CONTINUOUS_METRIC_ORDER) + " |"
    cont_divider = "| " + " | ".join(["---"] * (len(_CONTINUOUS_METRIC_ORDER) + 1)) + " |"
    cont_rows = [
        cont_header,
        cont_divider,
        _continuous_metric_row("T1 / R0 (skill only)", r0.continuous_metrics),
    ]
    if result.r1 is not None:
        recon_rows.append(
            _metric_row("T1 / R1 (skill + identity)", result.r1.reconstructed_metrics)
        )
        cont_rows.append(
            _continuous_metric_row("T1 / R1 (skill + identity)", result.r1.continuous_metrics)
        )

    lines: list[str] = [
        "# T1 bump against the fixed skill proxy -- development fits for R0 and R1 "
        "(card 015)",
        "",
        "The benchmark's second target formulation. Where T0 predicts the game "
        "outcome directly, **T1 predicts the residual left after subtracting the "
        "fixed historical proxy**, then reconstructs a win probability from it:",
        "",
        "```",
        "B_i     = won_i - base_p_i      (the target actually fitted)",
        "p_hat_i = base_p_i + B_hat_i    (the probability reconstructed from it)",
        "```",
        "",
        "The residual is fitted with the estimator's **regression** objective; T0 "
        "used the binary one. Same two representations phase 1 can supply -- **R0** "
        "(skill only) and **R1** (skill + card identity) -- through the same "
        "`deckbench.estimator.fit_and_predict`, the same grid, the same frozen "
        "folds and the same seed. This card constructs no learner, grid, or folds "
        "of its own, and never opens the holdout.",
        "",
        "> **`base_p` is not skill.** R0's single feature is the reliability-shrunk "
        "historical win-rate proxy `base_p`, a nuisance representation reproduced "
        "from the inherited implementation (card 005). It is not a measurement of "
        "player skill and is not described as one here.",
        "",
        "## Why T1, and what it does not decide",
        "",
        "Section 2 of the benchmark observes that player skill may generate far "
        "more between-observation variation than deck quality, so direct "
        "prediction of the outcome can be dominated by skill even where deck "
        "quality matters. T1 subtracts the skill component up front so the model "
        "is asked only for what is left. Whether that actually helps recover deck "
        "signal is **H2** (section 14), which predicts an ordering across T0, T1 "
        "and T2. **H2 is a hypothesis, not an assumed result.** This card produces "
        "one row of the table that question needs; it does not test the ordering, "
        "and it draws no conclusion. The single holdout read at card 017 is where "
        "any comparison is made.",
        "",
        "## R0's role under a residual target",
        "",
        "It is fair to ask what a model can learn about `won - base_p` when its "
        "only feature is `base_p` itself -- the proxy has already been used to "
        "construct the target. Per benchmark section 4, this is a coherent "
        "question and not a degenerate one: `T1_R0` asks what **systematic "
        "structure the proxy leaves behind** -- miscalibration at the extremes, "
        "regression toward the mean, a reliability weighting that over- or "
        "under-shrinks particular buckets. A flat prediction near zero would "
        "itself be informative, saying the proxy has no exploitable residual "
        "structure. R0 is scored here for exactly that reason; nothing about it is "
        "read as skill, and its role in constructing the target is stated rather "
        "than hidden.",
        "",
        "## Fit order and elapsed time",
        "",
        "R0 was fitted **first and completely**, reconstructed, and its run record "
        "written to disk, **before any R1 assembly or fitting began** -- the same "
        "de-risking order T0 used, so the real path is proven where failure costs "
        "nothing.",
        "",
        _t1_fit_line("R0", MODEL_IDS[TARGET_T1][R0], r0),
    ]
    if result.r1 is not None:
        lines.append(_t1_fit_line("R1", MODEL_IDS[TARGET_T1][R1], result.r1))
    else:
        lines.append("- **R1 fit**: not attempted (see the timing probe below).")

    lines += [
        "",
        "## Timing probe and the budget decision",
        "",
        "Before the full R1 grid search, a probe fits a **single grid point on a "
        "single fold** at the capped iteration count (no early stopping), under "
        "the regression objective T1 uses.",
        "",
        f"- Probe (one grid point, one fold): **{probe.probe_seconds:.1f} s**",
        f"- Single-booster fits in the full search: **{probe.n_fits}** "
        f"({len(estimator.HYPERPARAMETER_GRID)} grid x 5 folds + 5 out-of-fold + "
        "1 refit)",
        f"- Projected full-search total: **{probe.projected_seconds:.1f} s** "
        f"({probe.projected_seconds / 60:.1f} min)",
        f"- Executor budget for R1: **{result.budget_seconds:.0f} s** "
        f"({result.budget_seconds / 60:.1f} min)",
        "",
    ]
    if result.r1_attempted:
        lines.append(
            "The projection was within budget, so the full R1 grid search was run. "
            "The probe is only a rough guide, not a precise predictor; the one "
            "decision it exists to make is whether the search fits inside the "
            "budget."
        )
    else:
        assert result.r1_skip_reason is not None
        lines.append(result.r1_skip_reason)

    lines += [
        "",
        "## Reconstruction and clipping (a measurement, not a nuisance)",
        "",
        "`p_hat = base_p + B_hat` has no arithmetic guarantee of landing inside "
        "[0, 1]. The reconstruction is clipped into the unit interval using the "
        "panel's declared clip bound (`PROBABILITY_CLIP` = "
        f"{evaluation.PROBABILITY_CLIP:.0e}) **only for scoring** -- the target "
        "itself is never clipped. How often the additive decomposition escapes "
        "the unit interval, and by how much, is direct evidence about whether the "
        "decomposition in section 2 holds on this data; a large clipped fraction "
        "would be a finding about the formulation, not a detail to suppress.",
        "",
        _t1_clip_line("R0", r0),
    ]
    if result.r1 is not None:
        lines.append(_t1_clip_line("R1", result.r1))

    lines += [
        "",
        "## Development metrics (diagnostic only -- no comparison concluded)",
        "",
        "The card-010 panel is applied **twice** per model. The **continuous** "
        "view scores the bump prediction directly against the fitted residual "
        "`won - base_p`; the **Bernoulli** view scores the reconstructed, clipped "
        "probability against the raw `won` outcome, through the same panel T0 "
        "used. Both are out-of-fold development predictions.",
        "",
        "### Reconstructed-probability view (`outcome_type = \"bernoulli\"`)",
        "",
        *recon_rows,
        "",
        "### Bump view (`outcome_type = \"continuous\"`)",
        "",
        *cont_rows,
        "",
        "**Only the reconstructed-probability metrics are comparable with T0.** T0 "
        "fits a probability and T1 fits a residual, so their native metrics answer "
        "different questions -- an R-squared on a bump and a log loss on a "
        "probability are not commensurable. The one thing both formulations "
        "produce for the same observation is a win probability, so the "
        "reconstructed probability is the only common ground, and it is what card "
        "017 will compare. The continuous view is diagnostic for the T1 fit alone.",
        "",
        "**These are development metrics, and they are diagnostic only.** They are "
        "computed on the same development rows whose folds selected each model's "
        "hyperparameters, so they are contaminated and cannot stand in for an "
        "honest generalization estimate. They confirm the pipeline produces sane "
        "numbers; they settle nothing.",
        "",
        "**No comparison between R0 and R1, and none between T0 and T1, is "
        "concluded from these numbers, in any direction.** Card 011's prohibition "
        "stands unchanged and for the same reason: whether a representation or a "
        "target formulation adds information is not a question development metrics "
        "can answer. The benchmark's design puts that answer on the untouched "
        "external holdout, opened exactly once at card 017, scored through this "
        "same panel with the paired cluster bootstrap carrying the uncertainty on "
        "the difference. Section 13 forbids reading any null incremental result as "
        "an absence of a deck effect. So: look, record, and draw nothing.",
        "",
        "## Provenance",
        "",
        f"- Split SHA256 (verified before each fit): `{r0_rec['split_sha256']}`",
        f"- Seed: **{r0_rec['seed']}**; xgboost **{r0_rec['xgboost_version']}** "
        f"(compiled library; Python package "
        f"**{r0_rec.get('xgboost_python_version', 'not recorded')}**), "
        "single-threaded (byte-identical determinism).",
        f"- Objective: **{r0_rec['objective']}** (regression), for the continuous "
        "residual target -- distinct from T0's binary objective.",
        f"- R0 chosen hyperparameters: `{r0_rec['chosen_hyperparameters']}`, "
        f"{r0_rec['num_boost_round']} boosting rounds.",
    ]
    if result.r1 is not None:
        lines.append(
            f"- R1 chosen hyperparameters: "
            f"`{result.r1.record['chosen_hyperparameters']}`, "
            f"{result.r1.record['num_boost_round']} boosting rounds."
        )
    lines += [
        "- Run records are tracked in git (`data/runs/*_run.json`); the prediction "
        "parquets, reconstruction parquets and fitted boosters are gitignored and "
        "regenerable from the frozen split and the representation tables.",
        "- The holdout partition was not read; `cycle/holdout_ledger.jsonl` is "
        "byte-identical (0 bytes) before and after this card.",
        "",
    ]
    return lines


def write_t1_report(result: T1BuildResult, report_path: Path = REPORT_T1_MD) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(_t1_report_lines(result)), encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# The T2 report.
# --------------------------------------------------------------------------


def _t2_fit_line(label: str, model_id: str, model: T2ModelResult) -> str:
    n_features = model.record["n_features"]
    unit = "feature" if n_features == 1 else "features"
    return (
        f"- **{label} fit** ({model_id}): **{model.elapsed_seconds:.1f} s**, "
        f"{model.record['n_dev_rows']} development rows x {n_features} {unit}."
    )


def _t2_clip_line(label: str, model: T2ModelResult) -> str:
    s = model.recon_stats
    return (
        f"- **{label}**: {s.n_clipped} of {s.n_rows} rows clipped "
        f"({s.clipped_fraction * 100:.4f}%) -- {s.n_clipped_low} below the lower "
        f"bound, {s.n_clipped_high} above the upper. Raw reconstruction ranged "
        f"[{s.raw_min:.6f}, {s.raw_max:.6f}] before clipping to "
        f"[{s.clip_low:.0e}, 1 - {s.clip_low:.0e}]."
    )


def _t2_bump_line(label: str, model: T2ModelResult) -> str:
    return (
        f"- **{label}** ({MODEL_IDS[TARGET_T2][model.representation]}): out-of-fold "
        f"`B_hat` mean **{model.bump_mean:+.6f}**, std **{model.bump_std:.6f}**, "
        f"range [{model.bump_min:+.6f}, {model.bump_max:+.6f}]."
    )


def _t2_report_lines(result: T2BuildResult) -> list[str]:
    r0 = result.r0
    r0_rec = r0.record
    probe = result.probe
    base_rec = result.baseline.run_record
    base_path = result.baseline.predictions_path
    try:
        base_path_str = base_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        base_path_str = base_path.as_posix()

    recon_header = "| Model | " + " | ".join(_METRIC_ORDER) + " |"
    recon_divider = "| " + " | ".join(["---"] * (len(_METRIC_ORDER) + 1)) + " |"
    recon_rows = [
        recon_header,
        recon_divider,
        _metric_row("T2 / R0 (skill only)", r0.reconstructed_metrics),
    ]
    cont_header = "| Model | " + " | ".join(_CONTINUOUS_METRIC_ORDER) + " |"
    cont_divider = "| " + " | ".join(["---"] * (len(_CONTINUOUS_METRIC_ORDER) + 1)) + " |"
    cont_rows = [
        cont_header,
        cont_divider,
        _continuous_metric_row("T2 / R0 (skill only)", r0.continuous_metrics),
    ]
    bump_lines = [_t2_bump_line("R0", r0)]
    if result.r1 is not None:
        recon_rows.append(
            _metric_row("T2 / R1 (skill + identity)", result.r1.reconstructed_metrics)
        )
        cont_rows.append(
            _continuous_metric_row("T2 / R1 (skill + identity)", result.r1.continuous_metrics)
        )
        bump_lines.append(_t2_bump_line("R1", result.r1))

    lines: list[str] = [
        "# T2 bump against a cross-fitted learned baseline -- development fits for "
        "R0 and R1 (card 016)",
        "",
        "The benchmark's third and last target formulation. T1 subtracted a "
        "**fixed** historical proxy; **T2 subtracts a learned one, cross-fitted so "
        "that no observation ever helps train the model that produces its own "
        "baseline**, then reconstructs a win probability from the residual:",
        "",
        "```",
        "m_hat_-i(S_i)              the cross-fitted baseline, E[Y|S] out of fold",
        "B_i     = won_i - m_hat_-i(S_i)   (the target actually fitted)",
        "p_hat_i = m_hat_-i(S_i) + B_hat_i (the probability reconstructed from it)",
        "```",
        "",
        "The residual is fitted with the estimator's **regression** objective. Same "
        "two representations phase 1 can supply -- **R0** (skill only) and **R1** "
        "(skill + card identity) -- through the same "
        "`deckbench.estimator.fit_and_predict`, the same grid, the same frozen "
        "folds and the same seed. This card constructs no learner, grid, or folds "
        "of its own, and never opens the holdout.",
        "",
        "> **Neither `base_p` nor `m_hat` is skill.** R0's single feature is the "
        "reliability-shrunk historical win-rate proxy `base_p`, a nuisance "
        "representation (card 005). `m_hat` is a *learned* estimate of expected win "
        "probability given that representation. Both are baselines; neither is a "
        "measurement of a player, and neither is described as skill here.",
        "",
        "## The baseline is reused from T0_R0, not refitted",
        "",
        "`m(S) = E[Y|S]` fitted on R0 with the binary objective and predicted out "
        "of fold is exactly what card 011 produced as `T0_R0`. This card **reuses "
        "that artifact and refits nothing**: refitting an identical model would "
        "burn time to reproduce the same numbers and would let T2's baseline drift "
        "from the `T0_R0` card 017 also scores, which is the one thing that would "
        "make the T0/T2 contrast unreadable. Before the predictions were used, the "
        "`T0_R0` run record was validated -- target, representation, objective, "
        "feature count, seed and split hash all had to match -- so the residual is "
        "never formed against the wrong baseline.",
        "",
        "Baseline artifact consumed, so the residual is reproducible from the "
        "record alone:",
        "",
        f"- Out-of-fold `m_hat_-i` predictions: `{base_path_str}`",
        f"- `T0_R0` chosen hyperparameters: `{base_rec['chosen_hyperparameters']}`, "
        f"{base_rec['num_boost_round']} boosting rounds, objective "
        f"**{base_rec['objective']}**, seed **{base_rec['seed']}**.",
        f"- Full-data `m_hat` booster (**not** used here; card 017's): "
        f"`{base_rec['model_path']}`.",
        "",
        "## Two baselines, two places -- and why development uses the out-of-fold one",
        "",
        "The **development** reconstruction here adds the **out-of-fold** "
        "`m_hat_-i`, the same vector that formed the training residual. Using the "
        "full-data refit `m_hat(S)` to reconstruct development rows would add a "
        "baseline fitted **on those same rows**, injecting a leak that flatters T2 "
        "against T0 and T1 for no reason other than leakage and makes T2's "
        "development numbers incomparable with theirs. The full-data `m_hat(S)` "
        "(`T0_R0.xgb`) is **card 017's**, where it reconstructs holdout rows it "
        "never trained on and is honest by construction. The two must not be "
        "swapped, and they are not.",
        "",
        "## R0 is a cross-fitting diagnostic, not a result",
        "",
        "Under T2 the R0 features are the same `S` the baseline was fitted on, so "
        "`E[B|S] = E[Y|S] - m_hat(S)` is approximately zero by construction and "
        "`T2_R0` should predict close to nothing. That makes it the most "
        "informative check in the card, not a model: if its predictions carry "
        "substantial systematic structure, the cross-fitting leaked or the baseline "
        "underfit. R0 contains no deck information at all, so a small non-zero value "
        "is **not** deck signal -- it is read only as a check on the machinery.",
        "",
        *bump_lines,
        "",
        "A mean near zero with a small spread is the expected, healthy reading: the "
        "out-of-fold baseline left no exploitable systematic structure in `S`. A "
        "large systematic departure from zero would indicate leakage or baseline "
        "misfit and would be a finding about the machinery, not recovered signal.",
        "",
        "## A bounded, recorded leak: hyperparameter selection is not fold-honest",
        "",
        "The out-of-fold **training** is honest: each fold's baseline comes from a "
        "booster trained on the other four folds. But the grid point `chosen` was "
        "selected by cross-validation over **all** development folds, so fold k's "
        "baseline is produced by a booster trained without fold k under "
        "hyperparameters informed by it. Section T2's critical requirement governs "
        "*training*, which is fold-honest; this residual leak is a choice among the "
        "grid's three points, is bounded, and is **recorded here rather than "
        "hidden**. Strict nested cross-validation would remove it at a cost this "
        "first benchmark does not need to pay; the decision to accept and document "
        "it is deliberate.",
        "",
        "## Fit order and elapsed time",
        "",
        "R0 was fitted **first and completely**, reconstructed, and its run record "
        "written to disk, **before any R1 assembly or fitting began** -- the same "
        "de-risking order T0 and T1 used, so the real path is proven where failure "
        "costs nothing.",
        "",
        _t2_fit_line("R0", MODEL_IDS[TARGET_T2][R0], r0),
    ]
    if result.r1 is not None:
        lines.append(_t2_fit_line("R1", MODEL_IDS[TARGET_T2][R1], result.r1))
    else:
        lines.append("- **R1 fit**: not attempted (see the timing probe below).")

    lines += [
        "",
        "## Timing probe and the budget decision",
        "",
        "Before the full R1 grid search, a probe fits a **single grid point on a "
        "single fold** at the capped iteration count (no early stopping), under the "
        "regression objective T2 uses.",
        "",
        f"- Probe (one grid point, one fold): **{probe.probe_seconds:.1f} s**",
        f"- Single-booster fits in the full search: **{probe.n_fits}** "
        f"({len(estimator.HYPERPARAMETER_GRID)} grid x 5 folds + 5 out-of-fold + "
        "1 refit)",
        f"- Projected full-search total: **{probe.projected_seconds:.1f} s** "
        f"({probe.projected_seconds / 60:.1f} min)",
        f"- Executor budget for R1: **{result.budget_seconds:.0f} s** "
        f"({result.budget_seconds / 60:.1f} min)",
        "",
    ]
    if result.r1_attempted:
        lines.append(
            "The projection was within budget, so the full R1 grid search was run. "
            "The probe is only a rough guide, not a precise predictor; the one "
            "decision it exists to make is whether the search fits inside the "
            "budget."
        )
    else:
        assert result.r1_skip_reason is not None
        lines.append(result.r1_skip_reason)

    lines += [
        "",
        "## Reconstruction and clipping (a measurement, not a nuisance)",
        "",
        "`p_hat = m_hat_-i + B_hat` has no arithmetic guarantee of landing inside "
        "[0, 1]. The reconstruction is clipped into the unit interval using the "
        "panel's declared clip bound (`PROBABILITY_CLIP` = "
        f"{evaluation.PROBABILITY_CLIP:.0e}) **only for scoring** -- the target "
        "itself is never clipped. How often the additive decomposition escapes the "
        "unit interval, and by how much, is direct evidence about whether the "
        "decomposition in section 2 holds on this data; a large clipped fraction "
        "would be a finding about the formulation, not a detail to suppress.",
        "",
        _t2_clip_line("R0", r0),
    ]
    if result.r1 is not None:
        lines.append(_t2_clip_line("R1", result.r1))

    lines += [
        "",
        "## Development metrics (diagnostic only -- no comparison concluded)",
        "",
        "The card-010 panel is applied **twice** per model. The **continuous** view "
        "scores the bump prediction directly against the fitted residual "
        "`won - m_hat_-i`; the **Bernoulli** view scores the reconstructed, clipped "
        "probability against the raw `won` outcome, through the same panel T0 and "
        "T1 used. Both are out-of-fold development predictions.",
        "",
        "### Reconstructed-probability view (`outcome_type = \"bernoulli\"`)",
        "",
        *recon_rows,
        "",
        "### Bump view (`outcome_type = \"continuous\"`)",
        "",
        *cont_rows,
        "",
        "**Only the reconstructed-probability metrics are comparable across T0, T1 "
        "and T2.** Each target fits a different quantity -- a probability (T0), a "
        "residual against a fixed proxy (T1), a residual against a learned baseline "
        "(T2) -- so their native metrics answer different questions and an "
        "R-squared on a bump is not commensurable with a log loss on a probability. "
        "The one thing all three formulations produce for the same observation is a "
        "win probability, so the reconstructed probability is the only common "
        "ground, and it is what card 017 will compare. The continuous view is "
        "diagnostic for the T2 fit alone.",
        "",
        "**These are development metrics, and they are diagnostic only.** They are "
        "computed on the same development rows whose folds selected each model's "
        "hyperparameters, so they are contaminated and cannot stand in for an "
        "honest generalization estimate. They confirm the pipeline produces sane "
        "numbers; they settle nothing.",
        "",
        "**No comparison between R0 and R1, and none among T0, T1 and T2, is "
        "concluded from these numbers, in any direction.** H2 (section 14) predicts "
        "an ordering T2 > T1 > T0 in recovered deck signal; **producing T2's row is "
        "not testing that ordering, and this card does not test it.** Whether a "
        "representation or a target formulation adds information is not a question "
        "development metrics can answer. The benchmark's design puts that answer on "
        "the untouched external holdout, opened exactly once at card 017, scored "
        "through this same panel with the paired cluster bootstrap carrying the "
        "uncertainty on the difference. Section 13 forbids reading any null "
        "incremental result as an absence of a deck effect. So: look, record, and "
        "draw nothing.",
        "",
        "## Provenance",
        "",
        f"- Split SHA256 (verified before each fit): `{r0_rec['split_sha256']}`",
        f"- Seed: **{r0_rec['seed']}**; xgboost **{r0_rec['xgboost_version']}** "
        f"(compiled library; Python package "
        f"**{r0_rec.get('xgboost_python_version', 'not recorded')}**), "
        "single-threaded (byte-identical determinism).",
        f"- Objective: **{r0_rec['objective']}** (regression), for the continuous "
        "residual target -- distinct from T0's binary objective.",
        f"- R0 chosen hyperparameters: `{r0_rec['chosen_hyperparameters']}`, "
        f"{r0_rec['num_boost_round']} boosting rounds.",
    ]
    if result.r1 is not None:
        lines.append(
            f"- R1 chosen hyperparameters: "
            f"`{result.r1.record['chosen_hyperparameters']}`, "
            f"{result.r1.record['num_boost_round']} boosting rounds."
        )
    lines += [
        "- Run records are tracked in git (`data/runs/*_run.json`); the prediction "
        "parquets, reconstruction parquets and fitted boosters are gitignored and "
        "regenerable from the frozen split, the representation tables and the "
        "reused `T0_R0` baseline.",
        "- The holdout partition was not read; `cycle/holdout_ledger.jsonl` is "
        "byte-identical (0 bytes) before and after this card.",
        "",
    ]
    return lines


def write_t2_report(result: T2BuildResult, report_path: Path = REPORT_T2_MD) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(_t2_report_lines(result)), encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# Verify -- check the artifacts every fit produced. No fitting, fast.
# --------------------------------------------------------------------------


def _holdout_obs_ids(split_parquet: Path) -> set[str]:
    tbl = pq.read_table(split_parquet, columns=[OBS_ID_COL, PARTITION_COL])
    ids = tbl.column(OBS_ID_COL).to_pylist()
    parts = tbl.column(PARTITION_COL).to_pylist()
    return {o for o, p in zip(ids, parts, strict=True) if p == HOLDOUT}


def _expected_feature_counts(sources: Sources) -> dict[str, int]:
    """Expected feature counts, derived from the identity table's own schema.

    R0 is ``base_p`` alone (1); R1 is ``base_p`` plus every card column. Reading
    the parquet schema is a metadata-only operation, so ``verify`` stays cheap and
    never reassembles a matrix. On the frozen dataset this yields
    ``{R0: 1, R1: 194}`` (matching :data:`N_FEATURES`); on a synthetic fixture it
    tracks that fixture's card count instead of a hardcoded 194.
    """
    schema = pq.read_schema(sources.identity_parquet)
    n_cards = len([name for name in schema.names if name != OBS_ID_COL])
    return {R0: 1, R1: 1 + n_cards}


def _verify_model(
    target: str,
    representation: str,
    runs_dir: Path,
    holdout_ids: set[str],
    expected_split_sha: str,
    expected_features: int,
    problems: list[str],
) -> bool:
    """Verify one model's run record and artifacts. Returns whether it exists.

    Checks the run record's labels (including the objective the target must have
    been fitted under), the feature count, the split hash, the seed and the chosen
    hyperparameters; then the predictions parquet (present, non-empty, disjoint
    from the holdout). For T1 and T2 it additionally checks the reconstruction
    artifact: present, disjoint from the holdout, and every reconstructed
    probability inside the panel's clip bound.
    """
    model_id = MODEL_IDS[target][representation]
    label = f"{target}/{representation}"
    record_path = runs_dir / f"{model_id}_run.json"
    if not record_path.exists():
        return False
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("target") != target:
        problems.append(f"{label}: target is {record.get('target')!r}, not {target!r}")
    if record.get("representation") != representation:
        problems.append(f"{label}: representation label is {record.get('representation')!r}")
    if record.get("objective") != TARGET_OBJECTIVE[target]:
        problems.append(
            f"{label}: objective is {record.get('objective')!r}, expected "
            f"{TARGET_OBJECTIVE[target]!r}"
        )
    if record.get("n_features") != expected_features:
        problems.append(
            f"{label}: n_features is {record.get('n_features')!r}, "
            f"expected {expected_features}"
        )
    if record.get("split_sha256") != expected_split_sha:
        problems.append(f"{label}: split_sha256 does not match the manifest")
    if not isinstance(record.get("seed"), int):
        problems.append(f"{label}: seed is not recorded as an integer")
    if not isinstance(record.get("chosen_hyperparameters"), dict):
        problems.append(f"{label}: chosen_hyperparameters missing")

    predictions_path = runs_dir / f"{model_id}_predictions.parquet"
    if not predictions_path.exists():
        problems.append(f"{label}: predictions parquet {predictions_path.name} missing")
        return True
    preds = pq.read_table(predictions_path)
    emitted = set(preds.column(OBS_ID_COL).to_pylist())
    if not emitted:
        problems.append(f"{label}: predictions parquet is empty")
    if not emitted.isdisjoint(holdout_ids):
        problems.append(f"{label}: emitted obs_ids intersect the holdout partition")

    if target in RECONSTRUCTION_TARGETS:
        _verify_reconstruction(label, model_id, runs_dir, holdout_ids, problems)
    return True


def _verify_reconstruction(
    label: str,
    model_id: str,
    runs_dir: Path,
    holdout_ids: set[str],
    problems: list[str],
) -> None:
    """Check a T1/T2 reconstruction artifact: present, dev-only, clipped in range."""
    recon_path = runs_dir / f"{model_id}_reconstruction.parquet"
    if not recon_path.exists():
        problems.append(f"{label}: reconstruction parquet {recon_path.name} missing")
        return
    recon = pq.read_table(recon_path)
    recon_ids = set(recon.column(OBS_ID_COL).to_pylist())
    if not recon_ids:
        problems.append(f"{label}: reconstruction parquet is empty")
    if not recon_ids.isdisjoint(holdout_ids):
        problems.append(f"{label}: reconstruction obs_ids intersect the holdout partition")
    if RECON_PROB_COL not in recon.column_names:
        problems.append(f"{label}: reconstruction parquet lacks a {RECON_PROB_COL!r} column")
        return
    prob = np.asarray(
        recon.column(RECON_PROB_COL).to_numpy(zero_copy_only=False), dtype=np.float64
    )
    clip_low = evaluation.PROBABILITY_CLIP
    if prob.size and (float(np.min(prob)) < clip_low or float(np.max(prob)) > 1.0 - clip_low):
        problems.append(
            f"{label}: reconstructed probability escapes the clip bound "
            f"[{clip_low:.0e}, 1 - {clip_low:.0e}]"
        )


def verify(
    sources: Sources = DEFAULT_SOURCES,
    runs_dir: Path = RUNS_DIR,
    report_path: Path = REPORT_MD,
    ledger_path: Path = LEDGER_PATH,
    report_t1_path: Path = REPORT_T1_MD,
    report_t2_path: Path = REPORT_T2_MD,
) -> int:
    """Check the artifacts every fit produced, without fitting anything.

    Fast enough for the 300-second check budget: it reads the run records, the
    prediction parquets and (for T1/T2) the reconstruction parquets, and asserts
    feature counts, the split hash, the recorded objective, the disjoint holdout,
    the reports, and the untouched ledger. It walks **all three** target
    formulations -- T0, T1 and T2 -- so it inspects everything each card produced,
    not only T0. Each target's R0 is mandatory; R1 is checked only if its run
    record exists (a build may legitimately have stopped after R0).
    """
    problems: list[str] = []
    expected_split_sha = estimator.verify_split_hash(sources.split_parquet, sources.split_manifest)
    holdout_ids = _holdout_obs_ids(sources.split_parquet)
    expected = _expected_feature_counts(sources)

    r1_present: dict[str, bool] = {}
    for target in TARGETS:
        if not _verify_model(
            target, R0, runs_dir, holdout_ids, expected_split_sha, expected[R0], problems
        ):
            problems.append(
                f"{target}/R0 run record "
                f"{runs_dir / (MODEL_IDS[target][R0] + '_run.json')} is missing; "
                f"{target}/R0 must always be fitted."
            )
        r1_present[target] = _verify_model(
            target, R1, runs_dir, holdout_ids, expected_split_sha, expected[R1], problems
        )

    if not report_path.exists():
        problems.append(f"T0 report {report_path} is missing")
    if not report_t1_path.exists():
        problems.append(f"T1 report {report_t1_path} is missing")
    if not report_t2_path.exists():
        problems.append(f"T2 report {report_t2_path} is missing")

    if ledger_path.exists() and ledger_path.stat().st_size != 0:
        problems.append(
            f"holdout ledger {ledger_path} is not empty; this card must not open "
            "the holdout."
        )

    if problems:
        print("targets --verify FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    states = ", ".join(
        f"{target} R1 {'fitted' if r1_present[target] else 'not attempted'}"
        for target in TARGETS
    )
    print(
        "targets --verify OK: T0, T1 and T2 R0 run records and predictions "
        "present, feature counts and recorded objectives correct, split hash "
        f"verified, holdout disjoint, T1/T2 reconstruction in range ({states}); "
        "reports present; holdout ledger untouched."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--fit",
        action="store_true",
        help="fit T0 R0, run the R1 timing probe, fit R1 if within budget, write the T0 report.",
    )
    group.add_argument(
        "--fit-t1",
        dest="fit_t1",
        action="store_true",
        help="fit T1 R0, probe, fit R1 if within budget, reconstruct, write the T1 report.",
    )
    group.add_argument(
        "--fit-t2",
        dest="fit_t2",
        action="store_true",
        help=(
            "fit T2 R0, probe, fit R1 if within budget, reconstruct against the "
            "cross-fitted T0_R0 baseline, write the T2 report."
        ),
    )
    group.add_argument(
        "--verify",
        action="store_true",
        help="check the artifacts every fit produced (no fitting).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.fit:
        result = build()
        r1 = (
            f"R1 fitted in {result.r1_elapsed_seconds:.1f}s"
            if result.r1_attempted
            else "R1 not attempted (over budget)"
        )
        print(
            f"targets --fit OK: T0 R0 fitted in {result.r0_elapsed_seconds:.1f}s; "
            f"probe {result.probe.probe_seconds:.1f}s -> projected "
            f"{result.probe.projected_seconds:.1f}s; {r1}. "
            f"Report at {REPORT_MD.relative_to(REPO_ROOT).as_posix()}."
        )
        return 0
    if args.fit_t1:
        result_t1 = build_t1()
        r1t = (
            f"R1 fitted in {result_t1.r1.elapsed_seconds:.1f}s"
            if result_t1.r1_attempted and result_t1.r1 is not None
            else "R1 not attempted (over budget)"
        )
        print(
            f"targets --fit-t1 OK: T1 R0 fitted in "
            f"{result_t1.r0.elapsed_seconds:.1f}s "
            f"(clipped {result_t1.r0.recon_stats.n_clipped}/"
            f"{result_t1.r0.recon_stats.n_rows}); probe "
            f"{result_t1.probe.probe_seconds:.1f}s -> projected "
            f"{result_t1.probe.projected_seconds:.1f}s; {r1t}. "
            f"Report at {REPORT_T1_MD.relative_to(REPO_ROOT).as_posix()}."
        )
        return 0
    if args.fit_t2:
        result_t2 = build_t2()
        r1t2 = (
            f"R1 fitted in {result_t2.r1.elapsed_seconds:.1f}s"
            if result_t2.r1_attempted and result_t2.r1 is not None
            else "R1 not attempted (over budget)"
        )
        print(
            f"targets --fit-t2 OK: T2 R0 fitted in "
            f"{result_t2.r0.elapsed_seconds:.1f}s "
            f"(B_hat mean {result_t2.r0.bump_mean:+.6f}, std "
            f"{result_t2.r0.bump_std:.6f}; clipped "
            f"{result_t2.r0.recon_stats.n_clipped}/"
            f"{result_t2.r0.recon_stats.n_rows}); baseline "
            f"{result_t2.baseline.predictions_path.name}; probe "
            f"{result_t2.probe.probe_seconds:.1f}s -> projected "
            f"{result_t2.probe.projected_seconds:.1f}s; {r1t2}. "
            f"Report at {REPORT_T2_MD.relative_to(REPO_ROOT).as_posix()}."
        )
        return 0
    if args.verify:
        return verify()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
