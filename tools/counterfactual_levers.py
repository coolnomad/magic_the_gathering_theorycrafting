"""A MENTAL EXERCISE: if the fitted model were the true causal model, how big are
the two levers -- changing the deck, and changing the player?

**Nothing here is a causal finding, and the premise is one this project has
explicitly not established.** Benchmark section 13 governs: a predictive
increment measured with a fixed learner on a fixed representation does not show
that changing a deck would change a win rate. This script computes the
arithmetic of "suppose it did", because that arithmetic is a useful way to feel
the size of the measured effects -- not because the supposition is believed.

One assumption inside it is actively known to be false in a way that biases the
answer. ``base_p`` is a historical *win rate*, and a player's win rate is partly
produced by the decks they habitually draft. Section 13 names exactly this:
"skill partially proxies expected deck quality because stronger players draft
better decks." So the SKILL lever below is really *skill plus the deck quality
that travels with it*, and the skill-to-deck ratio it implies is an **upper
bound on skill's advantage**, not an estimate of it.

Two interventions, both read off card 017's committed holdout predictions:

  DECK   hold the player fixed, swap the deck.
         lever = the deck model's adjustment, ``T2_R1 - T2_R0``
  SKILL  hold the deck fixed, swap the player.
         lever = the spread of the skill-only prediction, ``T2_R0``

Head-to-head is computed in log-odds space. A per-game probability ``p`` is "win
against the average field", so a player's strength is
``theta = logit(p) - logit(p_field)`` and ``P(A beats B) = sigmoid(theta_A -
theta_B)``. That keeps probabilities in range and makes the two levers
commensurable. It is an assumption layered on top of the model, not something
this project tested.

The deck lever is also shown with the measured attenuation correction (x1.178,
from ``tools/run_level_calibration.py``), since the model understates the deck
effect.

Derived analysis of committed artifacts: ``load_holdout`` is never called and
``cycle/holdout_ledger.jsonl`` is untouched.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from math import comb
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from numpy.typing import NDArray

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

RUNS_DIR = REPO_ROOT / "data" / "runs"
SPLIT_PARQUET = REPO_ROOT / "data" / "processed" / "model_split.parquet"

SKILL_ONLY = "T2_R0"
SKILL_DECK = "T2_R1"

#: Measured attenuation of the deck signal; see reports/run_level_calibration.md.
ATTENUATION = 1.1782

FloatArray = NDArray[np.float64]


def _logit(p: float) -> float:
    return float(np.log(p / (1.0 - p)))


def _sigmoid(z: float) -> float:
    return float(1.0 / (1.0 + np.exp(-z)))


def run_outcomes(p: float) -> tuple[float, float]:
    """``(expected wins, P(trophy))`` for a stopped 7-win / 3-loss run."""
    q = 1.0 - p
    expected_wins = trophy = 0.0
    for losses in (0, 1, 2):
        pr = comb(6 + losses, losses) * p**7 * q**losses
        expected_wins += 7 * pr
        trophy += pr
    for wins in range(7):
        expected_wins += wins * comb(wins + 2, 2) * p**wins * q**3
    return expected_wins, trophy


def _read(model: str) -> tuple[list[str], FloatArray]:
    table = pq.read_table(RUNS_DIR / f"{model}_holdout_predictions.parquet")
    return (
        [str(o) for o in table.column("obs_id")],
        np.asarray(table.column("win_probability"), dtype=np.float64),
    )


def main() -> int:
    obs, p0 = _read(SKILL_ONLY)
    obs1, p1 = _read(SKILL_DECK)
    if obs != obs1:
        raise SystemExit("the two holdout artifacts disagree on rows")
    adj = p1 - p0

    split = pq.read_table(SPLIT_PARQUET)
    draft_of = dict(
        zip(
            [str(o) for o in split.column("obs_id")],
            [str(d) for d in split.column("draft_id")],
            strict=True,
        )
    )
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for o, skill, deck in zip(obs, p0, adj, strict=True):
        row = acc[draft_of[o]]
        row[0] += 1.0
        row[1] += float(skill)
        row[2] += float(deck)
    keys = sorted(acc)
    skill_r = np.array([acc[k][1] / acc[k][0] for k in keys])
    adj_r = np.array([acc[k][2] / acc[k][0] for k in keys])

    field = float(np.mean(p0))
    print("*** MENTAL EXERCISE -- the premise is NOT established. See section 13. ***\n")
    print(f"holdout runs {len(keys):,}   field mean per-game win probability {field:.4f}\n")

    print("THE TWO LEVERS, as spreads in per-game win probability (run level)\n")
    header = f"{'':28s} {'10th':>9s} {'50th':>9s} {'90th':>9s} {'p90-p10':>10s} {'sd':>8s}"
    print(header)
    print("-" * len(header))
    for name, v in (("SKILL (deck fixed)", skill_r), ("DECK  (player fixed)", adj_r)):
        q10, q50, q90 = (float(x) for x in np.percentile(v, [10, 50, 90]))
        print(f"{name:28s} {q10:>9.4f} {q50:>9.4f} {q90:>9.4f} "
              f"{q90 - q10:>10.4f} {v.std():>8.4f}")
    q10d, q90d = (float(x) for x in np.percentile(adj_r, [10, 90]))
    print(f"{'DECK, attenuation-corrected':28s} {q10d * ATTENUATION:>9.4f} {0.0:>9.4f} "
          f"{q90d * ATTENUATION:>9.4f} {(q90d - q10d) * ATTENUATION:>10.4f} "
          f"{adj_r.std() * ATTENUATION:>8.4f}")

    s10, s90 = (float(x) for x in np.percentile(skill_r, [10, 90]))
    span_deck = (q90d - q10d) * ATTENUATION
    print(f"\nlever ratio (p90 - p10): skill / deck = {(s90 - s10) / span_deck:.1f}x")
    print("  -- an UPPER BOUND on skill's advantage: base_p carries deck quality inside it.")

    print("\n\nHEAD TO HEAD, log-odds space, two otherwise identical players\n")
    base = float(np.median(skill_r))
    for label, a_adj, b_adj in (
        ("same skill, same deck", 0.0, 0.0),
        ("same skill, A top-decile deck vs B median", q90d * ATTENUATION, 0.0),
        ("same skill, A top-decile vs B bottom-decile", q90d * ATTENUATION, q10d * ATTENUATION),
    ):
        theta_a = _logit(base + a_adj) - _logit(field)
        theta_b = _logit(base + b_adj) - _logit(field)
        print(f"  {label:46s} P(A wins) = {_sigmoid(theta_a - theta_b):.4f}")
    theta_a = _logit(s90) - _logit(field)
    theta_b = _logit(s10) - _logit(field)
    print(f"  {'same deck, A 90th-pct player vs B 10th-pct':46s} "
          f"P(A wins) = {_sigmoid(theta_a - theta_b):.4f}")

    print("\n\nOVER A WHOLE RUN (stopped 7-win / 3-loss), from the median player\n")
    print(f"{'intervention':48s} {'E[wins]':>9s} {'trophy':>9s}")
    print("-" * 70)
    for label, p in (
        ("baseline: median player, median deck", base),
        ("swap to a bottom-decile deck", base + q10d * ATTENUATION),
        ("swap to a top-decile deck", base + q90d * ATTENUATION),
        ("become a 10th-percentile player (deck fixed)", s10),
        ("become a 90th-percentile player (deck fixed)", s90),
    ):
        expected_wins, trophy = run_outcomes(p)
        print(f"{label:48s} {expected_wins:>9.3f} {trophy:>8.2%}")

    print("\n*** Still a mental exercise. None of the above is a causal finding. ***")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
