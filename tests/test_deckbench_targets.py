"""Tests for card 011's T0 R0/R1 fitting (:mod:`deckbench.targets`).

The real fits run on 194,215 development rows and take minutes, far beyond the
validation budget, so these tests never fit the real dataset. Two fixtures cover
the two things that need checking:

* a **synthetic** wiring (a small split + skill + identity + model table in a
  temp dir) drives assembly, the fit-through-the-estimator path, the timing
  probe, the panel, the budget decision, determinism, and ``verify`` end to end,
  fast; and
* a **real-artifact** group, run only when the frozen phase-1 parquets are on
  disk, pins the two facts about the real data the card asserts -- R0 has exactly
  one feature ``base_p`` and R1 has exactly 194 -- and checks the tracked run
  records the actual fit produced.

The load-bearing guards are that both fits go through the estimator (no learner
is built here), that no assembled or emitted row is a holdout row, and that the
holdout ledger is byte-identical across a build.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from deckbench import estimator, targets

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
# verify(): passes on a good build, fails on a tampered one.
# --------------------------------------------------------------------------


def test_verify_passes_on_a_good_build(wired: _Wired) -> None:
    wired.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    wired.ledger_path.write_bytes(b"")
    targets.build(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_path,
    )
    assert (
        targets.verify(wired.sources, wired.runs_dir, wired.report_path, wired.ledger_path) == 0
    )


def test_verify_fails_when_r0_is_missing(wired: _Wired) -> None:
    wired.runs_dir.mkdir(parents=True, exist_ok=True)
    wired.report_path.write_text("stub", encoding="utf-8")
    assert (
        targets.verify(wired.sources, wired.runs_dir, wired.report_path, wired.ledger_path) == 1
    )


def test_verify_fails_when_ledger_is_dirty(wired: _Wired) -> None:
    targets.build(
        wired.sources,
        wired.runs_dir,
        budget_seconds=targets.R1_FIT_BUDGET_SECONDS,
        report_path=wired.report_path,
    )
    wired.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    wired.ledger_path.write_text('{"card_id": "099"}\n', encoding="utf-8")
    assert (
        targets.verify(wired.sources, wired.runs_dir, wired.report_path, wired.ledger_path) == 1
    )


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
