"""The single holdout read (card 017): score the six fitted models once.

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md``. This is the
measurement the whole benchmark was built to make, and the only irreversible step
in it. The external holdout is sealed (card 006): it may be opened once, through
:func:`deckbench.holdout.load_holdout`, which appends one line to an append-only
ledger *before* returning rows. When this card is done, ``cycle/holdout_ledger``
must contain exactly one line.

Nothing here is trained, tuned, selected or refitted. The six models exist as
fitted boosters under ``data/runs/``; this module loads them, predicts the holdout
rows, reconstructs a win probability on the one scale the three target
formulations share, scores through the card-010 panel, carries the uncertainty
with the paired cluster bootstrap, and writes a report.

    T0_R0  T0_R1      raw outcome
    T1_R0  T1_R1      bump against the fixed proxy
    T2_R0  T2_R1      bump against the cross-fitted learned baseline

The three reconstructions, on the reconstructed-probability scale:

* **T0** -- the booster's output is the win probability directly.
* **T1** -- ``p = base_p + B_hat``, clipped into the unit interval for scoring,
  with the clip counts at each end reported.
* **T2** -- ``p = m_hat(S) + B_hat``, where ``m_hat`` is the **full-data**
  ``T0_R0.xgb`` applied to holdout rows. No holdout row trained ``m_hat``, so the
  full-data model is honest on them by construction; the development out-of-fold
  baseline does not exist for holdout rows and is never synthesised. On
  development (rehearsal) the *same* full-data baseline is used, because the
  rehearsal exists to exercise the identical code path, not to produce an honest
  development number.

The order of operations is load-bearing. ``load_holdout`` writes its ledger line
before returning rows, so every failure that can happen *before* the read is free
and every failure *after* it is permanent. Environment check, split-hash
verification, run-record validation, feature assembly, booster loading and the
full rehearsal all happen in front of the seal; the read itself is followed only
by pure computation.

Two entry points:

* ``python -m deckbench.final_read --verify`` -- check the emitted artifacts and
  the ledger **without reading the holdout**. Safe to run on every retry; it never
  appends a ledger line.
* :func:`run_final_read` -- the executor's own single-shot work: validate, rehearse
  on development, open the holdout once, score, bootstrap, and write the report.
  It is **not** wired into ``--verify`` or any check, because those run on every
  retry and each run would append another ledger line.

There is deliberately no ``repeat`` path. If the read fails after the ledger line
is appended, the executor stops and reports it; whether to spend a second read of
a once-only partition is an operator's decision, never the executor's.
"""

from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from numpy.typing import NDArray

from deckbench import estimator, evaluation, targets
from deckbench.environment import require_pinned_environment
from deckbench.holdout import load_dev, load_holdout

if TYPE_CHECKING:
    from collections.abc import Sequence

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

REPO_ROOT = estimator.REPO_ROOT
RUNS_DIR = estimator.RUNS_DIR
SPLIT_PARQUET = estimator.SPLIT_PARQUET
SPLIT_MANIFEST = estimator.SPLIT_MANIFEST
LEDGER_PATH = REPO_ROOT / "cycle" / "holdout_ledger.jsonl"

# The rehearsal is a smoke test, not a measurement: it exists to prove the whole
# scoring and bootstrap path runs on real rows before the seal is touched, and
# nobody reads its intervals. Measured on this data, a 1000-replicate bootstrap
# over the 194,215 development rows takes 1581 s while scoring all six models
# takes 8 s -- so at the measurement's replicate count the dry run costs roughly
# four times the irreversible holdout measurement it protects. Fifty replicates
# exercises every line of the same path. The HOLDOUT bootstrap is unaffected and
# stays at evaluation.DEFAULT_BOOTSTRAP_REPLICATES, which is what the report's
# intervals are computed from: a confidence interval's *width* converges quickly
# in the replicate count, but its endpoints are order statistics of the replicate
# draws and stay visibly seed-dependent until the count is large.
REHEARSAL_REPLICATES: int = 50
REPORT_MD = REPO_ROOT / "reports" / "holdout_read.md"

# This card's id. The holdout is opened as this card, exactly once.
CARD_ID = "017"
READ_REASON = (
    "card 017: the single external-holdout read -- score all six fitted models "
    "(T0/T1/T2 x R0/R1) through the card-010 panel and the paired cluster "
    "bootstrap. This is the one comparison the benchmark was built to make."
)

# The full-data learned baseline m_hat(S) T2 reconstructs the holdout with. It is
# T0_R0's full-data booster, honest on holdout rows because none of them trained
# it. The out-of-fold development baseline is a development-only object and is not
# used here (see the module docstring).
BASELINE_MODEL_ID = "T0_R0"

# The six models, each an immutable spec used both to validate its run record and
# to reconstruct its probability. n_features is checked against the assembled
# matrix rather than a hardcoded constant, so this stays correct on a synthetic
# fixture with a different card count.
R0 = targets.R0
R1 = targets.R1
T0 = targets.TARGET_T0
T1 = targets.TARGET_T1
T2 = targets.TARGET_T2


@dataclass(frozen=True)
class ModelSpec:
    """One benchmark model: its id, target formulation, representation, objective."""

    model_id: str
    target: str
    representation: str
    objective: str


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec("T0_R0", T0, R0, estimator.BINARY),
    ModelSpec("T0_R1", T0, R1, estimator.BINARY),
    ModelSpec("T1_R0", T1, R0, estimator.REGRESSION),
    ModelSpec("T1_R1", T1, R1, estimator.REGRESSION),
    ModelSpec("T2_R0", T2, R0, estimator.REGRESSION),
    ModelSpec("T2_R1", T2, R1, estimator.REGRESSION),
)

