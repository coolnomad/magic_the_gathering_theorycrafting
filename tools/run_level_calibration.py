"""Run-level calibration of the holdout predictions, with cluster-bootstrap intervals.

**This is a derived analysis, not a second holdout read.** Every outcome used
here comes from the prediction artifacts card 017 committed under ``data/runs/``
(``obs_id``, ``won``, ``win_probability``), which exist precisely so the read's
numbers can be re-expressed without reopening the seal. ``draft_id`` is joined
from the frozen ``model_split.parquet`` purely as grouping metadata.
:func:`deckbench.holdout.load_holdout` is **never called**, no ledger line is
appended, and ``repeat=True`` appears nowhere. Re-expressing one completed
measurement in different units is not a new probe; bootstrapping metric after
metric on the holdout until one clears zero would be, and this script is fixed
rather than exploratory for that reason.

The unit here is the **run** (one Arena draft event), not the game, because that
is the unit a Limited player experiences. For each run:

    predicted win rate = mean of the per-game predicted probabilities
    observed  win rate = wins / games

Three quantities are reported, each with a paired cluster bootstrap over drafts
using the project's own :func:`deckbench.evaluation.bootstrap_replicate_indices`
at the benchmark's declared settings:

* **calibration slope** -- regress observed on predicted, per model. 1.0 is
  perfect. Reported for the skill-only and the skill-plus-deck model, and for
  their difference.
* **attenuation slope** -- regress the residual the *skill-only* model left on
  the *deck* model's adjustment. 1.0 means the deck signal is scaled exactly
  right; above 1 means the model understates the deck effect; below 1 means it
  overstates it.
* **ventile table** -- twenty equal-count bins for the eye. The fits are on the
  unbinned rows; binning is display only, and the script reports the game-level,
  run-level and ventile-level slopes side by side so the reader can see that the
  result does not depend on either choice.

Run: ``python tools/run_level_calibration.py``. Writes
``reports/figures/run_level_calibration.png`` and prints every number the report
quotes.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from numpy.typing import NDArray

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# `deckbench` is reached through the sys.path insert above, so mypy cannot
# resolve it from tools/; the package ships no py.typed marker.
from deckbench import evaluation  # type: ignore[import-untyped]  # noqa: E402

RUNS_DIR = REPO_ROOT / "data" / "runs"
SPLIT_PARQUET = REPO_ROOT / "data" / "processed" / "model_split.parquet"
FIGURE = REPO_ROOT / "reports" / "figures" / "run_level_calibration.png"

SKILL_ONLY = "T2_R0"
SKILL_DECK = "T2_R1"
N_BINS = 20

FloatArray = NDArray[np.float64]


def wls(x: FloatArray, y: FloatArray, w: FloatArray) -> tuple[float, float]:
    """Weighted least squares. Returns ``(intercept, slope)``."""
    sw = w.sum()
    mx = float((w * x).sum() / sw)
    my = float((w * y).sum() / sw)
    slope = float((w * (x - mx) * (y - my)).sum() / (w * (x - mx) ** 2).sum())
    return my - slope * mx, slope


def _draft_of() -> dict[str, str]:
    split = pq.read_table(SPLIT_PARQUET)
    return dict(
        zip(
            [str(o) for o in split.column("obs_id")],
            [str(d) for d in split.column("draft_id")],
            strict=True,
        )
    )


def _predictions(model: str) -> tuple[list[str], FloatArray, FloatArray]:
    table = pq.read_table(RUNS_DIR / f"{model}_holdout_predictions.parquet")
    obs = [str(o) for o in table.column("obs_id")]
    won = np.asarray(table.column("won"), dtype=np.float64)
    p = np.asarray(table.column("win_probability"), dtype=np.float64)
    return obs, won, p


def collapse_to_runs(
    obs: list[str], draft_of: dict[str, str], *columns: FloatArray
) -> tuple[FloatArray, ...]:
    """Mean each column within a draft; also return the game count per draft."""
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0] * (len(columns) + 1))
    for i, o in enumerate(obs):
        row = acc[draft_of[o]]
        row[0] += 1.0
        for j, col in enumerate(columns):
            row[j + 1] += float(col[i])
    keys = sorted(acc)
    n = np.array([acc[k][0] for k in keys], dtype=np.float64)
    means = tuple(
        np.array([acc[k][j + 1] / acc[k][0] for k in keys], dtype=np.float64)
        for j in range(len(columns))
    )
    return (n, *means)


def ventiles(
    x: FloatArray, y: FloatArray, w: FloatArray
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Equal-count bins on ``x``; weighted means plus a per-bin standard error."""
    order = np.argsort(x)
    px, py, se, cnt = [], [], [], []
    for chunk in np.array_split(order, N_BINS):
        ww = w[chunk]
        px.append(float((ww * x[chunk]).sum() / ww.sum()))
        m = float((ww * y[chunk]).sum() / ww.sum())
        py.append(m)
        var = float((ww * (y[chunk] - m) ** 2).sum() / ww.sum())
        se.append(float(np.sqrt(var / len(chunk))))
        cnt.append(float(len(chunk)))
    return np.array(px), np.array(py), np.array(se), np.array(cnt)


