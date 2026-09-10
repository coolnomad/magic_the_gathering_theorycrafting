"""Tests for T0 (011), T1 (015) and T2 (016) R0/R1 fitting (:mod:`deckbench.targets`).

The real fits run on 194,215 development rows and take minutes, far beyond the
validation budget, so these tests never fit the real dataset. Two fixtures cover
the two things that need checking:

* a **synthetic** wiring (a small split + skill + identity + model table in a
  temp dir) drives assembly, the fit-through-the-estimator path, the timing
  probe, the panel, the budget decision, determinism, the T1 and T2 residual
  targets and their reconstruction, and ``verify`` end to end, fast; and
* a **real-artifact** group, run only when the frozen phase-1 parquets are on
  disk, pins the two facts about the real data the card asserts -- R0 has exactly
  one feature ``base_p`` and R1 has exactly 194 -- and checks the tracked run
  records the actual fits produced for all three targets.

The load-bearing guards are that every fit goes through the estimator (no learner
is built here), that T1 and T2 fit the residual under the regression objective,
that T2's baseline is the out-of-fold vector and not the full-data refit, that no
assembled or emitted row is a holdout row, and that the holdout ledger is
byte-identical across a build.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from deckbench import estimator, evaluation, targets

ROOT = Path(__file__).resolve().parent.parent

# The frozen phase-1 artifacts, present here but gitignored; the real-data group
# skips when a fresh checkout has not rebuilt them.
_REAL = targets.Sources()
_REAL_PRESENT = (
    _REAL.split_parquet.exists()
    and _REAL.skill_parquet.exists()
    and _REAL.identity_parquet.exists()
    and _REAL.model_table.exists()
)
requires_real = pytest.mark.skipif(
    not _REAL_PRESENT, reason="frozen phase-1 parquets not on disk"
)


# --------------------------------------------------------------------------
# Synthetic fixture: a small split and three aligned tables in a temp dir.
# --------------------------------------------------------------------------

_N_DRAFTS = 40
_GAMES = 3
_HOLDOUT_DRAFTS = 4
_N_CARDS = 5


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Wired:
    """A synthetic split plus skill/identity/model tables that all share obs_ids."""

    def __init__(self, tmp_path: Path) -> None:
        processed = tmp_path / "data" / "processed"
        processed.mkdir(parents=True)
        splits = tmp_path / "data" / "splits"
        splits.mkdir(parents=True)

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
                    partitions.append(targets.HOLDOUT)
                    folds.append(-1)
                else:
                    partitions.append(estimator.DEV)
                    folds.append(d % 5)
        self.all_obs_ids = obs_ids
        self.holdout_obs_id = f"obs{_N_DRAFTS - 1:03d}0"

        split = pa.table(
            {
                "obs_id": pa.array(obs_ids, type=pa.string()),
                "draft_id": pa.array(draft_ids, type=pa.string()),
                "partition": pa.array(partitions, type=pa.string()),
                "fold": pa.array(folds, type=pa.int32()),
            }
        )
        self.split_parquet = processed / "model_split.parquet"
        pq.write_table(split, self.split_parquet, compression="snappy")
        self.split_manifest = splits / "split_manifest.json"
        self.split_manifest.write_text(
            json.dumps({"split_sha256": _sha256(self.split_parquet)}) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        rng = np.random.default_rng(3)
        n = len(obs_ids)
        base_p = rng.uniform(0.4, 0.65, size=n)
        self.skill_parquet = processed / "skill_features.parquet"
        pq.write_table(
            pa.table(
                {
                    "obs_id": pa.array(obs_ids, type=pa.string()),
                    "base_p_raw": pa.array(base_p, type=pa.float64()),
                    "base_p": pa.array(base_p, type=pa.float64()),
                }
            ),
            self.skill_parquet,
            compression="snappy",
        )

        # A card-fraction table whose rows sum to 1, one column per synthetic card.
        cards = rng.dirichlet(np.ones(_N_CARDS), size=n)
        identity_cols: dict[str, object] = {"obs_id": pa.array(obs_ids, type=pa.string())}
        for j in range(_N_CARDS):
            identity_cols[f"card_c{j}"] = pa.array(cards[:, j], type=pa.float64())
        self.identity_parquet = processed / "deck_identity.parquet"
        pq.write_table(pa.table(identity_cols), self.identity_parquet, compression="snappy")

        # The model table carries the string outcome the card maps to {0, 1}.
        signal = base_p - 0.5 + 0.1 * cards[:, 0]
        won = (signal + rng.normal(scale=0.2, size=n) > 0).tolist()
        self.model_table = processed / "model_table.parquet"
        pq.write_table(
            pa.table(
                {
                    "obs_id": pa.array(obs_ids, type=pa.string()),
                    "won": pa.array([str(bool(w)) for w in won], type=pa.string()),
                    "deck_size": pa.array([40] * n, type=pa.int32()),
                }
            ),
            self.model_table,
            compression="snappy",
        )

        self.sources = targets.Sources(
            split_parquet=self.split_parquet,
            split_manifest=self.split_manifest,
            skill_parquet=self.skill_parquet,
            identity_parquet=self.identity_parquet,
            model_table=self.model_table,
        )
        self.runs_dir = tmp_path / "runs"
        self.report_path = tmp_path / "report.md"
        self.report_t1_path = tmp_path / "report_t1.md"
        self.report_t2_path = tmp_path / "report_t2.md"
        self.ledger_path = tmp_path / "cycle" / "holdout_ledger.jsonl"

    @property
    def dev_obs_ids(self) -> set[str]:
        table = pq.read_table(self.split_parquet)
        return {
            o
            for o, p in zip(
                table.column("obs_id").to_pylist(),
                table.column("partition").to_pylist(),
                strict=True,
            )
            if p == estimator.DEV
        }

    @property
    def holdout_ids(self) -> set[str]:
        table = pq.read_table(self.split_parquet)
        return {
            o
            for o, p in zip(
                table.column("obs_id").to_pylist(),
                table.column("partition").to_pylist(),
                strict=True,
            )
            if p == targets.HOLDOUT
        }


@pytest.fixture
def wired(tmp_path: Path) -> _Wired:
    return _Wired(tmp_path)


# --------------------------------------------------------------------------
# Assembly: shape, order, dev-only rows, outcome mapping, totality.
# --------------------------------------------------------------------------


def test_r0_has_exactly_one_base_p_feature(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    assert a0.features.shape[1] == 1
    assert a0.feature_names == [targets.BASE_P_COL]


def test_r1_is_base_p_plus_every_card_fraction(wired: _Wired) -> None:
    a1 = targets.assemble(targets.R1, wired.sources)
    assert a1.features.shape[1] == 1 + _N_CARDS
    assert a1.feature_names[0] == targets.BASE_P_COL
    # base_p is column 0; the remaining columns are exactly the identity columns.
    assert a1.feature_names[1:] == [f"card_c{j}" for j in range(_N_CARDS)]


def test_assembly_is_dev_rows_only_in_split_order(wired: _Wired) -> None:
    a1 = targets.assemble(targets.R1, wired.sources)
    assert set(a1.obs_ids) == wired.dev_obs_ids
    assert set(a1.obs_ids).isdisjoint(wired.holdout_ids)
    # Row order equals load_dev's row order.
    dev = pq.read_table(wired.split_parquet)
    expected = [
        o
        for o, p in zip(
            dev.column("obs_id").to_pylist(),
            dev.column("partition").to_pylist(),
            strict=True,
        )
        if p == estimator.DEV
    ]
    assert a1.obs_ids == expected


def test_outcome_is_mapped_to_zero_one(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    assert set(np.unique(a0.outcome)).issubset({0.0, 1.0})
    assert a0.outcome.shape == (len(a0.obs_ids),)


def test_groups_are_the_draft_ids(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    split = pq.read_table(wired.split_parquet)
    truth = dict(
        zip(
            split.column("obs_id").to_pylist(),
            split.column("draft_id").to_pylist(),
            strict=True,
        )
    )
    for obs_id, group in zip(a0.obs_ids, a0.groups, strict=True):
        assert group == truth[obs_id]


def test_unknown_representation_is_rejected(wired: _Wired) -> None:
    with pytest.raises(targets.RepresentationUnknown):
        targets.assemble("R2", wired.sources)


def test_unexpected_outcome_value_stops_the_run(wired: _Wired, tmp_path: Path) -> None:
    # Corrupt one outcome cell to a value outside the {True, False} mapping.
    tbl = pq.read_table(wired.model_table)
    won = tbl.column("won").to_pylist()
    won[0] = "Maybe"
    bad = tbl.set_column(tbl.schema.get_field_index("won"), "won", pa.array(won, pa.string()))
    pq.write_table(bad, wired.model_table, compression="snappy")
    with pytest.raises(targets.UnexpectedOutcomeValue):
        targets.assemble(targets.R0, wired.sources)


def test_non_total_join_stops_the_run(wired: _Wired) -> None:
    # Drop one development row from the identity table: the join is no longer total.
    tbl = pq.read_table(wired.identity_parquet)
    dev_id = sorted(wired.dev_obs_ids)[0]
    keep = [o != dev_id for o in tbl.column("obs_id").to_pylist()]
    pq.write_table(tbl.filter(pa.array(keep)), wired.identity_parquet, compression="snappy")
    with pytest.raises(targets.JoinNotTotal):
        targets.assemble(targets.R1, wired.sources)


# --------------------------------------------------------------------------
# The fit goes through the estimator, and no learner is built here.
# --------------------------------------------------------------------------


def test_module_builds_no_learner_grid_or_folds() -> None:
    source = Path(targets.__file__).read_text(encoding="utf-8")
    # No hyperparameter grid, fold construction, or split reader defined locally:
    # every one of those comes from the estimator.
    assert "HYPERPARAMETER_GRID: " not in source  # only referenced, never redefined
    assert "def _fold_index_pairs" not in source
    assert "def fit_and_predict" not in source
    # The holdout's sealed reader is never named.
    assert "load_holdout" not in source


def test_fit_goes_through_the_estimator(wired: _Wired, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    real = estimator.fit_and_predict

    def spy(*args: object, **kw: object) -> object:
        calls.append(kw)
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(estimator, "fit_and_predict", spy)
    a0 = targets.assemble(targets.R0, wired.sources)
    result = targets.fit_representation(a0, wired.sources, wired.runs_dir)
    assert len(calls) == 1
    assert calls[0]["objective"] == estimator.BINARY
    assert calls[0]["target"] == targets.TARGET
    assert calls[0]["representation"] == targets.R0
    assert result.run_record["n_features"] == 1


def test_fit_emits_dev_only_predictions_disjoint_from_holdout(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    result = targets.fit_representation(a0, wired.sources, wired.runs_dir)
    emitted = set(result.obs_ids)
    assert emitted == wired.dev_obs_ids
    assert emitted.isdisjoint(wired.holdout_ids)
    preds = pq.read_table(result.predictions_path)
    assert set(preds.column("obs_id").to_pylist()).isdisjoint(wired.holdout_ids)


def test_refitting_r0_is_byte_identical(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    first = targets.fit_representation(a0, wired.sources, wired.runs_dir)
    before = first.predictions_path.read_bytes()
    second = targets.fit_representation(a0, wired.sources, wired.runs_dir)
    assert np.array_equal(first.predictions, second.predictions)
    assert second.predictions_path.read_bytes() == before


# --------------------------------------------------------------------------
# The timing probe and the budget decision.
# --------------------------------------------------------------------------


def test_probe_projects_the_full_search(wired: _Wired) -> None:
    a1 = targets.assemble(targets.R1, wired.sources)
    probe = targets.timing_probe(a1, wired.sources.split_parquet)
    n_grid = len(estimator.HYPERPARAMETER_GRID)
    assert probe.n_fits == n_grid * 5 + 5 + 1
    assert probe.probe_seconds > 0.0
    assert probe.projected_seconds == pytest.approx(probe.probe_seconds * probe.n_fits)


def test_over_budget_stops_after_r0(wired: _Wired) -> None:
    # A zero budget forces the R1 skip branch: R0 is fitted, R1 is not attempted.
    result = targets.build(
        wired.sources,
        wired.runs_dir,
        budget_seconds=0.0,
        report_path=wired.report_path,
    )
    assert result.r1_attempted is False
    assert result.r1_record is None
    assert result.r1_skip_reason is not None
    assert (wired.runs_dir / "T0_R0_run.json").exists()
    assert not (wired.runs_dir / "T0_R1_run.json").exists()
    # The report records the projection and the reason R1 was not attempted.
    text = wired.report_path.read_text(encoding="utf-8")
    assert "not attempted" in text
    assert f"{result.probe.projected_seconds:.0f}s" in text


# --------------------------------------------------------------------------
# The panel is applied and produces sane Bernoulli probabilities.
# --------------------------------------------------------------------------


def test_development_metrics_are_the_bernoulli_panel(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    result = targets.fit_representation(a0, wired.sources, wired.runs_dir)
    metrics = targets.development_metrics(a0.outcome, result.predictions)
    # The Bernoulli panel: no bare r2, a brier_skill_score instead.
    assert "r2" not in metrics
    assert "brier_skill_score" in metrics
    for key in ("log_loss", "brier", "rmse", "mae", "auc", "cal_intercept", "cal_slope"):
        assert key in metrics
    # xgboost's logistic objective emits probabilities in the unit interval.
    assert 0.0 <= result.predictions.min() and result.predictions.max() <= 1.0


# --------------------------------------------------------------------------
# build() end to end on the synthetic wiring, and the ledger stays untouched.
# --------------------------------------------------------------------------


def test_build_fits_r0_before_r1(wired: _Wired, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    real = estimator.fit_and_predict

    def spy(*args: object, **kw: object) -> object:
        order.append(str(kw["representation"]))
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(estimator, "fit_and_predict", spy)
    targets.build(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_path,
    )
    assert order == [targets.R0, targets.R1]


def test_build_leaves_the_holdout_ledger_byte_identical(wired: _Wired) -> None:
    wired.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    wired.ledger_path.write_bytes(b"")  # the frozen state: zero reads
    before = wired.ledger_path.read_bytes()
    targets.build(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_path,
    )
    assert wired.ledger_path.read_bytes() == before


# --------------------------------------------------------------------------
# T1: the residual target, the regression objective, and the reconstruction.
# --------------------------------------------------------------------------


def test_bump_target_has_both_signs_and_is_not_the_unit_interval(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    bump = targets.bump_target(a0)
    # A genuine residual, not the raw outcome relabelled: both signs are present
    # and it escapes [0, 1] on the low side (a loss below the proxy is negative).
    assert bool((bump < 0.0).any())
    assert bool((bump > 0.0).any())
    assert float(bump.min()) < 0.0
    # It is exactly won - base_p.
    assert np.allclose(bump, a0.outcome - a0.base_p)


def test_t1_fit_uses_the_regression_objective(
    wired: _Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []
    real = estimator.fit_and_predict

    def spy(*args: object, **kw: object) -> object:
        calls.append(kw)
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(estimator, "fit_and_predict", spy)
    a0 = targets.assemble(targets.R0, wired.sources)
    run = targets.fit_representation(a0, wired.sources, wired.runs_dir, target=targets.TARGET_T1)
    assert len(calls) == 1
    assert calls[0]["objective"] == estimator.REGRESSION
    assert calls[0]["target"] == targets.TARGET_T1
    assert run.run_record["model_id"] == "T1_R0"
    assert run.run_record["objective"] == "regression"
    assert run.run_record["n_features"] == 1
    # The regression prediction is a bump, not a probability: it takes both signs.
    assert bool((run.predictions < 0.0).any())


def test_build_t1_records_feature_counts_and_regression(wired: _Wired) -> None:
    result = targets.build_t1(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t1_path,
    )
    assert result.r0.record["n_features"] == 1
    assert result.r0.record["objective"] == "regression"
    assert result.r0.record["target"] == "T1"
    assert result.r1 is not None
    assert result.r1.record["n_features"] == 1 + _N_CARDS
    assert result.r1.record["objective"] == "regression"


def test_t1_reconstruction_artifact_carries_bump_and_probability(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    targets._fit_t1_model(a0, wired.sources, wired.runs_dir)
    recon_path = wired.runs_dir / "T1_R0_reconstruction.parquet"
    assert recon_path.exists()
    tbl = pq.read_table(recon_path)
    for col in (
        "obs_id",
        targets.BUMP_COL,
        targets.BASE_P_COL,
        targets.RECON_RAW_COL,
        targets.RECON_PROB_COL,
    ):
        assert col in tbl.column_names
    ids = set(tbl.column("obs_id").to_pylist())
    assert ids == wired.dev_obs_ids
    assert ids.isdisjoint(wired.holdout_ids)
    # The reconstruction is base_p + bump, clipped into the panel's unit interval.
    base_p = np.asarray(tbl.column(targets.BASE_P_COL).to_numpy(zero_copy_only=False))
    bump = np.asarray(tbl.column(targets.BUMP_COL).to_numpy(zero_copy_only=False))
    raw = np.asarray(tbl.column(targets.RECON_RAW_COL).to_numpy(zero_copy_only=False))
    prob = np.asarray(tbl.column(targets.RECON_PROB_COL).to_numpy(zero_copy_only=False))
    assert np.allclose(raw, base_p + bump)
    clip = evaluation.PROBABILITY_CLIP
    assert float(prob.min()) >= clip
    assert float(prob.max()) <= 1.0 - clip
    assert np.allclose(prob, np.clip(raw, clip, 1.0 - clip))


def test_t1_clip_counts_match_the_raw_reconstruction(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    result = targets._fit_t1_model(a0, wired.sources, wired.runs_dir)
    tbl = pq.read_table(wired.runs_dir / "T1_R0_reconstruction.parquet")
    raw = np.asarray(tbl.column(targets.RECON_RAW_COL).to_numpy(zero_copy_only=False))
    clip = evaluation.PROBABILITY_CLIP
    stats = result.recon_stats
    assert stats.n_clipped_low == int(np.count_nonzero(raw < clip))
    assert stats.n_clipped_high == int(np.count_nonzero(raw > 1.0 - clip))
    assert stats.n_clipped == stats.n_clipped_low + stats.n_clipped_high
    assert stats.n_rows == len(a0.obs_ids)


def test_t1_scores_both_the_continuous_and_the_bernoulli_views(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    result = targets._fit_t1_model(a0, wired.sources, wired.runs_dir)
    # Continuous view (on the bump): weighted r2, no probabilistic metrics.
    assert "r2" in result.continuous_metrics
    assert "log_loss" not in result.continuous_metrics
    assert "auc" not in result.continuous_metrics
    # Bernoulli view (on the reconstructed probability): no bare r2, a BSS instead.
    assert "r2" not in result.reconstructed_metrics
    assert "brier_skill_score" in result.reconstructed_metrics
    for key in ("log_loss", "brier", "rmse", "mae", "auc", "cal_intercept", "cal_slope"):
        assert key in result.reconstructed_metrics


def test_refitting_t1_r0_is_byte_identical(wired: _Wired) -> None:
    a0 = targets.assemble(targets.R0, wired.sources)
    first = targets.fit_representation(a0, wired.sources, wired.runs_dir, target=targets.TARGET_T1)
    before = first.predictions_path.read_bytes()
    second = targets.fit_representation(
        a0, wired.sources, wired.runs_dir, target=targets.TARGET_T1
    )
    assert np.array_equal(first.predictions, second.predictions)
    assert second.predictions_path.read_bytes() == before


def test_build_t1_fits_r0_before_r1(wired: _Wired, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    real = estimator.fit_and_predict

    def spy(*args: object, **kw: object) -> object:
        order.append(str(kw["representation"]))
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(estimator, "fit_and_predict", spy)
    targets.build_t1(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t1_path,
    )
    assert order == [targets.R0, targets.R1]


def test_t1_over_budget_stops_after_r0(wired: _Wired) -> None:
    result = targets.build_t1(
        wired.sources,
        wired.runs_dir,
        budget_seconds=0.0,
        report_path=wired.report_t1_path,
    )
    assert result.r1_attempted is False
    assert result.r1 is None
    assert result.r1_skip_reason is not None
    assert (wired.runs_dir / "T1_R0_run.json").exists()
    assert not (wired.runs_dir / "T1_R1_run.json").exists()
    text = wired.report_t1_path.read_text(encoding="utf-8")
    assert "not attempted" in text
    assert f"{result.probe.projected_seconds:.0f}s" in text


def test_build_t1_leaves_the_holdout_ledger_byte_identical(wired: _Wired) -> None:
    wired.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    wired.ledger_path.write_bytes(b"")  # the frozen state: zero reads
    before = wired.ledger_path.read_bytes()
    targets.build_t1(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t1_path,
    )
    assert wired.ledger_path.read_bytes() == before


# --------------------------------------------------------------------------
# verify(): passes on a good build of all three targets, fails on a tampered one.
# --------------------------------------------------------------------------


def _build_both(wired: _Wired) -> None:
    """Fit T0, T1 and T2 R0/R1 on the synthetic wiring, ledger frozen empty.

    T0 is fitted first because its ``T0_R0`` out-of-fold predictions are the
    cross-fitted baseline T2 residualizes against.
    """
    wired.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    wired.ledger_path.write_bytes(b"")
    targets.build(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_path,
    )
    targets.build_t1(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t1_path,
    )
    targets.build_t2(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t2_path,
    )


def _verify(wired: _Wired) -> int:
    return targets.verify(
        wired.sources,
        wired.runs_dir,
        wired.report_path,
        wired.ledger_path,
        wired.report_t1_path,
        wired.report_t2_path,
    )


def test_verify_passes_on_a_good_build(wired: _Wired) -> None:
    _build_both(wired)
    assert _verify(wired) == 0


def test_verify_fails_when_r0_is_missing(wired: _Wired) -> None:
    wired.runs_dir.mkdir(parents=True, exist_ok=True)
    wired.report_path.write_text("stub", encoding="utf-8")
    wired.report_t1_path.write_text("stub", encoding="utf-8")
    assert _verify(wired) == 1


def test_verify_fails_when_ledger_is_dirty(wired: _Wired) -> None:
    _build_both(wired)
    wired.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    wired.ledger_path.write_text('{"card_id": "099"}\n', encoding="utf-8")
    assert _verify(wired) == 1


def test_verify_fails_when_a_t1_run_record_is_removed(wired: _Wired) -> None:
    _build_both(wired)
    assert _verify(wired) == 0  # the build is good to begin with
    (wired.runs_dir / "T1_R0_run.json").unlink()
    assert _verify(wired) == 1


def test_verify_fails_when_a_t1_reconstruction_is_removed(wired: _Wired) -> None:
    _build_both(wired)
    assert _verify(wired) == 0
    # Removing only the reconstruction artifact -- the run record and predictions
    # still present -- must still fail: the check is not vacuous.
    (wired.runs_dir / "T1_R1_reconstruction.parquet").unlink()
    assert _verify(wired) == 1


def test_verify_fails_when_a_t2_run_record_is_removed(wired: _Wired) -> None:
    _build_both(wired)
    assert _verify(wired) == 0  # the build is good to begin with
    (wired.runs_dir / "T2_R0_run.json").unlink()
    assert _verify(wired) == 1


def test_verify_fails_when_a_t2_reconstruction_is_removed(wired: _Wired) -> None:
    _build_both(wired)
    assert _verify(wired) == 0
    # Removing only the T2 reconstruction -- run record and predictions still
    # present -- must still fail: verify covers T2 artifacts, not only T0/T1.
    (wired.runs_dir / "T2_R1_reconstruction.parquet").unlink()
    assert _verify(wired) == 1


# --------------------------------------------------------------------------
# T2: the cross-fitted learned baseline, the residual, and the reconstruction.
# --------------------------------------------------------------------------


def _split_sha(wired: _Wired) -> str:
    return estimator.verify_split_hash(wired.sources.split_parquet, wired.sources.split_manifest)


def _fit_baseline(wired: _Wired) -> targets.Assembled:
    """Fit T0_R0 on the synthetic wiring; its OOF predictions are T2's baseline."""
    a0 = targets.assemble(targets.R0, wired.sources)
    targets.fit_representation(a0, wired.sources, wired.runs_dir, target=targets.TARGET_T0)
    return a0


