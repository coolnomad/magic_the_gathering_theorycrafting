"""Tests for the single holdout read (:mod:`deckbench.final_read`, card 017).

The real read is irreversible and touches the sealed holdout, so these tests never
run it. A synthetic fixture wires a small split (development + holdout partitions)
with aligned skill/identity/model tables in a temp dir, fits all six models
through the real target/estimator path once, and then drives ``final_read`` against
those artifacts with an isolated ledger. The synthetic "holdout" is a real
partition of the synthetic split, opened through the same sealed reader with a
throwaway ledger -- so the once-only, ledger-before-rows machinery is exercised
without ever touching the project's real holdout.

The load-bearing guards:

* the rehearsal (development) and the real read call the **same** scoring
  function, not two parallel implementations;
* holdout features are assembled in the **same column order** the boosters were
  fitted with (xgboost matches positionally);
* T2 reconstructs with the **full-data** ``T0_R0.xgb`` baseline, never a
  synthesised out-of-fold vector;
* a bad run record stops the card **before** the seal;
* the read happens exactly once and leaves exactly one ledger line;
* the bootstrap is deterministic in its seed;
* ``--verify`` checks artifacts and the ledger without reading the holdout, and is
  non-vacuous -- removing an artifact makes it fail.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from deckbench import estimator, evaluation, final_read, targets

ROOT = Path(__file__).resolve().parent.parent

_N_DRAFTS = 60
_GAMES = 4
_HOLDOUT_DRAFTS = 12
_N_CARDS = 6


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Wired:
    """A synthetic split + aligned tables, with all six models fitted once."""

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
        self.split_sha = _sha256(self.split_parquet)
        self.split_manifest.write_text(
            json.dumps({"split_sha256": self.split_sha}) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        rng = np.random.default_rng(11)
        n = len(obs_ids)
        base_p = rng.uniform(0.4, 0.65, size=n)
        self.skill_parquet = processed / "skill_features.parquet"
        pq.write_table(
            pa.table(
                {
                    "obs_id": pa.array(obs_ids, type=pa.string()),
                    "base_p": pa.array(base_p, type=pa.float64()),
                }
            ),
            self.skill_parquet,
            compression="snappy",
        )

        cards = rng.dirichlet(np.ones(_N_CARDS), size=n)
        identity_cols: dict[str, object] = {"obs_id": pa.array(obs_ids, type=pa.string())}
        for j in range(_N_CARDS):
            identity_cols[f"card_c{j}"] = pa.array(cards[:, j], type=pa.float64())
        self.identity_parquet = processed / "deck_identity.parquet"
        pq.write_table(pa.table(identity_cols), self.identity_parquet, compression="snappy")

        signal = base_p - 0.5 + 0.3 * cards[:, 0] - 0.2 * cards[:, 1]
        won = (signal + rng.normal(scale=0.2, size=n) > 0).tolist()
        self.model_table = processed / "model_table.parquet"
        pq.write_table(
            pa.table(
                {
                    "obs_id": pa.array(obs_ids, type=pa.string()),
                    "won": pa.array([str(bool(w)) for w in won], type=pa.string()),
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
        self.ledger_path = tmp_path / "cycle" / "holdout_ledger.jsonl"
        self.report_path = tmp_path / "reports" / "holdout_read.md"

        # Fit all six models through the real target/estimator path, using a small
        # budget so R1 is always attempted on the tiny synthetic matrix.
        targets.build(self.sources, self.runs_dir, write_report_file=False)
        targets.build_t1(self.sources, self.runs_dir, write_report_file=False)
        targets.build_t2(self.sources, self.runs_dir, write_report_file=False)

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

    def run(self, **overrides: object) -> final_read.FinalReadResult:
        kwargs: dict[str, object] = dict(
            sources=self.sources,
            runs_dir=self.runs_dir,
            split_parquet=self.split_parquet,
            split_manifest=self.split_manifest,
            ledger_path=self.ledger_path,
            report_path=self.report_path,
            n_replicates=40,
            write_report_file=True,
        )
        kwargs.update(overrides)
        return final_read.run_final_read(**kwargs)  # type: ignore[arg-type]


@pytest.fixture
def wired(tmp_path: Path) -> _Wired:
    return _Wired(tmp_path)


# --------------------------------------------------------------------------
# Assembly and column order.
# --------------------------------------------------------------------------


def test_r0_assembly_is_base_p_only(wired: _Wired) -> None:
    order = sorted(wired.holdout_ids)
    a0 = final_read.assemble_features(order, final_read.R0, wired.sources)
    assert a0.features.shape == (len(order), 1)
    assert a0.feature_names == [targets.BASE_P_COL]


def test_r1_column_order_matches_the_fitted_order(wired: _Wired) -> None:
    # The holdout R1 assembly must have exactly the columns, in the order, the
    # fitted booster expects: base_p first, then every identity column in the
    # identity table's own order. This is the transposition guard.
    order = sorted(wired.holdout_ids)
    a1 = final_read.assemble_features(order, final_read.R1, wired.sources)
    expected = [targets.BASE_P_COL] + [f"card_c{j}" for j in range(_N_CARDS)]
    assert a1.feature_names == expected
    # And it agrees with the development assembly the models were fitted through.
    dev = targets.assemble(final_read.R1, wired.sources)
    assert a1.feature_names == dev.feature_names


def test_assembly_join_must_be_total(wired: _Wired) -> None:
    order = [*sorted(wired.holdout_ids), "obs_does_not_exist"]
    with pytest.raises(targets.JoinNotTotal):
        final_read.assemble_features(order, final_read.R1, wired.sources)


# --------------------------------------------------------------------------
# Run-record validation, all in front of the seal.
# --------------------------------------------------------------------------


def test_all_run_records_validate(wired: _Wired) -> None:
    records = final_read.validate_all_run_records(
        wired.runs_dir, wired.sources, wired.split_sha
    )
    assert set(records) == {s.model_id for s in final_read.MODEL_SPECS}


def test_bad_run_record_stops_before_the_read(wired: _Wired) -> None:
    # Corrupt T2_R1's recorded objective; validation must reject it, and no ledger
    # line may be written because the read never happens.
    record_path = wired.runs_dir / "T2_R1_run.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["objective"] = estimator.BINARY  # T2 is a regression model
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(final_read.RunRecordInvalid):
        wired.run()
    assert not wired.ledger_path.exists() or wired.ledger_path.stat().st_size == 0


def test_wrong_split_hash_stops_before_the_read(wired: _Wired) -> None:
    record_path = wired.runs_dir / "T0_R0_run.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["split_sha256"] = "0" * 64
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(final_read.RunRecordInvalid):
        wired.run()
    assert not wired.ledger_path.exists() or wired.ledger_path.stat().st_size == 0


# --------------------------------------------------------------------------
# The read happens once, through the shared scoring path.
# --------------------------------------------------------------------------


def test_single_read_leaves_exactly_one_ledger_line(wired: _Wired) -> None:
    result = wired.run()
    lines = [ln for ln in wired.ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["card_id"] == final_read.CARD_ID
    assert record["is_repeat"] is False
    # The report quotes the ledger line verbatim.
    assert result.ledger_line == lines[0]
    assert lines[0] in wired.report_path.read_text(encoding="utf-8")


def test_rehearsal_and_read_call_the_same_scoring_function(
    wired: _Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels: list[str] = []
    real = final_read.score_partition

    def spy(*args: object, **kw: object) -> object:
        labels.append(str(kw.get("partition_label")))
        return real(*args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(final_read, "score_partition", spy)
    wired.run()
    # Exactly one dev (rehearsal) and one holdout call, both through score_partition.
    assert labels == ["dev", "holdout"]


def test_scored_holdout_rows_are_exactly_the_holdout_partition(wired: _Wired) -> None:
    result = wired.run()
    assert set(result.holdout.obs_ids) == wired.holdout_ids


def test_t2_reconstruction_uses_the_full_data_t0r0_booster(
    wired: _Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The baseline m_hat(S) for T2 must be the full-data T0_R0.xgb applied to the
    # rows, not any out-of-fold vector. Assert the booster loaded for the baseline
    # id is exactly BASELINE_MODEL_ID, and that T2's reconstruction equals
    # m_hat + B_hat computed independently.
    loaded: list[str] = []
    real_load = final_read._load_booster

    def spy(xgb: object, model_id: str, runs_dir: Path) -> object:
        loaded.append(model_id)
        return real_load(xgb, model_id, runs_dir)  # type: ignore[arg-type]

    monkeypatch.setattr(final_read, "_load_booster", spy)
    result = wired.run()
    assert final_read.BASELINE_MODEL_ID in loaded

    # Recompute m_hat + B_hat for T2_R1 independently and compare to the artifact.
    import xgboost as xgb

    order = result.holdout.obs_ids
    a0 = final_read.assemble_features(order, final_read.R0, wired.sources)
    a1 = final_read.assemble_features(order, final_read.R1, wired.sources)
    base = xgb.Booster()
    base.load_model(str(wired.runs_dir / "T0_R0.xgb"))
    m_hat = np.asarray(base.predict(xgb.DMatrix(a0.features)), dtype=np.float64)
    t2 = xgb.Booster()
    t2.load_model(str(wired.runs_dir / "T2_R1.xgb"))
    b_hat = np.asarray(t2.predict(xgb.DMatrix(a1.features)), dtype=np.float64)
    raw = m_hat + b_hat
    np.testing.assert_allclose(result.holdout.raw_reconstructions["T2_R1"], raw)


def test_t0_probability_is_the_booster_output_directly(wired: _Wired) -> None:
    result = wired.run()
    import xgboost as xgb

    order = result.holdout.obs_ids
    a1 = final_read.assemble_features(order, final_read.R1, wired.sources)
    booster = xgb.Booster()
    booster.load_model(str(wired.runs_dir / "T0_R1.xgb"))
    direct = np.asarray(booster.predict(xgb.DMatrix(a1.features)), dtype=np.float64)
    np.testing.assert_allclose(result.holdout.probabilities["T0_R1"], direct)


def test_clip_counts_reported_for_t1_and_t2_only(wired: _Wired) -> None:
    result = wired.run()
    for model_id in ("T1_R0", "T1_R1", "T2_R0", "T2_R1"):
        assert model_id in result.holdout.clip_stats
    for model_id in ("T0_R0", "T0_R1"):
        assert model_id not in result.holdout.clip_stats


# --------------------------------------------------------------------------
# Bootstrap, increments, difference of increments.
# --------------------------------------------------------------------------


def test_bootstrap_is_deterministic_on_development_rows(wired: _Wired) -> None:
    # Determinism asserted on the DEVELOPMENT partition, never the holdout: score
    # dev through the shared path (no ledger, no seal) and bootstrap twice.
    from deckbench.holdout import load_dev

    dev = load_dev(wired.split_parquet)
    scored = final_read.score_partition(
        dev, wired.sources, wired.runs_dir, partition_label="dev"
    )
    first = final_read.bootstrap_panel(scored, n_replicates=50)
    second = final_read.bootstrap_panel(scored, n_replicates=50)
    a, b = final_read.WITHIN_TARGET_INCREMENTS[0]
    key = evaluation._comparison_key(a, b)
    for metric in final_read.BOOTSTRAP_METRICS:
        assert first.differences[key][metric].lo == second.differences[key][metric].lo
        assert first.differences[key][metric].hi == second.differences[key][metric].hi


def test_difference_of_increments_is_paired_on_shared_indices(wired: _Wired) -> None:
    result = wired.run()
    # Every DiD pair and each of the three DiD metrics is present, and the point is
    # exactly increment(a) - increment(b) recomputed from the level differences.
    metrics = {evaluation.BRIER_SKILL_SCORE, evaluation.LOG_LOSS, evaluation.BRIER}
    seen_pairs = {(d.target_a, d.target_b) for d in result.did}
    assert seen_pairs == set(final_read.DID_PAIRS)
    assert {d.metric for d in result.did} == metrics

    boot = result.bootstrap
    for did in result.did:
        inc_a = boot.differences[
            evaluation._comparison_key(f"{did.target_a}_R1", f"{did.target_a}_R0")
        ][did.metric].point
        inc_b = boot.differences[
            evaluation._comparison_key(f"{did.target_b}_R1", f"{did.target_b}_R0")
        ][did.metric].point
        assert did.interval.point == pytest.approx(inc_a - inc_b)


def test_within_target_increments_present_in_bootstrap(wired: _Wired) -> None:
    result = wired.run()
    for a, b in final_read.WITHIN_TARGET_INCREMENTS:
        key = evaluation._comparison_key(a, b)
        assert key in result.bootstrap.differences
    for a, b in final_read.CROSS_TARGET_R1:
        key = evaluation._comparison_key(a, b)
        assert key in result.bootstrap.differences


# --------------------------------------------------------------------------
# Artifacts and --verify.
# --------------------------------------------------------------------------


def test_artifacts_written_keyed_by_obs_id(wired: _Wired) -> None:
    result = wired.run()
    assert len(result.artifacts) == len(final_read.MODEL_SPECS)
    for spec in final_read.MODEL_SPECS:
        path = wired.runs_dir / f"{spec.model_id}_holdout_predictions.parquet"
        assert path.exists()
        table = pq.read_table(path)
        assert final_read.OBS_ID_COL in table.column_names
        assert final_read.PROB_ART_COL in table.column_names
        assert set(table.column(final_read.OBS_ID_COL).to_pylist()) == wired.holdout_ids


def test_verify_passes_after_the_read(wired: _Wired) -> None:
    wired.run()
    code = final_read.verify(
        runs_dir=wired.runs_dir,
        ledger_path=wired.ledger_path,
        report_path=wired.report_path,
    )
    assert code == 0


def test_verify_is_non_vacuous_when_an_artifact_is_removed(wired: _Wired) -> None:
    wired.run()
    (wired.runs_dir / "T2_R1_holdout_predictions.parquet").unlink()
    code = final_read.verify(
        runs_dir=wired.runs_dir,
        ledger_path=wired.ledger_path,
        report_path=wired.report_path,
    )
    assert code == 1


def test_verify_fails_when_ledger_has_more_than_one_line(wired: _Wired) -> None:
    wired.run()
    with wired.ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"card_id": "999"}) + "\n")
    code = final_read.verify(
        runs_dir=wired.runs_dir,
        ledger_path=wired.ledger_path,
        report_path=wired.report_path,
    )
    assert code == 1


def test_verify_does_not_read_the_holdout(
    wired: _Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.run()
    # If --verify opened the seal, this would raise; it must not be called at all.
    import deckbench.holdout as holdout_mod

    def boom(*args: object, **kw: object) -> object:
        raise AssertionError("verify must not open the holdout")

    monkeypatch.setattr(holdout_mod, "load_holdout", boom)
    monkeypatch.setattr(final_read, "load_holdout", boom)
    code = final_read.verify(
        runs_dir=wired.runs_dir,
        ledger_path=wired.ledger_path,
        report_path=wired.report_path,
    )
    assert code == 0


# --------------------------------------------------------------------------
# The report.
# --------------------------------------------------------------------------


def test_report_carries_section_13_and_no_bare_r2(wired: _Wired) -> None:
    wired.run()
    text = wired.report_path.read_text(encoding="utf-8")
    # Section 13's two sentences, distinguished.
    assert "Deck composition does not affect win probability." in text
    assert "little detectable incremental predictive information beyond skill" in text
    # The listed alternative explanations, stated not gestured at.
    assert "deck effects are interaction-dependent" in text
    assert "card identity is an inefficient representation" in text
    # base_p and m_hat are not described as skill.
    assert "`base_p` is not skill" in text
    # The master table reports a brier skill score, not an unlabelled r2 column.
    assert evaluation.BRIER_SKILL_SCORE in text