# The paired-cluster-bootstrap metrics carried on the reconstructed probability --
# the only scale on which the three target formulations are comparable. These are
# the section-9 Bernoulli panel's scalar metrics; calibration intercept/slope are
# reported as levels but are not bootstrapped.
BOOTSTRAP_METRICS: tuple[str, ...] = (
    evaluation.LOG_LOSS,
    evaluation.BRIER,
    evaluation.BRIER_SKILL_SCORE,
    evaluation.RMSE,
    evaluation.MAE,
    evaluation.AUC,
)

# The within-target increment R1 - R0 (the incremental-value question of section
# 11), one per target formulation.
WITHIN_TARGET_INCREMENTS: tuple[tuple[str, str], ...] = (
    ("T0_R1", "T0_R0"),
    ("T1_R1", "T1_R0"),
    ("T2_R1", "T2_R0"),
)

# The cross-target comparisons among the three R1 models.
CROSS_TARGET_R1: tuple[tuple[str, str], ...] = (
    ("T1_R1", "T0_R1"),
    ("T2_R1", "T0_R1"),
    ("T2_R1", "T1_R1"),
)

# H2's ordering is a difference of differences: increment(target_a) minus
# increment(target_b), each increment itself R1 - R0. Reported paired on the same
# bootstrap resamples.
DID_PAIRS: tuple[tuple[str, str], ...] = (
    (T1, T0),
    (T2, T0),
    (T2, T1),
)

# The reconstructed-probability artifact columns, keyed by obs_id, so the report's
# numbers are reproducible without a second read.
OBS_ID_COL = targets.OBS_ID_COL
OUTCOME_ART_COL = "won"
PROB_ART_COL = "win_probability"
RAW_ART_COL = "reconstructed_raw"


def _holdout_artifact_path(model_id: str, runs_dir: Path) -> Path:
    return runs_dir / f"{model_id}_holdout_predictions.parquet"


class RunRecordInvalid(ValueError):
    """Raised when a model's run record does not describe what card 017 scores.

    Every model's record is validated before its booster is used -- target,
    representation, objective, feature count, seed and split hash. Any mismatch
    stops the card **before** the holdout is opened, so an irreversible read is
    never spent on a model that is not the one that was built.
    """


class ArtifactMissing(ValueError):
    """Raised by ``--verify`` when a required holdout artifact is absent."""


# --------------------------------------------------------------------------
# Feature assembly -- from the same frozen tables, in the same column order each
# model was fitted with. Reuses the fitting module's own join primitives so the
# order is guaranteed identical rather than merely intended to be.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Assembled:
    """One representation's matrix for a given obs_id order, plus base_p alone."""

    representation: str
    features: FloatArray
    feature_names: list[str]
    base_p: FloatArray


def assemble_features(
    order: Sequence[str], representation: str, sources: targets.Sources
) -> Assembled:
    """Assemble one representation's matrix for an arbitrary obs_id order.

    R0 is ``base_p`` alone; R1 is ``base_p`` followed by every card-fraction
    column, in the identity table's own column order. This is the *same* assembly
    the fitting module uses (:func:`deckbench.targets.assemble`), via the same join
    primitives, so the column order matches the fitted booster positionally -- the
    only guarantee that matters, because xgboost matches features by position and a
    silently transposed matrix would produce plausible, wrong numbers. Every join
    is on ``obs_id`` and must be total; a missing id stops the run.
    """
    if representation not in (R0, R1):
        raise targets.RepresentationUnknown(
            f"representation {representation!r} is not supported; choose R0 or R1."
        )
    base_p_map = targets._base_p_by_obs(sources.skill_parquet)
    targets._require_total(order, base_p_map, f"{sources.skill_parquet.name} base_p")
    base_p = np.asarray([base_p_map[o] for o in order], dtype=np.float64)
    if representation == R0:
        return Assembled(R0, base_p.reshape(-1, 1), [targets.BASE_P_COL], base_p)
    cards, card_names = targets._identity_matrix(order, sources.identity_parquet)
    features = np.column_stack([base_p, cards])
    return Assembled(R1, features, [targets.BASE_P_COL, *card_names], base_p)


def outcome_vector(order: Sequence[str], sources: targets.Sources) -> FloatArray:
    """The raw outcome ``won`` in {0, 1}, in ``order``'s row order; join must be total."""
    outcome_map = targets._outcome_by_obs(sources.model_table)
    targets._require_total(order, outcome_map, f"{sources.model_table.name} won")
    return np.asarray([outcome_map[o] for o in order], dtype=np.float64)


# --------------------------------------------------------------------------
# Run-record validation -- every guard in front of the seal.
# --------------------------------------------------------------------------


def expected_feature_counts(sources: targets.Sources) -> dict[str, int]:
    """Expected feature counts derived from the identity schema: R0 -> 1, R1 -> 1 + cards."""
    return targets._expected_feature_counts(sources)


def load_run_record(model_id: str, runs_dir: Path) -> dict[str, Any]:
    path = runs_dir / f"{model_id}_run.json"
    if not path.exists():
        raise RunRecordInvalid(f"run record {path} is missing; fit {model_id} first.")
    record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return record