def test_t2_target_objective_is_regression() -> None:
    assert targets.TARGET_T2 in targets.TARGETS
    assert targets.TARGET_OBJECTIVE[targets.TARGET_T2] == estimator.REGRESSION


def test_load_baseline_fails_when_t0_r0_is_missing(wired: _Wired) -> None:
    with pytest.raises(targets.BaselineRecordInvalid):
        targets.load_baseline(wired.runs_dir, _split_sha(wired), estimator.DEFAULT_SEED)


def test_load_baseline_rejects_a_mismatched_record(wired: _Wired) -> None:
    _fit_baseline(wired)
    sha = _split_sha(wired)
    # A good baseline loads without complaint.
    targets.load_baseline(wired.runs_dir, sha, estimator.DEFAULT_SEED)
    # Corrupt the T0_R0 record's objective: it is no longer the binary baseline
    # T2 requires, so residualizing against it must be refused.
    rec_path = wired.runs_dir / "T0_R0_run.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    rec["objective"] = "regression"
    rec_path.write_text(json.dumps(rec), encoding="utf-8", newline="\n")
    with pytest.raises(targets.BaselineRecordInvalid):
        targets.load_baseline(wired.runs_dir, sha, estimator.DEFAULT_SEED)


def test_load_baseline_rejects_a_split_hash_mismatch(wired: _Wired) -> None:
    _fit_baseline(wired)
    with pytest.raises(targets.BaselineRecordInvalid):
        targets.load_baseline(wired.runs_dir, "not-the-frozen-hash", estimator.DEFAULT_SEED)