def main() -> int:
    draft_of = _draft_of()
    obs, won, p0 = _predictions(SKILL_ONLY)
    obs1, won1, p1 = _predictions(SKILL_DECK)
    if obs != obs1 or not np.array_equal(won, won1):
        raise SystemExit("the two holdout artifacts disagree on rows or outcomes")

    groups = np.array([draft_of[o] for o in obs], dtype=object)
    ones = np.ones_like(won)
    adj = p1 - p0
    resid0 = won - p0

    n_runs, obs_r, p0_r, p1_r = collapse_to_runs(obs, draft_of, won, p0, p1)
    adj_r = p1_r - p0_r
    resid0_r = obs_r - p0_r

    print(f"holdout games {len(won):,}   runs (drafts) {len(n_runs):,}   "
          f"mean games/run {n_runs.mean():.2f}\n")

    # The result must not depend on aggregation or on binning; show all three.
    vx, vy, _, _ = ventiles(adj_r, resid0_r, n_runs)
    print(f"{'attenuation slope at':34s} {'rows':>8s} {'slope':>9s} {'intercept':>11s}")
    print("-" * 66)
    for label, rows, sl in (
        ("game level, unbinned", len(won), wls(adj, resid0, ones)),
        ("run level, unbinned (weighted)", len(n_runs), wls(adj_r, resid0_r, n_runs)),
        ("ventile means (as plotted)", N_BINS, wls(vx, vy, np.ones(N_BINS))),
    ):
        print(f"{label:34s} {rows:>8,} {sl[1]:>9.4f} {sl[0]:>+11.5f}")

    print("\ncorr(deck adjustment, skill-only prediction): "
          f"game {np.corrcoef(adj, p0)[0, 1]:+.4f}   run {np.corrcoef(adj_r, p0_r)[0, 1]:+.4f}")

    # Paired cluster bootstrap, the benchmark's own settings and primitive.
    n_rep = evaluation.DEFAULT_BOOTSTRAP_REPLICATES
    seed = evaluation.DEFAULT_BOOTSTRAP_SEED
    ci = evaluation.DEFAULT_CI_LEVEL
    print(f"\npaired cluster bootstrap over drafts: {n_rep} replicates, seed {seed}, "
          f"{ci:.0%} percentile intervals\n")

    point = {
        "attenuation": wls(adj, resid0, ones)[1],
        "calib_skill_only": wls(p0, won, ones)[1],
        "calib_skill_deck": wls(p1, won, ones)[1],
    }
    point["calib_diff"] = point["calib_skill_deck"] - point["calib_skill_only"]

    draws: dict[str, list[float]] = defaultdict(list)
    for idx in evaluation.bootstrap_replicate_indices(groups, n_rep, seed):
        o = np.ones(len(idx), dtype=np.float64)
        draws["attenuation"].append(wls(adj[idx], resid0[idx], o)[1])
        a = wls(p0[idx], won[idx], o)[1]
        b = wls(p1[idx], won[idx], o)[1]
        draws["calib_skill_only"].append(a)
        draws["calib_skill_deck"].append(b)
        draws["calib_diff"].append(b - a)

    alpha = (1.0 - ci) / 2.0
    labels = {
        "attenuation": "attenuation slope  (1.0 = scaled right)",
        "calib_skill_only": "calibration slope, skill only",
        "calib_skill_deck": "calibration slope, skill + deck",
        "calib_diff": "calibration slope, deck - skill only",
    }
    print(f"{'quantity':42s} {'point':>8s} {'lo':>9s} {'hi':>9s}   excludes null")
    print("-" * 86)
    for key, label in labels.items():
        arr = np.asarray(draws[key])
        lo = float(np.percentile(arr, 100 * alpha))
        hi = float(np.percentile(arr, 100 * (1 - alpha)))
        null = 0.0 if key == "calib_diff" else 1.0
        excl = "YES" if (lo > null or hi < null) else "no"
        print(f"{label:42s} {point[key]:>8.4f} {lo:>9.4f} {hi:>9.4f}   {null:g}? {excl}")

    arr = np.asarray(draws["attenuation"])
    lo = float(np.percentile(arr, 100 * alpha))
    hi = float(np.percentile(arr, 100 * (1 - alpha)))
    print(f"\nP(attenuation slope > 1) = {(arr > 1.0).mean():.3f}")
    print(f"understatement of the deck effect: {100 * (point['attenuation'] - 1):.1f}% "
          f"[{100 * (lo - 1):.1f}%, {100 * (hi - 1):.1f}%]")

    cx, cy, cse, ccnt = ventiles(p1_r, obs_r, n_runs)
    print(f"\nventile calibration table, skill + deck ({N_BINS} bins):")
    print(f"{'bin':>4} {'runs':>7} {'pred':>9} {'obs':>9} {'diff':>9}")
    for i, (a_, b_, c_) in enumerate(zip(cx, cy, ccnt, strict=True), 1):
        print(f"{i:>4} {int(c_):>7} {a_:>9.4f} {b_:>9.4f} {b_ - a_:>+9.4f}")

    _plot(p0_r, p1_r, obs_r, n_runs, point, draws, alpha)
    print(f"\nwrote {FIGURE.relative_to(REPO_ROOT)}")
    return 0