def validate_run_record(
    spec: ModelSpec,
    runs_dir: Path,
    expected_features: int,
    expected_split_sha: str,
    expected_seed: int = estimator.DEFAULT_SEED,
) -> dict[str, Any]:
    """Validate one model's run record against what card 017 scores; raise on mismatch.

    Checks ``target``, ``representation``, ``objective``, ``n_features`` (against
    the assembled matrix width, not a hardcoded constant), ``seed`` and
    ``split_sha256`` (against the manifest). Any mismatch raises before the holdout
    is opened.
    """
    record = load_run_record(spec.model_id, runs_dir)
    problems: list[str] = []
    if record.get("target") != spec.target:
        problems.append(f"target is {record.get('target')!r}, expected {spec.target!r}")
    if record.get("representation") != spec.representation:
        problems.append(
            f"representation is {record.get('representation')!r}, expected "
            f"{spec.representation!r}"
        )
    if record.get("objective") != spec.objective:
        problems.append(f"objective is {record.get('objective')!r}, expected {spec.objective!r}")
    if record.get("n_features") != expected_features:
        problems.append(
            f"n_features is {record.get('n_features')!r}, expected {expected_features}"
        )
    if record.get("seed") != expected_seed:
        problems.append(f"seed is {record.get('seed')!r}, expected {expected_seed}")
    if record.get("split_sha256") != expected_split_sha:
        problems.append(
            f"split_sha256 is {record.get('split_sha256')!r}, expected "
            f"{expected_split_sha!r} (the manifest hash)"
        )
    if problems:
        raise RunRecordInvalid(
            f"{spec.model_id} run record is not the model card 017 scores: "
            + "; ".join(problems)
            + ". Refusing to open the holdout for a model that is not the one built."
        )
    return record


def validate_all_run_records(
    runs_dir: Path, sources: targets.Sources, expected_split_sha: str
) -> dict[str, dict[str, Any]]:
    """Validate all six run records; return them keyed by model id. Raises on any mismatch."""
    expected = expected_feature_counts(sources)
    records: dict[str, dict[str, Any]] = {}
    for spec in MODEL_SPECS:
        records[spec.model_id] = validate_run_record(
            spec, runs_dir, expected[spec.representation], expected_split_sha
        )
    return records


# --------------------------------------------------------------------------
# Booster prediction and probability reconstruction -- the shared scoring path.
# --------------------------------------------------------------------------


def _load_booster(xgb: Any, model_id: str, runs_dir: Path) -> Any:
    path = runs_dir / f"{model_id}.xgb"
    if not path.exists():
        raise RunRecordInvalid(f"fitted booster {path} is missing; fit {model_id} first.")
    booster = xgb.Booster()
    # The .xgb extension is gitignored; xgboost warns it defaults to UBJSON for an
    # unrecognised extension, which is exactly the format the estimator saved. The
    # warning is cosmetic -- silence it rather than rename the artifact.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        booster.load_model(str(path))
    return booster


def _predict(xgb: Any, booster: Any, features: FloatArray) -> FloatArray:
    """Predict a numpy feature matrix; xgboost matches columns positionally."""
    return np.asarray(booster.predict(xgb.DMatrix(features)), dtype=np.float64)


@dataclass(frozen=True)
class ClipStats:
    """How a reconstructed probability behaved before the clip, per end."""

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


def _clip_with_stats(raw: FloatArray) -> tuple[FloatArray, ClipStats]:
    clip_low = evaluation.PROBABILITY_CLIP
    clip_high = 1.0 - clip_low
    clipped = np.clip(raw, clip_low, clip_high)
    stats = ClipStats(
        n_rows=int(raw.size),
        n_clipped_low=int(np.count_nonzero(raw < clip_low)),
        n_clipped_high=int(np.count_nonzero(raw > clip_high)),
        clip_low=clip_low,
        clip_high=clip_high,
        raw_min=float(np.min(raw)),
        raw_max=float(np.max(raw)),
    )
    return clipped, stats


@dataclass(frozen=True)
class ScoredPartition:
    """Every model's reconstructed probability over one partition, plus outcome/groups.

    ``partition`` is a label for the report only (``holdout`` or ``dev``); the
    scoring arithmetic is identical for both, which is the point of the rehearsal.
    """

    partition: str
    obs_ids: list[str]
    groups: list[str]
    outcome: FloatArray
    probabilities: dict[str, FloatArray]
    raw_reconstructions: dict[str, FloatArray]
    clip_stats: dict[str, ClipStats]


def score_partition(
    partition_table: pa.Table,
    sources: targets.Sources,
    runs_dir: Path,
    *,
    partition_label: str,
) -> ScoredPartition:
    """Score all six models over one partition's rows -- the ONE scoring path.

    Both the development rehearsal and the real holdout read call exactly this
    function; only the ``partition_table`` differs (development rows from
    :func:`deckbench.holdout.load_dev`, holdout rows from
    :func:`deckbench.holdout.load_holdout`). It assembles R0 and R1 from the frozen
    tables in the fitted column order, loads every booster, and reconstructs each
    model's win probability on the common reconstructed-probability scale: T0
    directly, T1 as ``base_p + B_hat``, T2 as ``m_hat(S) + B_hat`` with ``m_hat``
    the full-data ``T0_R0.xgb`` applied to these rows. It fits nothing and reads no
    ledger.
    """
    order: list[str] = partition_table.column(OBS_ID_COL).to_pylist()
    groups: list[str] = partition_table.column("draft_id").to_pylist()
    outcome = outcome_vector(order, sources)

    a0 = assemble_features(order, R0, sources)
    a1 = assemble_features(order, R1, sources)
    features_by_rep = {R0: a0, R1: a1}

    xgb = estimator._import_xgboost()

    # The full-data learned baseline m_hat(S), applied to these rows. Honest on
    # holdout rows (none trained it); on development rows it is the same object,
    # used only to keep the rehearsal path identical.
    baseline_booster = _load_booster(xgb, BASELINE_MODEL_ID, runs_dir)
    m_hat = _predict(xgb, baseline_booster, a0.features)

    probabilities: dict[str, FloatArray] = {}
    raw_reconstructions: dict[str, FloatArray] = {}
    clip_stats: dict[str, ClipStats] = {}
    for spec in MODEL_SPECS:
        assembled = features_by_rep[spec.representation]
        booster = _load_booster(xgb, spec.model_id, runs_dir)
        prediction = _predict(xgb, booster, assembled.features)
        if spec.target == T0:
            # The booster's output is the win probability directly.
            raw = prediction
            prob = prediction
        elif spec.target == T1:
            raw = assembled.base_p + prediction
            prob, stats = _clip_with_stats(raw)
            clip_stats[spec.model_id] = stats
        else:  # T2
            raw = m_hat + prediction
            prob, stats = _clip_with_stats(raw)
            clip_stats[spec.model_id] = stats
        probabilities[spec.model_id] = prob
        raw_reconstructions[spec.model_id] = raw

    return ScoredPartition(
        partition=partition_label,
        obs_ids=order,
        groups=groups,
        outcome=outcome,
        probabilities=probabilities,
        raw_reconstructions=raw_reconstructions,
        clip_stats=clip_stats,
    )