def test_t2_baseline_is_out_of_fold_not_full_data_refit(wired: _Wired) -> None:
    # The load-bearing guard: the baseline is T0_R0's stored out-of-fold vector,
    # AND that vector differs from the full-data booster's in-sample predictions --
    # otherwise "is the OOF vector" would be satisfied by a model that leaked.
    a0 = _fit_baseline(wired)
    baseline = targets.load_baseline(wired.runs_dir, _split_sha(wired), estimator.DEFAULT_SEED)
    oof = baseline.aligned(a0.obs_ids)

    stored = pq.read_table(wired.runs_dir / "T0_R0_predictions.parquet")
    by_obs = dict(
        zip(
            stored.column("obs_id").to_pylist(),
            stored.column("prediction").to_pylist(),
            strict=True,
        )
    )
    assert np.array_equal(oof, np.asarray([by_obs[o] for o in a0.obs_ids], dtype=np.float64))

    xgb = estimator._import_xgboost()
    booster = xgb.Booster()
    booster.load_model(str(baseline.model_path))
    insample = np.asarray(booster.predict(xgb.DMatrix(a0.features)), dtype=np.float64)
    assert oof.shape == insample.shape
    # The full-data refit saw every row it now predicts; the OOF vector did not.
    assert not np.allclose(oof, insample)


