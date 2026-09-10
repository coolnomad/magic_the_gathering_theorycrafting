"""The one estimator every benchmark model is fit through (card 009).

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md``. Section 8 holds the
learner family constant so that a difference between two models is attributable
to the *representation* and not to the algorithm, and section 10 states the
requirement that makes that hold: **the estimator must not know how the
representation was generated.** This module is that single code path. Every cell
of the target x representation matrix -- T0/T1/T2 crossed with R0..R5 -- goes
through :func:`fit_and_predict`, which sees an opaque feature matrix and never
learns where its columns came from.

What this card does, and deliberately does not do:

* It fits models on **development data only**. It reads the development rows
  through :func:`deckbench.holdout.load_dev`, the unsealed path that needs no card
  id and touches no ledger, so ordinary fitting leaves the holdout ledger's
  signal untouched. It never routes through the sealed reader and never reads,
  samples from, or fits on the holdout partition by any route. The single holdout
  read is card 014.
* It computes **no** evaluation quantity. No R-squared, log loss, Brier, AUC, or
  calibration number is produced here, even as a convenience. Tuning uses the
  learner's own native training objective (logistic / squared error), which is
  intrinsic to the learner and needs no external panel; the evaluation panel is
  card 010 and operates on emitted predictions. The two cards are decoupled in
  both directions: this one needs no panel, and the panel needs no estimator.

The design that makes section 8's comparison meaningful:

* **Arrays in, not table paths.** A caller assembles the feature matrix for its
  representation and passes it as an opaque 2-D array. This module never inspects
  a column name, never imports the representation builders, and never reads a
  feature/representation parquet itself. The provenance-blindness test passes a
  real matrix and a random matrix of the same shape through the identical entry
  point and requires both to complete -- the cheap check that the path does not
  secretly special-case a column.
* **One grid, declared once as data.** :data:`HYPERPARAMETER_GRID` is the single
  grid searched for every model. It is a module constant, not rebuilt per call.
* **Folds come from the frozen split, never re-derived.** The inner
  cross-validation uses exactly the folds recorded in ``model_split.parquet``.
  The estimator never invents its own folds and never accepts a caller-supplied
  fold vector. Because those folds are assigned per draft upstream, no draft
  contributes rows to more than one inner fold -- a property inherited, not
  re-established here.
* **The split's identity is verified before any fit.** The run record's split
  SHA256 is read from ``split_manifest.json`` and the fit fails if it does not
  match the split parquet on disk, so a model can never be recorded against a
  split that moved under it.

Model identity, target formulation and representation *name* are carried on the
request purely as labels for the run record (section 15). They are written to the
record and are never read by the fitting code -- the core search-and-fit routine
receives only arrays, an objective, the frozen folds and a seed.

Run it with::

    python -m deckbench.estimator --selftest

which fits a small synthetic binary and regression model end to end in a
temporary directory, checks determinism, and confirms nothing was emitted for a
holdout row -- touching no tracked file.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib
import json
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from numpy.typing import NDArray

from deckbench.holdout import load_dev

if TYPE_CHECKING:
    from collections.abc import Sequence

# src/deckbench/estimator.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SPLIT_PARQUET = PROCESSED_DIR / "model_split.parquet"
SPLIT_MANIFEST = REPO_ROOT / "data" / "splits" / "split_manifest.json"
# Run records, emitted predictions and the fitted booster land here. The
# directory is gitignored: every artifact under it is regenerable from the frozen
# split and a representation matrix, so the blobs stay out of history while the
# run record makes each fit reproducible.
RUNS_DIR = REPO_ROOT / "data" / "runs"

# Partition label for development rows, matched to :mod:`deckbench.split`. The
# holdout partition is named nowhere in this module by design.
DEV = "dev"

# The two objectives, selected by the caller. A binary/logistic objective for raw
# game outcomes in {0, 1}; a squared-error regression objective for continuous
# bump/residual targets. The caller chooses; the estimator does not infer it from
# the data.
BINARY = "binary"
REGRESSION = "regression"
OBJECTIVES = (BINARY, REGRESSION)

# The learner's native training objective and the metric its own early stopping
# watches, per objective. This metric is intrinsic to the learner and is used
# only to tune -- it is never emitted as an output of this card.
_XGB_OBJECTIVE: dict[str, str] = {
    BINARY: "binary:logistic",
    REGRESSION: "reg:squarederror",
}
_XGB_EVAL_METRIC: dict[str, str] = {
    BINARY: "logloss",
    REGRESSION: "rmse",
}

# The single hyperparameter grid searched for every model fit through this path,
# declared once, as data. Section 8 fixes the learner family so a difference
# between two models is the representation, not the algorithm; that only holds if
# the grid is identical for every model, so it lives here and is never rebuilt
# per call. Kept deliberately small: the first benchmark asks whether a
# representation carries information, not whether an exhaustive search can wring
# it out.
HYPERPARAMETER_GRID: tuple[dict[str, float], ...] = (
    {"max_depth": 3, "eta": 0.10, "subsample": 1.0, "colsample_bytree": 1.0,
     "min_child_weight": 1.0},
    {"max_depth": 4, "eta": 0.10, "subsample": 0.8, "colsample_bytree": 0.8,
     "min_child_weight": 1.0},
    {"max_depth": 5, "eta": 0.05, "subsample": 0.8, "colsample_bytree": 0.8,
     "min_child_weight": 2.0},
)

# Boosting is capped here and early stopping on the native metric selects the
# actual iteration count, which is the number recorded in the run record.
MAX_BOOST_ROUND = 400
EARLY_STOPPING_ROUNDS = 25

# The default seed. Declared, recorded in every run record, and threaded into
# xgboost so that -- single-threaded -- two fits on the same inputs produce
# byte-identical predictions.
DEFAULT_SEED = 20260908

# Single-threaded on purpose: xgboost's multi-threaded histogram build is not
# bit-reproducible, and byte-identical predictions across two fits is an
# acceptance criterion.
_NTHREAD = 1


class MissingDependency(RuntimeError):
    """Raised when a required modeling dependency is not importable.

    xgboost is not imported at module import time, so this module stays
    importable in a graph-only checkout; the failure is deferred to the first
    fit and names the missing package.
    """


class ProvenanceUnavailable(RuntimeError):
    """Raised when the compiled xgboost library will not report its version.

    Recorded provenance that is silently wrong is worse than a fit that stops,
    so this fails closed rather than writing a placeholder. See
    :func:`_xgboost_library_version` for why the Python package's
    ``__version__`` is not an acceptable substitute.
    """


class SplitHashMismatch(RuntimeError):
    """Raised when the split parquet does not match the manifest's pinned hash.

    A model recorded against a split that moved under it is not attributable, so
    the fit fails closed before touching the data.
    """


class ObjectiveUnknown(ValueError):
    """Raised when the caller names an objective that is not supported."""


class HoldoutRowRejected(ValueError):
    """Raised when a caller passes an obs_id that is not a development row.

    The estimator fits and predicts on development rows only. An id that is not
    in the development partition -- a holdout id, or an unknown one -- stops the
    fit rather than being silently scored.
    """


class GroupMismatch(ValueError):
    """Raised when a caller's group id disagrees with the frozen split.

    The caller assembles the matrix and passes the draft id of each row; if that
    disagrees with the split's own draft id for the same observation, the matrix
    is misaligned and the fit stops rather than fitting a scrambled table.
    """


def _import_xgboost() -> Any:
    """Import xgboost lazily, or fail naming the missing dependency."""
    try:
        import xgboost as xgb
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise MissingDependency(
            "xgboost is required to fit a model but is not importable. It is the "
            "benchmark's fixed learner (section 8); install it with "
            "`pip install 'xgboost>=2'` (declared in pyproject's `modeling` extra)."
        ) from exc
    return xgb


def _xgboost_library_version(xgb: Any) -> str:
    """Return the version of the compiled ``libxgboost`` that will train.

    ``xgb.__version__`` is the **Python package's** self-reported string, which
    need not equal the version of the native library that actually builds the
    model. The library is what trains, so the library version is what
    ``xgboost_version`` means in a run record, and the wrapper version is
    recorded beside it as ``xgboost_python_version`` rather than discarded --
    the Python side builds the DMatrix and drives the boosting loop, so it can
    move results too, and a disagreement between the two fields is worth seeing.

    On this project the two have always agreed; recording both is cheap
    insurance, not a fix for an observed mismatch. What actually bit here was
    two *environments*: compact's executor runs in ``control_plane``'s venv
    (xgboost 3.4.1) while an interactive session runs the user-site interpreter
    (3.1.2), and fits made in one do not reproduce in the other. See the
    LABNOTEBOOK entry [2026-09-10 18:40].
    """
    # `xgboost.core._LIB` is private and not re-exported, so a direct import is
    # an attr-defined error under mypy --strict. Reach it dynamically instead.
    try:
        core = importlib.import_module("xgboost.core")
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ProvenanceUnavailable(
            "xgboost imported but its native library handle is unavailable, so "
            "the version that would train the model cannot be recorded."
        ) from exc
    lib = getattr(core, "_LIB", None)
    if lib is None:  # pragma: no cover - environment-dependent
        raise ProvenanceUnavailable(
            "xgboost.core exposes no native library handle, so the version that "
            "would train the model cannot be recorded."
        )

    major, minor, patch = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
    try:
        lib.XGBoostVersion(
            ctypes.byref(major), ctypes.byref(minor), ctypes.byref(patch)
        )
    except AttributeError as exc:  # pragma: no cover - environment-dependent
        raise ProvenanceUnavailable(
            "libxgboost does not export XGBoostVersion, so the training "
            "library's version cannot be recorded. Refusing to fit rather than "
            f"record the Python package's {xgb.__version__!r} as if it were the "
            "library's."
        ) from exc
    return f"{major.value}.{minor.value}.{patch.value}"


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_split_hash(
    split_parquet: Path = SPLIT_PARQUET, split_manifest: Path = SPLIT_MANIFEST
) -> str:
    """Return the split SHA256 from the manifest, having checked it on disk.

    Reads ``split_sha256`` from ``split_manifest.json`` and compares it to the
    SHA256 of the split parquet on disk. Fails closed on a missing manifest,
    missing parquet, or any mismatch, so a fit never records a split hash it did
    not verify against the bytes it will fit through.
    """
    if not split_manifest.exists():
        raise SplitHashMismatch(
            f"split manifest not found: {split_manifest}. Freeze the split with "
            "`python -m deckbench.split` first."
        )
    if not split_parquet.exists():
        raise SplitHashMismatch(
            f"split parquet not found: {split_parquet}. Freeze the split with "
            "`python -m deckbench.split` first."
        )
    manifest = json.loads(split_manifest.read_text(encoding="utf-8"))
    pinned = manifest.get("split_sha256")
    if not isinstance(pinned, str) or not pinned:
        raise SplitHashMismatch(
            f"split manifest {split_manifest} does not pin a split_sha256."
        )
    actual = _sha256(split_parquet)
    if actual != pinned:
        raise SplitHashMismatch(
            "split parquet SHA256 does not match the manifest: the split moved "
            f"after it was frozen (manifest {pinned}, disk {actual})."
        )
    return actual


def dev_fold_map(split_parquet: Path = SPLIT_PARQUET) -> dict[str, tuple[str, int]]:
    """Map each development ``obs_id`` to its ``(draft_id, fold)``.

    Read through :func:`deckbench.holdout.load_dev`, the unsealed development
    path, so no ledger is touched. The fold is taken verbatim from the frozen
    split; this function never computes a fold. Holdout rows are absent by
    construction -- ``load_dev`` returns the development partition only.
    """
    table = load_dev(split_parquet)
    obs_ids: list[str] = table.column("obs_id").to_pylist()
    draft_ids: list[str] = table.column("draft_id").to_pylist()
    folds: list[int] = table.column("fold").to_pylist()
    return {
        obs_id: (draft_id, int(fold))
        for obs_id, draft_id, fold in zip(obs_ids, draft_ids, folds, strict=True)
    }


def _aligned_folds(
    obs_ids: Sequence[str],
    groups: Sequence[str],
    split_parquet: Path,
) -> NDArray[np.int64]:
    """Return the frozen fold of every passed row, in row order.

    Every ``obs_id`` must be a development row (a holdout or unknown id stops the
    fit), and every caller-supplied group must equal the split's own draft id for
    that observation (a disagreement stops the fit). No draft may then straddle
    two folds, which is asserted here and inherited from the split rather than
    re-derived.
    """
    fold_map = dev_fold_map(split_parquet)
    folds: list[int] = []
    draft_to_fold: dict[str, int] = {}
    for obs_id, group in zip(obs_ids, groups, strict=True):
        if obs_id not in fold_map:
            raise HoldoutRowRejected(
                f"observation {obs_id!r} is not a development row; the estimator "
                "fits on development rows only and never on the holdout."
            )
        split_draft, fold = fold_map[obs_id]
        if group != split_draft:
            raise GroupMismatch(
                f"observation {obs_id!r} carries group {group!r} but the split "
                f"assigns it draft {split_draft!r}; the matrix is misaligned."
            )
        prior = draft_to_fold.setdefault(split_draft, fold)
        if prior != fold:
            raise GroupMismatch(
                f"draft {split_draft!r} maps to folds {prior} and {fold}; a draft "
                "must not span two inner folds."
            )
        folds.append(fold)
    return np.asarray(folds, dtype=np.int64)


def _fold_index_pairs(
    fold_vector: NDArray[np.int64],
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """Turn the per-row fold vector into (train_idx, test_idx) pairs.

    One pair per distinct fold present, holding that fold out for testing. These
    are the frozen folds; nothing here shuffles or re-partitions.
    """
    pairs: list[tuple[NDArray[np.int64], NDArray[np.int64]]] = []
    for fold in sorted({int(f) for f in fold_vector.tolist()}):
        test_idx = np.nonzero(fold_vector == fold)[0].astype(np.int64)
        train_idx = np.nonzero(fold_vector != fold)[0].astype(np.int64)
        pairs.append((train_idx, test_idx))
    return pairs


def _base_params(objective: str, seed: int) -> dict[str, object]:
    """The fixed non-tuned parameters: objective, native metric, seed, threads."""
    if objective not in OBJECTIVES:
        raise ObjectiveUnknown(
            f"objective {objective!r} is not supported; choose one of "
            f"{OBJECTIVES}."
        )
    return {
        "objective": _XGB_OBJECTIVE[objective],
        "eval_metric": _XGB_EVAL_METRIC[objective],
        "tree_method": "hist",
        "seed": seed,
        "nthread": _NTHREAD,
    }


@dataclass(frozen=True)
class _Chosen:
    """The grid point and iteration count selected by the inner CV."""

    params: dict[str, float]
    num_boost_round: int


def _select_hyperparameters(
    xgb: Any,
    features: NDArray[np.float64],
    outcome: NDArray[np.float64],
    weights: NDArray[np.float64] | None,
    fold_pairs: list[tuple[NDArray[np.int64], NDArray[np.int64]]],
    objective: str,
    seed: int,
) -> _Chosen:
    """Search :data:`HYPERPARAMETER_GRID` with the frozen folds; return the best.

    For each grid point, xgboost's own cross-validation runs over the frozen
    folds with early stopping on the native metric. The grid point with the best
    native cross-validated metric wins, and its early-stopped iteration count is
    carried forward. The metric drives selection only; it is never emitted.
    """
    dtrain = xgb.DMatrix(features, label=outcome, weight=weights)
    metric = _XGB_EVAL_METRIC[objective]
    best: _Chosen | None = None
    best_score: float | None = None
    for grid_point in HYPERPARAMETER_GRID:
        params = {**_base_params(objective, seed), **grid_point}
        cv = xgb.cv(
            params,
            dtrain,
            num_boost_round=MAX_BOOST_ROUND,
            folds=fold_pairs,
            early_stopping_rounds=EARLY_STOPPING_ROUNDS,
            seed=seed,
            as_pandas=False,
        )
        # `cv` is a dict of metric-name -> list-of-per-round means; the length is
        # the number of rounds actually run before early stopping. Lower is
        # better for both logloss and rmse.
        history = cv[f"test-{metric}-mean"]
        rounds = len(history)
        score = float(history[-1])
        if best_score is None or score < best_score:
            best_score = score
            best = _Chosen(params=dict(grid_point), num_boost_round=rounds)
    assert best is not None  # the grid is non-empty
    return best


def _out_of_fold_predictions(
    xgb: Any,
    features: NDArray[np.float64],
    outcome: NDArray[np.float64],
    weights: NDArray[np.float64] | None,
    fold_pairs: list[tuple[NDArray[np.int64], NDArray[np.int64]]],
    objective: str,
    chosen: _Chosen,
    seed: int,
) -> NDArray[np.float64]:
    """Predict every development row from a model trained without its own fold.

    Each held-out fold is predicted by a booster trained on the other folds, with
    the selected hyperparameters and iteration count. This is the honest,
    representation-agnostic development output the residual/cross-fitting targets
    (T1/T2) build on; it uses the frozen folds and nothing else.
    """
    params = {**_base_params(objective, seed), **chosen.params}
    oof = np.full(features.shape[0], np.nan, dtype=np.float64)
    for train_idx, test_idx in fold_pairs:
        w_train = None if weights is None else weights[train_idx]
        dtrain = xgb.DMatrix(
            features[train_idx], label=outcome[train_idx], weight=w_train
        )
        booster = xgb.train(params, dtrain, num_boost_round=chosen.num_boost_round)
        dtest = xgb.DMatrix(features[test_idx])
        oof[test_idx] = np.asarray(booster.predict(dtest), dtype=np.float64)
    return oof


def _fit_final(
    xgb: Any,
    features: NDArray[np.float64],
    outcome: NDArray[np.float64],
    weights: NDArray[np.float64] | None,
    objective: str,
    chosen: _Chosen,
    seed: int,
) -> Any:
    """Fit the final booster on all development rows for later holdout scoring."""
    params = {**_base_params(objective, seed), **chosen.params}
    dtrain = xgb.DMatrix(features, label=outcome, weight=weights)
    return xgb.train(params, dtrain, num_boost_round=chosen.num_boost_round)


@dataclass(frozen=True)
class RunResult:
    """The emitted development predictions plus the run record and its paths."""

    run_record: dict[str, object]
    obs_ids: list[str]
    predictions: NDArray[np.float64]
    fold_vector: NDArray[np.int64]
    run_record_path: Path
    predictions_path: Path
    model_path: Path
    grid: tuple[dict[str, float], ...] = HYPERPARAMETER_GRID


def _rel(path: Path) -> str:
    """Path relative to the repo root when it lives under it, else absolute.

    Real runs write under the repo; tests and the self-test write to a temp dir
    outside it. Either way the run record carries a usable path string.
    """
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _write_predictions(path: Path, obs_ids: Sequence[str], preds: NDArray[np.float64]) -> None:
    table = pa.table(
        {
            "obs_id": pa.array(list(obs_ids), type=pa.string()),
            "prediction": pa.array(preds.tolist(), type=pa.float64()),
        }
    )
    pq.write_table(table, path, compression="snappy")


def fit_and_predict(
    features: NDArray[np.float64],
    outcome: NDArray[np.float64],
    *,
    groups: Sequence[str],
    obs_ids: Sequence[str],
    objective: str,
    model_id: str,
    target: str,
    representation: str,
    weights: NDArray[np.float64] | None = None,
    seed: int = DEFAULT_SEED,
    split_parquet: Path = SPLIT_PARQUET,
    split_manifest: Path = SPLIT_MANIFEST,
    runs_dir: Path = RUNS_DIR,
) -> RunResult:
    """Fit one benchmark model on development data and emit its predictions.

    The estimator's fitting inputs are the opaque ``features`` matrix, the
    ``outcome`` vector, optional ``weights``, the row ``groups`` (draft ids) and
    ``obs_ids``, the ``objective``, and the frozen split (read via
    :func:`deckbench.holdout.load_dev`). ``model_id``, ``target`` and
    ``representation`` are labels: they are written to the run record and are
    never seen by the code that fits the matrix -- which is exactly why a real
    matrix and a random matrix of the same shape produce the same behaviour.

    Returns the out-of-fold development predictions keyed by ``obs_id`` (no
    holdout row is present) and the run record, and writes three artifacts under
    ``runs_dir``: the predictions parquet, the run record json, and the final
    booster. Computes no metric, score, or calibration quantity.
    """
    features = np.asarray(features, dtype=np.float64)
    outcome = np.asarray(outcome, dtype=np.float64)
    if weights is not None:
        weights = np.asarray(weights, dtype=np.float64)
    if features.ndim != 2:
        raise ValueError(f"features must be a 2-D matrix; got shape {features.shape}.")
    n_rows = features.shape[0]
    if not (len(outcome) == len(obs_ids) == len(groups) == n_rows):
        raise ValueError(
            "features, outcome, obs_ids and groups must share a row count; got "
            f"{n_rows}, {len(outcome)}, {len(obs_ids)}, {len(groups)}."
        )
    if objective not in OBJECTIVES:
        raise ObjectiveUnknown(
            f"objective {objective!r} is not supported; choose one of {OBJECTIVES}."
        )

    # Verify the split's identity before any fit, and take the hash for the record.
    split_sha256 = verify_split_hash(split_parquet, split_manifest)

    # Folds come from the frozen split, aligned to the passed rows. A holdout or
    # unknown id, or a group that disagrees with the split, stops the fit here.
    fold_vector = _aligned_folds(obs_ids, groups, split_parquet)
    fold_pairs = _fold_index_pairs(fold_vector)

    xgb = _import_xgboost()
    chosen = _select_hyperparameters(
        xgb, features, outcome, weights, fold_pairs, objective, seed
    )
    predictions = _out_of_fold_predictions(
        xgb, features, outcome, weights, fold_pairs, objective, chosen, seed
    )
    final_booster = _fit_final(xgb, features, outcome, weights, objective, chosen, seed)

    runs_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = runs_dir / f"{model_id}_predictions.parquet"
    run_record_path = runs_dir / f"{model_id}_run.json"
    model_path = runs_dir / f"{model_id}.xgb"
    _write_predictions(predictions_path, obs_ids, predictions)
    # The .xgb extension is gitignored; xgboost warns that it defaults to UBJSON
    # for an unrecognised extension, which is the format we want. Silence the
    # cosmetic warning rather than rename the artifact out of the ignore rule.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        final_booster.save_model(str(model_path))

    run_record: dict[str, object] = {
        "model_id": model_id,
        "target": target,
        "representation": representation,
        "objective": objective,
        "n_features": int(features.shape[1]),
        "n_dev_rows": int(n_rows),
        "split_sha256": split_sha256,
        "seed": int(seed),
        "chosen_hyperparameters": chosen.params,
        "num_boost_round": int(chosen.num_boost_round),
        "predictions_path": _rel(predictions_path),
        "model_path": _rel(model_path),
        "xgboost_version": _xgboost_library_version(xgb),
        "xgboost_python_version": str(xgb.__version__),
    }
    run_record_path.write_text(
        json.dumps(run_record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return RunResult(
        run_record=run_record,
        obs_ids=list(obs_ids),
        predictions=predictions,
        fold_vector=fold_vector,
        run_record_path=run_record_path,
        predictions_path=predictions_path,
        model_path=model_path,
    )


# --------------------------------------------------------------------------
# Self-test: a full synthetic fit in a temp dir, touching no tracked file.
# --------------------------------------------------------------------------


@dataclass
class _Synthetic:
    features: NDArray[np.float64]
    outcome_binary: NDArray[np.float64]
    outcome_regression: NDArray[np.float64]
    obs_ids: list[str]
    groups: list[str]
    split_parquet: Path
    split_manifest: Path
    holdout_obs_id: str


def _build_synthetic(root: Path, seed: int = 7) -> _Synthetic:
    """Write a tiny synthetic split and matrix, all folds populated."""
    rng = np.random.default_rng(seed)
    n_drafts = 40
    games = 3
    obs_ids: list[str] = []
    groups: list[str] = []
    partitions: list[str] = []
    folds: list[int] = []
    # The latest 4 drafts are the holdout; the rest are development, hashed into
    # 5 folds so every fold is populated.
    for d in range(n_drafts):
        draft = f"draft{d:03d}"
        is_holdout = d >= n_drafts - 4
        for g in range(games):
            obs_ids.append(f"obs{d:03d}{g}")
            groups.append(draft)
            if is_holdout:
                partitions.append("holdout")
                folds.append(-1)
            else:
                partitions.append(DEV)
                folds.append(d % 5)
    split_table = pa.table(
        {
            "obs_id": pa.array(obs_ids, type=pa.string()),
            "draft_id": pa.array(groups, type=pa.string()),
            "partition": pa.array(partitions, type=pa.string()),
            "fold": pa.array(folds, type=pa.int32()),
        }
    )
    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    split_parquet = processed / "model_split.parquet"
    pq.write_table(split_table, split_parquet, compression="snappy")
    splits_dir = root / "data" / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    split_manifest = splits_dir / "split_manifest.json"
    split_manifest.write_text(
        json.dumps({"split_sha256": _sha256(split_parquet)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    n = len(obs_ids)
    features = rng.normal(size=(n, 6)).astype(np.float64)
    signal = features[:, 0] + 0.5 * features[:, 1]
    outcome_binary = (signal + rng.normal(scale=0.5, size=n) > 0).astype(np.float64)
    outcome_regression = signal + rng.normal(scale=0.3, size=n).astype(np.float64)
    return _Synthetic(
        features=features,
        outcome_binary=outcome_binary,
        outcome_regression=outcome_regression,
        obs_ids=obs_ids,
        groups=groups,
        split_parquet=split_parquet,
        split_manifest=split_manifest,
        holdout_obs_id=obs_ids[-1],
    )


def _selftest() -> int:
    """Fit synthetic binary and regression models end to end; check invariants."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        syn = _build_synthetic(root)
        runs = root / "runs"
        # Development rows only (drop the holdout rows the split marks).
        fold_map = dev_fold_map(syn.split_parquet)
        keep = [i for i, o in enumerate(syn.obs_ids) if o in fold_map]
        idx = np.asarray(keep, dtype=np.int64)
        feats = syn.features[idx]
        obs = [syn.obs_ids[i] for i in keep]
        grp = [syn.groups[i] for i in keep]

        common = dict(
            groups=grp,
            obs_ids=obs,
            split_parquet=syn.split_parquet,
            split_manifest=syn.split_manifest,
            runs_dir=runs,
        )
        first = fit_and_predict(
            feats,
            syn.outcome_binary[idx],
            objective=BINARY,
            model_id="selftest_binary",
            target="T0",
            representation="synthetic",
            **common,  # type: ignore[arg-type]
        )
        second = fit_and_predict(
            feats,
            syn.outcome_binary[idx],
            objective=BINARY,
            model_id="selftest_binary_again",
            target="T0",
            representation="synthetic",
            **common,  # type: ignore[arg-type]
        )
        assert np.array_equal(first.predictions, second.predictions), (
            "two fits on identical inputs disagree; the estimator is not deterministic"
        )
        reg = fit_and_predict(
            feats,
            syn.outcome_regression[idx],
            objective=REGRESSION,
            model_id="selftest_regression",
            target="T0",
            representation="synthetic",
            **common,  # type: ignore[arg-type]
        )
        assert set(first.obs_ids) == set(obs)
        assert syn.holdout_obs_id not in set(first.obs_ids), (
            "a holdout row was emitted"
        )
        assert first.run_record["split_sha256"] == _sha256(syn.split_parquet)
        rounds = reg.run_record["num_boost_round"]
        assert isinstance(rounds, int) and rounds >= 1
    print(
        "estimator selftest OK: deterministic binary + regression fits on a "
        "synthetic split, development rows only, no holdout row emitted, no "
        "tracked file touched."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="fit a small synthetic model end to end and check invariants.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.selftest:
        return _selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