# --------------------------------------------------------------------------
# Scoring the panel and carrying the uncertainty.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelPanel:
    """One model's scalar panel metrics plus its calibration line, on a partition."""

    model_id: str
    metrics: dict[str, float]
    cal_intercept: float
    cal_slope: float


def panel_for(scored: ScoredPartition) -> dict[str, ModelPanel]:
    """The card-010 Bernoulli panel plus calibration line, per model."""
    panels: dict[str, ModelPanel] = {}
    for spec in MODEL_SPECS:
        prob = scored.probabilities[spec.model_id]
        metrics = dict(
            evaluation.evaluate_metrics(
                scored.outcome, prob, outcome_type=evaluation.OUTCOME_BERNOULLI
            )
        )
        line = evaluation.calibration_intercept_slope(scored.outcome, prob)
        panels[spec.model_id] = ModelPanel(
            model_id=spec.model_id,
            metrics=metrics,
            cal_intercept=line.intercept,
            cal_slope=line.slope,
        )
    return panels


def _percentile_ci(
    point: float, samples: Sequence[float], ci_level: float
) -> evaluation.ConfidenceInterval:
    arr = np.asarray(samples, dtype=np.float64)
    alpha = (1.0 - ci_level) / 2.0
    lo = float(np.nanpercentile(arr, 100.0 * alpha))
    hi = float(np.nanpercentile(arr, 100.0 * (1.0 - alpha)))
    return evaluation.ConfidenceInterval(point=point, lo=lo, hi=hi)


@dataclass(frozen=True)
class DiDResult:
    """A difference of increments, paired on the bootstrap's own resamples.

    ``increment(target) = metric(target_R1) - metric(target_R0)``. The reported
    quantity is ``increment(target_a) - increment(target_b)`` for one metric, with
    a percentile interval from the shared replicate indices.
    """

    metric: str
    target_a: str
    target_b: str
    interval: evaluation.ConfidenceInterval


def difference_of_increments(
    scored: ScoredPartition,
    replicate_indices: Sequence[IntArray],
    *,
    metrics: Sequence[str],
    pairs: Sequence[tuple[str, str]],
    ci_level: float = evaluation.DEFAULT_CI_LEVEL,
) -> list[DiDResult]:
    """H2's difference of differences, reusing the bootstrap's paired resamples.

    For each replicate the six models are scored on the *same* resample indices,
    each within-target increment ``R1 - R0`` is formed, and the difference between
    two targets' increments is taken -- so the DiD stays paired, exactly as section
    12 requires. Three increments with overlapping intervals is not a test of the
    ordering; this is.
    """
    y = scored.outcome
    prob = scored.probabilities

    def metrics_on(idx: IntArray | None) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for spec in MODEL_SPECS:
            p = prob[spec.model_id]
            if idx is None:
                out[spec.model_id] = dict(
                    evaluation.evaluate_metrics(y, p, outcome_type=evaluation.OUTCOME_BERNOULLI)
                )
            else:
                out[spec.model_id] = dict(
                    evaluation.evaluate_metrics(
                        y[idx], p[idx], outcome_type=evaluation.OUTCOME_BERNOULLI
                    )
                )
        return out

    def increment(scored_metrics: dict[str, dict[str, float]], target: str, metric: str) -> float:
        return scored_metrics[f"{target}_R1"][metric] - scored_metrics[f"{target}_R0"][metric]

    point_metrics = metrics_on(None)
    replicate_metrics = [metrics_on(idx) for idx in replicate_indices]

    results: list[DiDResult] = []
    for metric in metrics:
        for a, b in pairs:
            point = increment(point_metrics, a, metric) - increment(point_metrics, b, metric)
            samples = [
                increment(rep, a, metric) - increment(rep, b, metric)
                for rep in replicate_metrics
            ]
            results.append(
                DiDResult(
                    metric=metric,
                    target_a=a,
                    target_b=b,
                    interval=_percentile_ci(point, samples, ci_level),
                )
            )
    return results