def test_t2_fits_the_learned_residual_under_regression(
    wired: _Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    a0 = _fit_baseline(wired)
    baseline = targets.load_baseline(wired.runs_dir, _split_sha(wired), estimator.DEFAULT_SEED)
    bvec = baseline.aligned(a0.obs_ids)

    captured: dict[str, object] = {}
    real = estimator.fit_and_predict

    def spy(*args: object, **kw: object) -> object:
        captured["values"] = args[1]
        captured["kw"] = kw
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(estimator, "fit_and_predict", spy)
    run = targets.fit_representation(
        a0, wired.sources, wired.runs_dir, target=targets.TARGET_T2, baseline=bvec
    )
    kw = captured["kw"]
    assert isinstance(kw, dict)
    assert kw["objective"] == estimator.REGRESSION
    assert kw["target"] == targets.TARGET_T2
    # The target actually handed to the estimator is won - m_hat_-i, not the raw
    # outcome and not won - base_p.
    assert np.allclose(np.asarray(captured["values"]), a0.outcome - bvec)
    assert not np.allclose(np.asarray(captured["values"]), a0.outcome - a0.base_p)
    assert run.run_record["model_id"] == "T2_R0"
    assert run.run_record["objective"] == "regression"
    assert run.run_record["n_features"] == 1
    # The regression prediction is a bump, not a probability: it takes both signs.
    assert bool((run.predictions < 0.0).any())


def test_t2_requires_a_baseline() -> None:
    # Without a baseline vector, T2 cannot form its residual and must refuse.
    dummy = targets.Assembled(
        representation=targets.R0,
        obs_ids=["a"],
        groups=["g"],
        outcome=np.zeros(1),
        base_p=np.zeros(1),
        features=np.zeros((1, 1)),
        feature_names=[targets.BASE_P_COL],
    )
    with pytest.raises(targets.TargetUnknown):
        targets._target_and_objective(targets.TARGET_T2, dummy, None)


def test_build_t2_records_feature_counts_and_regression(wired: _Wired) -> None:
    _fit_baseline(wired)
    result = targets.build_t2(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t2_path,
    )
    assert result.r0.record["n_features"] == 1
    assert result.r0.record["objective"] == "regression"
    assert result.r0.record["target"] == "T2"
    assert result.r1 is not None
    assert result.r1.record["n_features"] == 1 + _N_CARDS
    assert result.r1.record["objective"] == "regression"


def test_t2_reconstruction_uses_the_baseline_not_base_p(wired: _Wired) -> None:
    a0 = _fit_baseline(wired)
    baseline = targets.load_baseline(wired.runs_dir, _split_sha(wired), estimator.DEFAULT_SEED)
    targets._fit_t2_model(a0, baseline, wired.sources, wired.runs_dir)
    recon_path = wired.runs_dir / "T2_R0_reconstruction.parquet"
    assert recon_path.exists()
    tbl = pq.read_table(recon_path)
    # The base column is the learned baseline, explicitly not mislabelled base_p.
    assert targets.BASELINE_COL in tbl.column_names
    assert targets.BASE_P_COL not in tbl.column_names
    base = np.asarray(tbl.column(targets.BASELINE_COL).to_numpy(zero_copy_only=False))
    oof = baseline.aligned(a0.obs_ids)
    assert np.allclose(base, oof)
    # m_hat_-i is a learned function of base_p, not base_p itself.
    assert not np.allclose(base, a0.base_p)
    bump = np.asarray(tbl.column(targets.BUMP_COL).to_numpy(zero_copy_only=False))
    raw = np.asarray(tbl.column(targets.RECON_RAW_COL).to_numpy(zero_copy_only=False))
    prob = np.asarray(tbl.column(targets.RECON_PROB_COL).to_numpy(zero_copy_only=False))
    assert np.allclose(raw, base + bump)
    clip = evaluation.PROBABILITY_CLIP
    assert np.allclose(prob, np.clip(raw, clip, 1.0 - clip))
    ids = set(tbl.column("obs_id").to_pylist())
    assert ids == wired.dev_obs_ids
    assert ids.isdisjoint(wired.holdout_ids)


def test_t2_clip_counts_match_the_raw_reconstruction(wired: _Wired) -> None:
    a0 = _fit_baseline(wired)
    baseline = targets.load_baseline(wired.runs_dir, _split_sha(wired), estimator.DEFAULT_SEED)
    result = targets._fit_t2_model(a0, baseline, wired.sources, wired.runs_dir)
    tbl = pq.read_table(wired.runs_dir / "T2_R0_reconstruction.parquet")
    raw = np.asarray(tbl.column(targets.RECON_RAW_COL).to_numpy(zero_copy_only=False))
    clip = evaluation.PROBABILITY_CLIP
    stats = result.recon_stats
    assert stats.n_clipped_low == int(np.count_nonzero(raw < clip))
    assert stats.n_clipped_high == int(np.count_nonzero(raw > 1.0 - clip))
    assert stats.n_clipped == stats.n_clipped_low + stats.n_clipped_high
    assert stats.n_rows == len(a0.obs_ids)


def test_t2_scores_both_the_continuous_and_the_bernoulli_views(wired: _Wired) -> None:
    a0 = _fit_baseline(wired)
    baseline = targets.load_baseline(wired.runs_dir, _split_sha(wired), estimator.DEFAULT_SEED)
    result = targets._fit_t2_model(a0, baseline, wired.sources, wired.runs_dir)
    assert "r2" in result.continuous_metrics
    assert "log_loss" not in result.continuous_metrics
    assert "r2" not in result.reconstructed_metrics
    assert "brier_skill_score" in result.reconstructed_metrics
    for key in ("log_loss", "brier", "rmse", "mae", "auc", "cal_intercept", "cal_slope"):
        assert key in result.reconstructed_metrics


def test_t2_r0_bump_stats_are_recorded(wired: _Wired) -> None:
    # The cross-fitting diagnostic: T2_R0's B_hat should sit near zero. The stats
    # the report reads are captured from the actual predictions.
    a0 = _fit_baseline(wired)
    baseline = targets.load_baseline(wired.runs_dir, _split_sha(wired), estimator.DEFAULT_SEED)
    result = targets._fit_t2_model(a0, baseline, wired.sources, wired.runs_dir)
    tbl = pq.read_table(wired.runs_dir / "T2_R0_reconstruction.parquet")
    stored_bump = np.asarray(tbl.column(targets.BUMP_COL).to_numpy(zero_copy_only=False))
    assert result.bump_mean == pytest.approx(float(np.mean(stored_bump)))
    assert result.bump_min <= result.bump_mean <= result.bump_max
    assert result.bump_std >= 0.0


def test_refitting_t2_r0_is_byte_identical(wired: _Wired) -> None:
    a0 = _fit_baseline(wired)
    baseline = targets.load_baseline(wired.runs_dir, _split_sha(wired), estimator.DEFAULT_SEED)
    bvec = baseline.aligned(a0.obs_ids)
    first = targets.fit_representation(
        a0, wired.sources, wired.runs_dir, target=targets.TARGET_T2, baseline=bvec
    )
    before = first.predictions_path.read_bytes()
    second = targets.fit_representation(
        a0, wired.sources, wired.runs_dir, target=targets.TARGET_T2, baseline=bvec
    )
    assert np.array_equal(first.predictions, second.predictions)
    assert second.predictions_path.read_bytes() == before


def test_build_t2_fits_r0_before_r1(wired: _Wired, monkeypatch: pytest.MonkeyPatch) -> None:
    _fit_baseline(wired)
    order: list[str] = []
    real = estimator.fit_and_predict

    def spy(*args: object, **kw: object) -> object:
        order.append(str(kw["representation"]))
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(estimator, "fit_and_predict", spy)
    targets.build_t2(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t2_path,
    )
    assert order == [targets.R0, targets.R1]


def test_t2_over_budget_stops_after_r0(wired: _Wired) -> None:
    _fit_baseline(wired)
    result = targets.build_t2(
        wired.sources,
        wired.runs_dir,
        budget_seconds=0.0,
        report_path=wired.report_t2_path,
    )
    assert result.r1_attempted is False
    assert result.r1 is None
    assert result.r1_skip_reason is not None
    assert (wired.runs_dir / "T2_R0_run.json").exists()
    assert not (wired.runs_dir / "T2_R1_run.json").exists()
    text = wired.report_t2_path.read_text(encoding="utf-8")
    assert "not attempted" in text
    assert f"{result.probe.projected_seconds:.0f}s" in text


def test_build_t2_leaves_the_holdout_ledger_byte_identical(wired: _Wired) -> None:
    _fit_baseline(wired)
    wired.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    wired.ledger_path.write_bytes(b"")  # the frozen state: zero reads
    before = wired.ledger_path.read_bytes()
    targets.build_t2(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t2_path,
    )
    assert wired.ledger_path.read_bytes() == before


def test_build_t2_report_records_the_consumed_baseline(wired: _Wired) -> None:
    _fit_baseline(wired)
    targets.build_t2(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_t2_path,
    )
    text = wired.report_t2_path.read_text(encoding="utf-8")
    # The report names the baseline artifact by path and by T0_R0's hyperparameters.
    assert "T0_R0_predictions.parquet" in text
    assert "chosen hyperparameters" in text
    # And states development uses the out-of-fold baseline, holdout the full-data one.
    assert "out-of-fold" in text
    assert "card 017" in text


# --------------------------------------------------------------------------
# Real frozen dataset: the two feature-count facts the card asserts, and the
# tracked run records the actual fit produced. No fitting happens here.
# --------------------------------------------------------------------------


@requires_real
def test_real_r0_has_one_feature_and_r1_has_194() -> None:
    a0 = targets.assemble(targets.R0)
    a1 = targets.assemble(targets.R1)
    assert a0.features.shape[1] == 1
    assert a0.feature_names == [targets.BASE_P_COL]
    assert a1.features.shape[1] == 194
    assert a1.feature_names[0] == targets.BASE_P_COL
    assert len(a1.feature_names) == 194
    # Every development row appears in both, with no holdout row.
    assert a0.obs_ids == a1.obs_ids
    holdout = targets._holdout_obs_ids(_REAL.split_parquet)
    assert set(a0.obs_ids).isdisjoint(holdout)


@requires_real
def test_real_run_records_are_present_and_consistent() -> None:
    r0_path = targets.RUNS_DIR / "T0_R0_run.json"
    if not r0_path.exists():
        pytest.skip("run records not produced yet (run `python -m deckbench.targets --fit`)")
    r0 = json.loads(r0_path.read_text(encoding="utf-8"))
    assert r0["n_features"] == 1
    assert r0["target"] == "T0"
    assert r0["representation"] == "R0"
    expected_sha = estimator.verify_split_hash(_REAL.split_parquet, _REAL.split_manifest)
    assert r0["split_sha256"] == expected_sha
    r1_path = targets.RUNS_DIR / "T0_R1_run.json"
    if r1_path.exists():
        r1 = json.loads(r1_path.read_text(encoding="utf-8"))
        assert r1["n_features"] == 194
        assert r1["representation"] == "R1"


@requires_real
def test_real_t1_run_records_are_present_and_consistent() -> None:
    r0_path = targets.RUNS_DIR / "T1_R0_run.json"
    if not r0_path.exists():
        pytest.skip("T1 run records not produced yet (run `python -m deckbench.targets --fit-t1`)")
    r0 = json.loads(r0_path.read_text(encoding="utf-8"))
    assert r0["n_features"] == 1
    assert r0["target"] == "T1"
    assert r0["representation"] == "R0"
    assert r0["objective"] == "regression"
    expected_sha = estimator.verify_split_hash(_REAL.split_parquet, _REAL.split_manifest)
    assert r0["split_sha256"] == expected_sha
    r1_path = targets.RUNS_DIR / "T1_R1_run.json"
    if r1_path.exists():
        r1 = json.loads(r1_path.read_text(encoding="utf-8"))
        assert r1["n_features"] == 194
        assert r1["representation"] == "R1"
        assert r1["objective"] == "regression"