def _plot(
    p0_r: FloatArray,
    p1_r: FloatArray,
    obs_r: FloatArray,
    n_runs: FloatArray,
    point: dict[str, float],
    draws: dict[str, list[float]],
    alpha: float,
) -> None:
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    adj_r = p1_r - p0_r
    resid0_r = obs_r - p0_r
    FIGURE.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.4))
    fig.suptitle(
        "Run-level calibration on the sealed holdout  --  unit is the draft run, "
        f"{len(n_runs):,} runs, {int(n_runs.sum()):,} games",
        fontsize=13,
        y=0.99,
    )

    ax = axes[0]
    for pred, label, colour, key in (
        (p0_r, "skill only", "#B03A2E", "calib_skill_only"),
        (p1_r, "skill + deck", "#1F618D", "calib_skill_deck"),
    ):
        a, b = wls(pred, obs_r, n_runs)
        px, py, se, _ = ventiles(pred, obs_r, n_runs)
        arr = np.asarray(draws[key])
        lo = float(np.percentile(arr, 100 * alpha))
        hi = float(np.percentile(arr, 100 * (1 - alpha)))
        ax.errorbar(
            px, py, yerr=1.96 * se, fmt="o", ms=5, capsize=2.5, lw=1.1, color=colour,
            label=f"{label}   slope {b:.3f} [{lo:.3f}, {hi:.3f}]",
        )
    lims = (0.35, 0.80)
    ax.plot(lims, lims, "k--", lw=1, label="perfect calibration")
    ax.set_xlim(*lims)
    ax.set_ylim(*lims)
    ax.set_xlabel("Mean predicted win rate over the run (ventile)")
    ax.set_ylabel("Observed win rate over the run")
    ax.set_title("Ventile calibration, weighted by games")
    ax.legend(loc="upper left", fontsize=8.5, frameon=False)
    ax.grid(alpha=0.25, lw=0.5)

    ax = axes[1]
    ax.hist(adj_r, bins=60, weights=n_runs, color="#1F618D", alpha=0.85,
            edgecolor="white", lw=0.3)
    ax.axvline(0, color="k", ls="--", lw=1)
    ax.set_xlabel("Run-level deck adjustment  (predicted win rate with deck  -  without)")
    ax.set_ylabel("Games-weighted count of runs")
    ax.set_title(
        f"What the deck moves  --  sd {adj_r.std():.4f}, "
        f"10th/90th pct {np.percentile(adj_r, 10):+.3f}/{np.percentile(adj_r, 90):+.3f}"
    )
    ax.grid(alpha=0.25, lw=0.5)

    ax = axes[2]
    px, py, se, _ = ventiles(adj_r, resid0_r, n_runs)
    ax.errorbar(px, py, yerr=1.96 * se, fmt="o", ms=5, capsize=2.5, lw=1.1, color="#1F618D")
    arr = np.asarray(draws["attenuation"])
    lo = float(np.percentile(arr, 100 * alpha))
    hi = float(np.percentile(arr, 100 * (1 - alpha)))
    xs = np.linspace(float(adj_r.min()), float(adj_r.max()), 50)
    a2, b2 = wls(adj_r, resid0_r, n_runs)
    ax.plot(xs, a2 + b2 * xs, color="#B03A2E", lw=1.3,
            label=f"fitted slope {point['attenuation']:.3f} [{lo:.3f}, {hi:.3f}]")
    ax.plot(xs, xs, "k--", lw=1, label="slope 1 (perfectly scaled)")
    ax.axhline(0, color="k", lw=0.6, alpha=0.5)
    ax.axvline(0, color="k", lw=0.6, alpha=0.5)
    ax.set_xlabel("Run-level deck adjustment")
    ax.set_ylabel("Residual left by the skill-only model\n(observed - predicted)")
    ax.set_title("Is the deck signal correctly scaled?")
    ax.legend(loc="upper left", fontsize=8.5, frameon=False)
    ax.grid(alpha=0.25, lw=0.5)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(FIGURE, dpi=160)


if __name__ == "__main__":
    raise SystemExit(main())