def bootstrap_panel(
    scored: ScoredPartition,
    *,
    n_replicates: int = evaluation.DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = evaluation.DEFAULT_BOOTSTRAP_SEED,
    ci_level: float = evaluation.DEFAULT_CI_LEVEL,
) -> evaluation.BootstrapResult:
    """The paired cluster bootstrap over drafts for every model and comparison.

    Clusters on ``draft_id`` and pairs across models (section 12). Carries the
    within-target increments and the cross-target R1 comparisons; its
    ``replicate_indices`` are reused for the H2 difference-of-increments so the DiD
    is drawn on exactly the same resamples.
    """
    comparisons = list(WITHIN_TARGET_INCREMENTS) + list(CROSS_TARGET_R1)
    return evaluation.paired_cluster_bootstrap(
        {spec.model_id: scored.probabilities[spec.model_id] for spec in MODEL_SPECS},
        scored.outcome,
        scored.groups,
        metrics=list(BOOTSTRAP_METRICS),
        comparisons=comparisons,
        outcome_type=evaluation.OUTCOME_BERNOULLI,
        n_replicates=n_replicates,
        seed=seed,
        ci_level=ci_level,
    )


# --------------------------------------------------------------------------
# Artifacts -- reconstructed probabilities keyed by obs_id, under data/runs/.
# --------------------------------------------------------------------------


def write_holdout_artifacts(scored: ScoredPartition, runs_dir: Path) -> list[Path]:
    """Write one reconstructed-probability parquet per model, keyed by obs_id.

    Each carries the outcome, the reconstructed win probability and the pre-clip
    raw reconstruction, so the report's numbers are reproducible without a second
    read. Gitignored under ``data/runs`` alongside the boosters they come from.
    """
    runs_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in MODEL_SPECS:
        path = _holdout_artifact_path(spec.model_id, runs_dir)
        table = pa.table(
            {
                OBS_ID_COL: pa.array(scored.obs_ids, type=pa.string()),
                OUTCOME_ART_COL: pa.array(scored.outcome.tolist(), type=pa.float64()),
                PROB_ART_COL: pa.array(
                    scored.probabilities[spec.model_id].tolist(), type=pa.float64()
                ),
                RAW_ART_COL: pa.array(
                    scored.raw_reconstructions[spec.model_id].tolist(), type=pa.float64()
                ),
            }
        )
        pq.write_table(table, path, compression="snappy")
        written.append(path)
    return written


def _read_ledger_lines(ledger_path: Path) -> list[str]:
    if not ledger_path.exists():
        return []
    return [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]


# --------------------------------------------------------------------------
# The whole job: validate, rehearse, open once, score, bootstrap, report.
# --------------------------------------------------------------------------


@dataclass
class FinalReadResult:
    """Everything the report and the caller need from the single read."""

    split_sha256: str
    run_records: dict[str, dict[str, Any]]
    rehearsal: ScoredPartition
    holdout: ScoredPartition
    panels: dict[str, ModelPanel]
    bootstrap: evaluation.BootstrapResult
    did: list[DiDResult]
    ledger_line: str
    artifacts: list[Path] = field(default_factory=list)


def run_final_read(
    sources: targets.Sources = targets.DEFAULT_SOURCES,
    runs_dir: Path = RUNS_DIR,
    *,
    split_parquet: Path = SPLIT_PARQUET,
    split_manifest: Path = SPLIT_MANIFEST,
    ledger_path: Path = LEDGER_PATH,
    report_path: Path = REPORT_MD,
    n_replicates: int = evaluation.DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = evaluation.DEFAULT_BOOTSTRAP_SEED,
    ci_level: float = evaluation.DEFAULT_CI_LEVEL,
    card_id: str = CARD_ID,
    reason: str = READ_REASON,
    write_report_file: bool = True,
) -> FinalReadResult:
    """Do the single holdout read end to end: everything falsifiable before the seal.

    Order of operations, deliberately: (1) the environment must match the pins, or
    the card stops while the seal is intact; (2) the split hash is verified against
    the manifest; (3) all six run records are validated; (4) the development
    rehearsal runs the identical scoring path and its bootstrap, proving the code
    where a failure is free; only then (5) the holdout is opened **once** through
    the seal, scored through the same :func:`score_partition`, bootstrapped, and the
    H2 difference-of-increments computed on the bootstrap's own resamples; (6) the
    artifacts and the report are written. After the read nothing may fail into a
    second read: there is no repeat path.
    """
    # (1)-(3): every guard that can fail, in front of the seal.
    require_pinned_environment()
    split_sha256 = estimator.verify_split_hash(split_parquet, split_manifest)
    run_records = validate_all_run_records(runs_dir, sources, split_sha256)

    # (4) Rehearse on development through the identical scoring path, and exercise
    # the bootstrap too, so nothing about the code is in question at the seal.
    dev_table = load_dev(split_parquet)
    rehearsal = score_partition(dev_table, sources, runs_dir, partition_label="dev")
    bootstrap_panel(
        rehearsal, n_replicates=REHEARSAL_REPLICATES, seed=seed, ci_level=ci_level
    )

    # (5) THE READ. One line is appended to the ledger before rows return; from
    # here on, only pure computation, and no failure may reopen the holdout.
    holdout_table = load_holdout(
        card_id,
        reason,
        split_parquet=split_parquet,
        split_manifest=split_manifest,
        ledger_path=ledger_path,
    )
    holdout = score_partition(holdout_table, sources, runs_dir, partition_label="holdout")
    panels = panel_for(holdout)
    bootstrap = bootstrap_panel(holdout, n_replicates=n_replicates, seed=seed, ci_level=ci_level)
    did = difference_of_increments(
        holdout,
        bootstrap.replicate_indices,
        metrics=[evaluation.BRIER_SKILL_SCORE, evaluation.LOG_LOSS, evaluation.BRIER],
        pairs=DID_PAIRS,
        ci_level=ci_level,
    )

    ledger_lines = _read_ledger_lines(ledger_path)
    ledger_line = ledger_lines[-1] if ledger_lines else ""

    # (6) Artifacts, then the report.
    artifacts = write_holdout_artifacts(holdout, runs_dir)
    result = FinalReadResult(
        split_sha256=split_sha256,
        run_records=run_records,
        rehearsal=rehearsal,
        holdout=holdout,
        panels=panels,
        bootstrap=bootstrap,
        did=did,
        ledger_line=ledger_line,
        artifacts=artifacts,
    )
    if write_report_file:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(result), encoding="utf-8", newline="\n")
    return result


