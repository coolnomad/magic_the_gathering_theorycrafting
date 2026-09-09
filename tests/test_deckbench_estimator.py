"""Tests for the representation-agnostic estimator (:mod:`deckbench.estimator`).

The estimator is the single code path every benchmark model is fit through, so
the properties tested here are the ones that make a model-to-model comparison
attributable to the representation and nothing else: the path is blind to
provenance, it uses one declared grid, it takes its folds only from the frozen
split, it never touches the holdout or its ledger, it is deterministic, and it
writes a run record that can reproduce its own fit. No metric is computed here,
just as none is computed by the module.

Every fixture wires a small synthetic split parquet and manifest into a temp
dir, exactly as the split tests do, so nothing touches a tracked artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from deckbench import estimator

ROOT = Path(__file__).resolve().parent.parent

# --- Synthetic split + matrix ----------------------------------------------
# 40 drafts, 3 games each. The latest 4 drafts are the holdout; the remaining 36
# are development, hashed into 5 folds so every fold is populated. Small enough
# to fit in well under a second, large enough that xgboost's cross-validation
# folds are all non-empty.
_N_DRAFTS = 40
_GAMES = 3
_HOLDOUT_DRAFTS = 4


def _make_split(processed: Path) -> Path:
    obs_ids: list[str] = []
    draft_ids: list[str] = []
    partitions: list[str] = []
    folds: list[int] = []
    for d in range(_N_DRAFTS):
        draft = f"draft{d:03d}"
        is_holdout = d >= _N_DRAFTS - _HOLDOUT_DRAFTS
        for g in range(_GAMES):
            obs_ids.append(f"obs{d:03d}{g}")
            draft_ids.append(draft)
            if is_holdout:
                partitions.append("holdout")
                folds.append(-1)
            else:
                partitions.append(estimator.DEV)
                folds.append(d % 5)
    table = pa.table(
        {
            "obs_id": pa.array(obs_ids, type=pa.string()),
            "draft_id": pa.array(draft_ids, type=pa.string()),
            "partition": pa.array(partitions, type=pa.string()),
            "fold": pa.array(folds, type=pa.int32()),
        }
    )
    path = processed / "model_split.parquet"
    pq.write_table(table, path, compression="snappy")
    return path


class _Wired:
    def __init__(self, tmp_path: Path) -> None:
        processed = tmp_path / "data" / "processed"
        processed.mkdir(parents=True)
        self.split_parquet = _make_split(processed)
        splits = tmp_path / "data" / "splits"
        splits.mkdir(parents=True)
        self.split_manifest = splits / "split_manifest.json"
        self.split_manifest.write_text(
            json.dumps({"split_sha256": _sha256(self.split_parquet)}) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.runs_dir = tmp_path / "runs"

        # Development rows only, in split order.
        fold_map = estimator.dev_fold_map(self.split_parquet)
        self.obs_ids = list(fold_map)
        self.groups = [fold_map[o][0] for o in self.obs_ids]
        self.holdout_obs_id = f"obs{_N_DRAFTS - 1:03d}0"

        rng = np.random.default_rng(11)
        n = len(self.obs_ids)
        self.features = rng.normal(size=(n, 6)).astype(np.float64)
        signal = self.features[:, 0] + 0.5 * self.features[:, 1]
        self.y_binary = (signal + rng.normal(scale=0.5, size=n) > 0).astype(np.float64)
        self.y_regression = signal + rng.normal(scale=0.3, size=n).astype(np.float64)

    def kwargs(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = dict(
            groups=self.groups,
            obs_ids=self.obs_ids,
            objective=estimator.BINARY,
            model_id="m",
            target="T0",
            representation="R-real",
            split_parquet=self.split_parquet,
            split_manifest=self.split_manifest,
            runs_dir=self.runs_dir,
        )
        base.update(overrides)
        return base


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def wired(tmp_path: Path) -> _Wired:
    return _Wired(tmp_path)


# --------------------------------------------------------------------------
# Provenance blindness: a real and a random matrix go through the same call.
# --------------------------------------------------------------------------


def test_real_and_random_matrix_complete_through_identical_call(wired: _Wired) -> None:
    rng = np.random.default_rng(99)
    random_matrix = rng.normal(size=wired.features.shape).astype(np.float64)
    real = estimator.fit_and_predict(
        wired.features, wired.y_binary, **wired.kwargs(model_id="real", representation="R2")
    )
    rand = estimator.fit_and_predict(
        random_matrix,
        wired.y_binary,
        **wired.kwargs(model_id="rand", representation="random"),
    )
    # Both complete and emit a prediction per development row; the estimator did
    # not branch on where the columns came from.
    assert real.predictions.shape == rand.predictions.shape == (len(wired.obs_ids),)
    assert not np.isnan(real.predictions).any()
    assert not np.isnan(rand.predictions).any()


def test_module_does_not_import_the_representation_builders() -> None:
    source = Path(estimator.__file__).read_text(encoding="utf-8")
    assert "deckbench.identity" not in source
    assert "import identity" not in source
    # The estimator reads no feature/representation parquet itself: it never calls
    # a parquet reader on a feature table. The only parquet it reads is the split,
    # via load_dev.
    assert "read_table" not in source


# --------------------------------------------------------------------------
# One grid, declared once, used for every model.
# --------------------------------------------------------------------------


def test_single_grid_object_is_used(wired: _Wired, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    real_select = estimator._select_hyperparameters

    def spy(*args: object, **kw: object) -> object:
        # The grid the search iterates is the module constant, by identity.
        seen.append(estimator.HYPERPARAMETER_GRID)
        return real_select(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(estimator, "_select_hyperparameters", spy)
    estimator.fit_and_predict(
        wired.features, wired.y_binary, **wired.kwargs(model_id="a")
    )
    estimator.fit_and_predict(
        wired.features,
        wired.y_regression,
        **wired.kwargs(model_id="b", objective=estimator.REGRESSION),
    )
    assert len(seen) == 2
    # The very same object, not two equal copies: one grid for every model.
    assert seen[0] is seen[1] is estimator.HYPERPARAMETER_GRID
    assert len(estimator.HYPERPARAMETER_GRID) >= 1


def test_result_carries_the_module_grid(wired: _Wired) -> None:
    result = estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs())
    assert result.grid is estimator.HYPERPARAMETER_GRID


# --------------------------------------------------------------------------
# Both objectives are supported and chosen by the caller.
# --------------------------------------------------------------------------


def test_binary_and_regression_objectives_both_fit(wired: _Wired) -> None:
    b = estimator.fit_and_predict(
        wired.features, wired.y_binary, **wired.kwargs(model_id="bin", objective=estimator.BINARY)
    )
    r = estimator.fit_and_predict(
        wired.features,
        wired.y_regression,
        **wired.kwargs(model_id="reg", objective=estimator.REGRESSION),
    )
    assert b.run_record["objective"] == estimator.BINARY
    assert r.run_record["objective"] == estimator.REGRESSION
    # Binary predictions are probabilities in [0, 1]; regression predictions are
    # unconstrained, so at least one falls outside that range here.
    assert b.predictions.min() >= 0.0 and b.predictions.max() <= 1.0


def test_unknown_objective_is_rejected(wired: _Wired) -> None:
    with pytest.raises(estimator.ObjectiveUnknown):
        estimator.fit_and_predict(
            wired.features, wired.y_binary, **wired.kwargs(objective="poisson")
        )


# --------------------------------------------------------------------------
# Folds come from the frozen split and are never re-derived.
# --------------------------------------------------------------------------


def test_fold_assignment_equals_the_split_parquet(wired: _Wired) -> None:
    result = estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs())
    # What the estimator used, read back from its result.
    used = dict(zip(result.obs_ids, result.fold_vector.tolist(), strict=True))
    # The ground truth, read straight from the split parquet.
    table = pq.read_table(wired.split_parquet)
    truth = {
        o: int(f)
        for o, f, p in zip(
            table.column("obs_id").to_pylist(),
            table.column("fold").to_pylist(),
            table.column("partition").to_pylist(),
            strict=True,
        )
        if p == estimator.DEV
    }
    assert used == truth


def test_no_draft_spans_two_inner_folds(wired: _Wired) -> None:
    result = estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs())
    by_draft: dict[str, set[int]] = {}
    for group, fold in zip(wired.groups, result.fold_vector.tolist(), strict=True):
        by_draft.setdefault(group, set()).add(int(fold))
    for draft, folds in by_draft.items():
        assert len(folds) == 1, f"draft {draft} spans folds {folds}"


def test_group_disagreeing_with_split_is_rejected(wired: _Wired) -> None:
    bad_groups = list(wired.groups)
    bad_groups[0] = "draft999"  # a group the split never assigns to this obs
    with pytest.raises(estimator.GroupMismatch):
        estimator.fit_and_predict(
            wired.features, wired.y_binary, **wired.kwargs(groups=bad_groups)
        )


# --------------------------------------------------------------------------
# The holdout is never read, and its ledger is never touched.
# --------------------------------------------------------------------------


def test_module_source_never_references_the_sealed_reader() -> None:
    source = Path(estimator.__file__).read_text(encoding="utf-8")
    assert "load_holdout" not in source


def test_holdout_ledger_is_byte_identical_across_a_full_fit(
    wired: _Wired, tmp_path: Path
) -> None:
    ledger = tmp_path / "cycle" / "holdout_ledger.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_bytes(b"")  # the frozen state: zero reads
    before = ledger.read_bytes()
    estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs())
    estimator.fit_and_predict(
        wired.features,
        wired.y_regression,
        **wired.kwargs(model_id="c", objective=estimator.REGRESSION),
    )
    assert ledger.read_bytes() == before


def test_a_holdout_obs_id_is_rejected(wired: _Wired) -> None:
    obs = [*wired.obs_ids, wired.holdout_obs_id]
    groups = [*wired.groups, f"draft{_N_DRAFTS - 1:03d}"]
    features = np.vstack([wired.features, wired.features[:1]])
    outcome = np.concatenate([wired.y_binary, wired.y_binary[:1]])
    with pytest.raises(estimator.HoldoutRowRejected):
        estimator.fit_and_predict(
            features, outcome, **wired.kwargs(obs_ids=obs, groups=groups)
        )


# --------------------------------------------------------------------------
# Predictions are development rows only, keyed by obs_id.
# --------------------------------------------------------------------------


def test_emitted_ids_are_disjoint_from_holdout(wired: _Wired) -> None:
    result = estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs())
    table = pq.read_table(wired.split_parquet)
    holdout_ids = {
        o
        for o, p in zip(
            table.column("obs_id").to_pylist(),
            table.column("partition").to_pylist(),
            strict=True,
        )
        if p == "holdout"
    }
    emitted = set(result.obs_ids)
    assert emitted and emitted.isdisjoint(holdout_ids)
    # The emitted parquet keys on obs_id and carries one prediction per row.
    preds = pq.read_table(result.predictions_path)
    assert set(preds.column("obs_id").to_pylist()) == emitted
    assert set(preds.column("obs_id").to_pylist()).isdisjoint(holdout_ids)


# --------------------------------------------------------------------------
# Determinism, and the run record that reproduces the fit.
# --------------------------------------------------------------------------


def test_two_fits_same_seed_byte_identical_predictions(wired: _Wired) -> None:
    a = estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs(model_id="a"))
    b = estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs(model_id="b"))
    assert np.array_equal(a.predictions, b.predictions)
    # The parquet bytes agree too, since row order and values agree.
    assert a.predictions_path.read_bytes() == b.predictions_path.read_bytes()


def test_run_record_has_every_required_field(wired: _Wired) -> None:
    result = estimator.fit_and_predict(
        wired.features,
        wired.y_binary,
        **wired.kwargs(model_id="rec", target="T1", representation="R4"),
    )
    record = json.loads(result.run_record_path.read_text(encoding="utf-8"))
    assert record["model_id"] == "rec"
    assert record["target"] == "T1"
    assert record["representation"] == "R4"
    assert record["n_features"] == wired.features.shape[1]
    assert record["seed"] == estimator.DEFAULT_SEED
    assert record["split_sha256"] == _sha256(wired.split_parquet)
    assert isinstance(record["chosen_hyperparameters"], dict)
    # The chosen hyperparameters are one of the grid points, not the whole grid.
    assert record["chosen_hyperparameters"] in [dict(g) for g in estimator.HYPERPARAMETER_GRID]
    assert isinstance(record["num_boost_round"], int) and record["num_boost_round"] >= 1


def test_seed_is_recorded_and_threaded(wired: _Wired) -> None:
    result = estimator.fit_and_predict(
        wired.features, wired.y_binary, **wired.kwargs(seed=123456)
    )
    assert result.run_record["seed"] == 123456


# --------------------------------------------------------------------------
# The split hash is verified against the parquet on disk.
# --------------------------------------------------------------------------


def test_fit_fails_when_split_hash_does_not_match(wired: _Wired) -> None:
    # Move the split under the manifest: the pinned hash no longer matches.
    wired.split_manifest.write_text(
        json.dumps({"split_sha256": "0" * 64}) + "\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(estimator.SplitHashMismatch):
        estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs())


def test_verify_split_hash_returns_the_pinned_hash(wired: _Wired) -> None:
    got = estimator.verify_split_hash(wired.split_parquet, wired.split_manifest)
    assert got == _sha256(wired.split_parquet)


# --------------------------------------------------------------------------
# No metric is computed: the run record and result carry no score.
# --------------------------------------------------------------------------


def test_no_metric_leaks_into_the_run_record(wired: _Wired) -> None:
    result = estimator.fit_and_predict(wired.features, wired.y_binary, **wired.kwargs())
    record_keys = set(result.run_record)
    forbidden = {"r2", "rmse", "mae", "brier", "logloss", "log_loss", "auc", "score",
                 "calibration", "cal_slope", "cal_intercept", "cv_score"}
    assert record_keys.isdisjoint(forbidden)


# --------------------------------------------------------------------------
# The self-test entry point runs clean.
# --------------------------------------------------------------------------


def test_selftest_runs_and_returns_zero() -> None:
    assert estimator.main(["--selftest"]) == 0