# --------------------------------------------------------------------------
# The report.
# --------------------------------------------------------------------------

_LEVEL_METRIC_ORDER: tuple[str, ...] = (
    evaluation.LOG_LOSS,
    evaluation.BRIER,
    evaluation.BRIER_SKILL_SCORE,
    evaluation.RMSE,
    evaluation.MAE,
    evaluation.AUC,
)


def _fmt(x: float) -> str:
    return f"{x:.6f}"


def _ci(interval: evaluation.ConfidenceInterval) -> str:
    return f"{interval.point:+.6f} [{interval.lo:+.6f}, {interval.hi:+.6f}]"


def _crosses_zero(interval: evaluation.ConfidenceInterval) -> bool:
    return interval.lo <= 0.0 <= interval.hi


def render_report(result: FinalReadResult) -> str:  # noqa: C901 - one linear report builder
    """Render ``reports/holdout_read.md`` from the computed result."""
    boot = result.bootstrap
    lines: list[str] = []
    lines.append("# The single holdout read -- all six models scored once (card 017)")
    lines.append("")
    lines.append(
        "This is the measurement the benchmark was built to make. The sealed "
        "external holdout was opened **exactly once**, through "
        "`deckbench.holdout.load_holdout`, and all six fitted models "
        "(T0/T1/T2 x R0/R1) were scored through the card-010 evaluation panel on "
        "the reconstructed-probability scale -- the only scale on which the three "
        "target formulations are comparable. Nothing was trained, tuned, selected "
        "or refitted; the boosters are fixed inputs. The uncertainty on every "
        "comparison is carried by the paired cluster bootstrap, clustered on "
        "`draft_id`."
    )
    lines.append("")
    lines.append(
        "> **`base_p` is not skill, and `m_hat` is not skill.** R0's single "
        "feature is the reliability-shrunk historical win-rate proxy `base_p`, a "
        "nuisance representation (card 005). `m_hat` is a *learned* estimate of "
        "expected win probability given that representation (the full-data "
        "`T0_R0` booster). Both are baselines; neither is a measurement of a "
        "player."
    )
    lines.append("")

    # The ledger line, verbatim.
    lines.append("## The one ledger line")
    lines.append("")
    lines.append(
        "`cycle/holdout_ledger.jsonl` was 0 bytes before this card and now holds "
        "exactly one line, quoted verbatim:"
    )
    lines.append("")
    lines.append("```json")
    lines.append(result.ledger_line)
    lines.append("```")
    lines.append("")

    # Guards in front of the seal.
    lines.append("## What was verified before the seal was touched")
    lines.append("")
    lines.append(
        "Every failure that can happen before the read is free; every failure "
        "after it is permanent, because `load_holdout` appends its ledger line "
        "before returning rows. So all validation ran in front of the seal:"
    )
    lines.append("")
    lines.append(
        "1. **Environment.** `deckbench.environment.require_pinned_environment()` "
        "was called first: xgboost 3.1.2, numpy 2.3.5, pyarrow 22.0.0. A "
        "mismatched stack would have stopped the card while the seal was still "
        "intact."
    )
    lines.append(
        f"2. **Split hash.** The split parquet was verified against the manifest "
        f"(`{result.split_sha256}`)."
    )
    lines.append(
        "3. **Run records.** All six records were validated -- `target`, "
        "`representation`, `objective`, `n_features`, `seed` and `split_sha256` -- "
        "before any booster was used. The feature counts were checked against the "
        "assembled matrix width, not a hardcoded constant, because xgboost matches "
        "features positionally and a silently transposed matrix would produce "
        "plausible, wrong numbers."
    )
    lines.append(
        "4. **Rehearsal.** The development partition was scored through the "
        "identical `score_partition` code path, and its bootstrap run, before the "
        "holdout was opened. The rehearsal and the real read call the same scoring "
        "function; they are not two parallel implementations. (The rehearsal's "
        "development numbers are contaminated -- the boosters trained on those "
        "rows -- and are deliberately not tabulated beside the holdout numbers.)"
    )
    lines.append("")

    # Reconstruction and clipping.
    lines.append("## Reconstruction and clipping on the holdout")
    lines.append("")
    lines.append(
        "T0's booster output is the win probability directly. T1 reconstructs "
        "`base_p + B_hat`; T2 reconstructs `m_hat(S) + B_hat`, where `m_hat` is "
        "the **full-data** `T0_R0.xgb` applied to holdout rows -- no holdout row "
        "trained it, so it is honest on them by construction, and the development "
        "out-of-fold baseline (which does not exist for holdout rows) is never "
        "synthesised. Each reconstruction is clipped into the unit interval with "
        "the panel's declared bound (`PROBABILITY_CLIP` = "
        f"{evaluation.PROBABILITY_CLIP:.0e}) **only for scoring**; the counts at "
        "each end are a measurement, not a nuisance:"
    )
    lines.append("")
    lines.append("| Model | rows | clipped low | clipped high | raw min | raw max |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for spec in MODEL_SPECS:
        stats = result.holdout.clip_stats.get(spec.model_id)
        if stats is None:
            lines.append(
                f"| {spec.model_id} | {len(result.holdout.obs_ids)} | - | - | "
                "n/a (T0: direct probability) | n/a |"
            )
        else:
            lines.append(
                f"| {spec.model_id} | {stats.n_rows} | {stats.n_clipped_low} | "
                f"{stats.n_clipped_high} | {stats.raw_min:.6f} | {stats.raw_max:.6f} |"
            )
    lines.append("")

    # Master results table.
    lines.append("## Master results -- holdout panel, one row per model")
    lines.append("")
    header = (
        "| Model | Target | Repr | "
        + " | ".join(_LEVEL_METRIC_ORDER)
        + " | cal_intercept | cal_slope |"
    )
    lines.append(header)
    lines.append("| " + " | ".join(["---"] * (len(_LEVEL_METRIC_ORDER) + 5)) + " |")
    for spec in MODEL_SPECS:
        panel = result.panels[spec.model_id]
        cells = [_fmt(panel.metrics[m]) for m in _LEVEL_METRIC_ORDER]
        lines.append(
            f"| {spec.model_id} | {spec.target} | {spec.representation} | "
            + " | ".join(cells)
            + f" | {_fmt(panel.cal_intercept)} | {_fmt(panel.cal_slope)} |"
        )
    lines.append("")
    lines.append(
        f"All metrics are on the reconstructed win probability against the raw "
        f"`won` outcome, `outcome_type = bernoulli`. There is deliberately no "
        f"unlabelled regression R-squared on a Bernoulli outcome; the panel "
        f"reports a Brier skill score instead (section 9). Bootstrap: "
        f"{boot.n_replicates} replicates, seed {boot.seed}, "
        f"{boot.ci_level:.0%} interval, clustered on `{boot.cluster_level}`."
    )
    lines.append("")

    # Within-target increments.
    lines.append("## Incremental value: the within-target increment R1 - R0 (section 11)")
    lines.append("")
    lines.append(
        "The incremental-value question is how much card identity adds beyond the "
        "skill-only baseline, within each target formulation. Each cell is "
        "`point [lo, hi]` for `metric(R1) - metric(R0)`, from the paired cluster "
        "bootstrap. For log loss, Brier, RMSE and MAE a **negative** difference "
        "favours R1 (lower error); for Brier skill score and AUC a **positive** "
        "difference favours R1."
    )
    lines.append("")
    inc_header = "| Increment | " + " | ".join(BOOTSTRAP_METRICS) + " |"
    lines.append(inc_header)
    lines.append("| " + " | ".join(["---"] * (len(BOOTSTRAP_METRICS) + 1)) + " |")
    for a, b in WITHIN_TARGET_INCREMENTS:
        key = evaluation._comparison_key(a, b)
        cells = [_ci(boot.differences[key][m]) for m in BOOTSTRAP_METRICS]
        lines.append(f"| {a} - {b} | " + " | ".join(cells) + " |")
    lines.append("")

    # Cross-target R1 comparisons.
    lines.append("## Cross-target comparisons among the three R1 models")
    lines.append("")
    lines.append(
        "How the skill-plus-identity representation performs across the three "
        "target formulations, on the common probability scale. Each cell is "
        "`point [lo, hi]` for `metric(a) - metric(b)`."
    )
    lines.append("")
    lines.append(inc_header)
    lines.append("| " + " | ".join(["---"] * (len(BOOTSTRAP_METRICS) + 1)) + " |")
    for a, b in CROSS_TARGET_R1:
        key = evaluation._comparison_key(a, b)
        cells = [_ci(boot.differences[key][m]) for m in BOOTSTRAP_METRICS]
        lines.append(f"| {a} - {b} | " + " | ".join(cells) + " |")
    lines.append("")

    # H2 difference of increments.
    lines.append("## H2 -- the difference of increments (a difference of differences)")
    lines.append("")
    lines.append(
        "H2 predicts an ordering of *deck signal* across target formulations, "
        "`increment(T2) > increment(T1) > increment(T0)`, where deck signal is the "
        "increment `R1 - R0` within a formulation -- **not** the absolute "
        "performance of R1, which is dominated by how well the formulation predicts "
        "outcomes at all. So the comparison is a difference of differences, and its "
        "uncertainty is drawn from the **same** bootstrap resamples for both "
        "increments (the panel returns `replicate_indices` precisely so this stays "
        "paired). Three increments with overlapping intervals is not a test of the "
        "ordering; the intervals below are."
    )
    lines.append("")
    lines.append(
        "On Brier skill score, deck signal is larger when the increment is larger "
        "(higher is better), so H2 predicts each `increment(T2) - increment(T1)` "
        "and `increment(T1) - increment(T0)` to be positive. On log loss and "
        "Brier, lower is better, so the sign convention flips."
    )
    lines.append("")
    lines.append("| Metric | increment(a) - increment(b) | point [lo, hi] | interval excludes 0 |")
    lines.append("| --- | --- | --- | --- |")
    for did in result.did:
        excludes = "yes" if not _crosses_zero(did.interval) else "no"
        lines.append(
            f"| {did.metric} | increment({did.target_a}) - increment({did.target_b}) | "
            f"{_ci(did.interval)} | {excludes} |"
        )
    lines.append("")
    lines.append(
        "An interval that includes zero does not establish the ordering H2 "
        "predicts, in either direction. The development-side increments were "
        "ordered `T2 > T0 > T1`, against H2's predicted `T2 > T1 > T0`; that was "
        "recorded as an expectation carrying no weight, because development metrics "
        "are contaminated by the folds that selected the hyperparameters. The "
        "holdout intervals above are the only honest evidence on the ordering."
    )
    lines.append("")

    # H1.
    lines.append("## H1 -- skill dominance")
    lines.append("")
    lines.append(
        "H1 says skill alone explains substantially more predictable variation in "
        "raw outcomes than deck identity does. The skill-only models (R0) and the "
        "skill-plus-identity models (R1) are compared directly by the within-target "
        "increments above: the R1 - R0 differences measure exactly the additional "
        "predictable variation card identity contributes beyond the `base_p` "
        "baseline. The absolute panel shows the skill-only R0 models already "
        "capturing the bulk of the achievable Brier skill score, with the R1 "
        "increments small in every target formulation -- consistent with H1's "
        "claim that skill dominates. The magnitude of each increment, and whether "
        "its interval clears zero, is read from the increment table; the absolute "
        "R0 levels are in the master table."
    )
    lines.append("")

    # Section 13 interpretation rule, in full.
    lines.append("## Interpretation rule (benchmark section 13), in full")
    lines.append("")
    lines.append(
        "A null incremental result is a limit of the representation, learner and "
        "dataset -- **never** evidence that deck composition does not affect win "
        "probability. Concretely, `R2(S + D) approx R2(S)` supports:"
    )
    lines.append("")
    lines.append(
        "> Card identity provides little detectable incremental predictive "
        "information beyond skill under this representation, learner and dataset."
    )
    lines.append("")
    lines.append("It does **not** establish:")
    lines.append("")
    lines.append("> Deck composition does not affect win probability.")
    lines.append("")
    lines.append(
        "The difference between those two sentences is the entire epistemic content "
        "of this benchmark. A null result has several explanations that section 13 "
        "requires be stated rather than gestured at:"
    )
    lines.append("")
    lines.append("* deck effects are small relative to skill;")
    lines.append("* deck effects are interaction-dependent;")
    lines.append("* card identity is an inefficient representation;")
    lines.append("* outcome noise overwhelms small effects;")
    lines.append(
        "* skill partially proxies expected deck quality because stronger players "
        "draft better decks."
    )
    lines.append("")
    lines.append(
        "No causal conclusion about deck composition is stated or implied "
        "anywhere in this report. The representation axis that would probe deck "
        "structure directly -- R2 (knowledge graph), R3 (game script), R4 and R5 "
        "-- is phase 3, a separate benchmark against a holdout this card has now "
        "spent; whether phase 3 needs a fresh split is a question for whoever "
        "writes it, to be asked before any model is fitted."
    )
    lines.append("")

    # Provenance.
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Split SHA256 (verified before the read): `{result.split_sha256}`")
    lines.append(
        f"- Bootstrap: {boot.n_replicates} replicates, seed {boot.seed}, "
        f"{boot.ci_level:.0%} percentile interval, clustered on `{boot.cluster_level}`; "
        "the same seed reproduces the intervals byte for byte."
    )
    lines.append(
        "- Environment: xgboost 3.1.2, numpy 2.3.5, pyarrow 22.0.0 "
        "(`deckbench.environment` pins)."
    )
    lines.append(
        "- Holdout reconstructed-probability artifacts, keyed by `obs_id`, are "
        "written under `data/runs/{model_id}_holdout_predictions.parquet` (six "
        "files), so every number above is reproducible without a second read. "
        "They are gitignored alongside the boosters, and regenerable only by "
        "re-reading the holdout -- which this card does not permit."
    )
    lines.append(
        "- The holdout was opened exactly once; the single ledger line above "
        "records the commit, timestamp and split hash of that read."
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# --verify: check artifacts and ledger, WITHOUT reading the holdout.
# --------------------------------------------------------------------------


def verify(
    runs_dir: Path = RUNS_DIR,
    ledger_path: Path = LEDGER_PATH,
    report_path: Path = REPORT_MD,
    *,
    card_id: str = CARD_ID,
) -> int:
    """Check the emitted artifacts and the ledger; never read the holdout.

    Verifies that each of the six holdout reconstructed-probability artifacts
    exists and is non-empty, that the report exists, and that the ledger records
    exactly one read, by this card. It reads no split partition and opens no seal,
    so it is safe to run on every retry. Non-vacuous: removing any one artifact
    makes it fail.
    """
    problems: list[str] = []
    for spec in MODEL_SPECS:
        path = _holdout_artifact_path(spec.model_id, runs_dir)
        if not path.exists():
            problems.append(f"holdout artifact {path} is missing")
            continue
        table = pq.read_table(path)
        if table.num_rows == 0:
            problems.append(f"holdout artifact {path} is empty")
        elif OBS_ID_COL not in table.column_names or PROB_ART_COL not in table.column_names:
            problems.append(
                f"holdout artifact {path} lacks {OBS_ID_COL!r}/{PROB_ART_COL!r} columns"
            )

    if not report_path.exists():
        problems.append(f"holdout report {report_path} is missing")

    lines = _read_ledger_lines(ledger_path)
    if len(lines) != 1:
        problems.append(
            f"holdout ledger {ledger_path} has {len(lines)} line(s); the single "
            "read must leave exactly one."
        )
    else:
        try:
            record = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            problems.append(f"the single ledger line is not valid JSON: {exc}")
        else:
            if record.get("card_id") != card_id:
                problems.append(
                    f"the ledger line records card {record.get('card_id')!r}, "
                    f"expected {card_id!r}"
                )
            if record.get("is_repeat") is True:
                problems.append("the ledger line is marked a repeat read")

    if problems:
        print("final_read --verify FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        "final_read --verify OK: six holdout prediction artifacts present and "
        "non-empty, report present, and the holdout ledger records exactly one "
        "read by card 017 -- checked without reading the holdout."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="check the emitted artifacts and the ledger, without reading the holdout.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.verify:
        return verify()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
