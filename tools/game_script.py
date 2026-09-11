"""R3: the game-script simulator. Mana and casting only -- NO graph is used.

Exploratory tooling for phase 3, preserved because its result is a NEGATIVE
and negatives are what nobody reconstructs. See `reports/phase3_exploration.md`:
the script does not beat the skill proxy alone on development, and adding it to
card identity makes identity worse.

It uses no knowledge graph, which is what makes it the correct CONTROL for
phase 3 rather than a candidate -- it measures what a curve-aware encoding buys
before any mechanism is involved.

Changes from the first pass:
  * TAPPED LANDS. Every dual in this set enters tapped (Mirkwood, Goblin-town,
    Iron Hills, Lake-town, Elvenking's Halls) as does The Lonely Mountain; the
    basics do not. A land played on turn t that enters tapped first produces mana
    on turn t+1. Ignoring this inflated early curve quality, and inflated it most
    for two-colour decks playing duals -- exactly the signal R3 exists to measure.
  * ON THE PLAY. No draw on turn 1; a draw on turns 2..10.
  * The land drop is chosen by LOOKAHEAD on SPELLS CAST, tie-broken by how much
    of the hand's colour demand the resulting mana base covers. That is what makes the tapped-land
    trade-off real -- a tapped dual costs tempo now to fix colour later.

Still declared simplifications: no mulligans (every hand is kept), greedy rather
than optimal casting, no mana abilities on nonlands, no cost reduction, no X
spells, no scry or selection.
"""

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import pyarrow.parquet as pq

ROOT = str(Path(__file__).resolve().parents[1])
TURNS = 10
N_SIMS = 4000
SEED = 20260908

TAPPED_MARKERS = ("enters tapped", "enters the battlefield tapped")

FACE = {}
for line in open(f"{ROOT}/data/normalized/faces.jsonl", encoding="utf-8"):
    d = json.loads(line)
    if d.get("index", 0) != 0:
        continue
    mc = d.get("mana_cost") or {}
    tl = d.get("type_line") or {}
    txt = (d.get("oracle_text") or "").replace("\n", " ").lower()
    pips = dict(mc.get("pips") or {})
    FACE[d["name"]] = {
        "pips": pips,
        "generic": int(mc.get("generic") or 0),
        "cmc": int(mc.get("generic") or 0) + sum(pips.values()),
        "is_land": "Land" in (tl.get("types") or []),
        "produces": set(d.get("produced_mana") or []),
        "tapped": any(m in txt for m in TAPPED_MARKERS),
    }

feat2name = {}
with open(f"{ROOT}/data/processed/card_identity_manifest.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        feat2name[r["feature_name"]] = r["source_column"][len("deck_"):]


def can_pay(lands: list[set], pips: dict, generic: int) -> bool:
    need = [c for c, k in pips.items() for _ in range(k)]
    if len(need) + generic > len(lands):
        return False
    used = [False] * len(lands)

    def match(i: int) -> bool:
        if i == len(need):
            return True
        for j, src in enumerate(lands):
            if not used[j] and need[i] in src:
                used[j] = True
                if match(i + 1):
                    return True
                used[j] = False
        return False

    return match(0) and sum(1 for u in used if not u) >= generic


def greedy_cast(pool: list[set], hand: list[str]) -> tuple[int, int, list[str]]:
    """Cast the best SET of spells this turn: max count, ties broken on mana spent.

    Not a sequential greedy. Casting several spells in one turn only requires the
    COMBINED cost to be payable from the pool, so the choice is a subset search
    and the same matching test applies to the summed cost. Subsets are tried in
    decreasing (count, total cmc) order and the first payable one wins, which is
    exactly the stated policy: two 2-drops beat one 5-drop on five lands, but
    when only one spell is castable either way the 5-drop is preferred over the
    2-drop rather than stranding it.
    """
    spells = sorted(
        (c for c in hand if not FACE[c]["is_land"]), key=lambda c: FACE[c]["cmc"]
    )
    if not spells or not pool:
        return 0, 0, list(hand)
    # a turn can never cast more spells than it has mana for
    k_max = min(len(spells), len(pool))
    while k_max and sum(FACE[c]["cmc"] for c in spells[:k_max]) > len(pool):
        k_max -= 1

    for k in range(k_max, 0, -1):
        best = None
        for combo in combinations(spells, k):
            total = sum(FACE[c]["cmc"] for c in combo)
            if total > len(pool):
                continue
            if best is not None and total <= best[0]:
                continue
            pips: Counter = Counter()
            generic = 0
            for c in combo:
                for col, n in FACE[c]["pips"].items():
                    pips[col] += n
                generic += FACE[c]["generic"]
            if can_pay(pool, dict(pips), generic):
                best = (total, combo)
        if best is not None:
            total, combo = best
            rest = list(hand)
            for c in combo:
                rest.remove(c)
            return total, k, rest
    return 0, 0, list(hand)


def simulate(deck_counts: dict[str, int], rng: random.Random) -> dict:
    library = [n for n, k in deck_counts.items() for _ in range(k)]
    rng.shuffle(library)
    hand, library = library[:7], library[7:]
    board: list[tuple[set, int]] = []  # (produces, first turn it can tap)
    out = {}
    for turn in range(1, TURNS + 1):
        if turn > 1 and library:  # ON THE PLAY: no turn-1 draw
            hand.append(library.pop())

        lands_in_hand = {c for c in hand if FACE[c]["is_land"]}
        if lands_in_hand:
            best, best_key = None, None
            for cand in lands_in_hand:
                avail = [p for p, t0 in board if t0 <= turn]
                if not FACE[cand]["tapped"]:
                    avail = avail + [FACE[cand]["produces"]]
                _, n_cast, _ = greedy_cast(avail, hand)
                # colour balance: how much of the hand's pip demand the mana base
                # would actually cover, counting each colour only up to demand.
                supply: Counter = Counter()
                for p, _t in board:
                    for col in p:
                        supply[col] += 1
                for col in FACE[cand]["produces"]:
                    supply[col] += 1
                demand: Counter = Counter()
                for c in hand:
                    if not FACE[c]["is_land"]:
                        for col, k in FACE[c]["pips"].items():
                            demand[col] += k
                coverage = sum(min(supply[col], demand[col]) for col in demand)
                key = (n_cast, coverage, len(FACE[cand]["produces"]))
                if best_key is None or key > best_key:
                    best, best_key = cand, key
            hand.remove(best)
            board.append(
                (FACE[best]["produces"], turn + 1 if FACE[best]["tapped"] else turn)
            )

        usable = [p for p, t0 in board if t0 <= turn]
        spent, cast, _ = greedy_cast(usable, hand)
        screwed = any(
            not FACE[c]["is_land"]
            and FACE[c]["cmc"] <= len(usable)
            and not can_pay(usable, FACE[c]["pips"], FACE[c]["generic"])
            for c in hand
        )
        # a spell was cast this turn, so remove it from hand for the next turn
        _, _, hand = greedy_cast(usable, hand)
        out[turn] = {
            "lands": len(board),
            "usable": len(usable),
            "spent": spent,
            "wasted": len(usable) - spent,
            "cast": cast,
            "screwed": screwed,
            "drop": len(board) >= turn,
        }
    return out


def script_of(counts: dict[str, int], n: int = N_SIMS) -> dict:
    rng = random.Random(SEED)
    acc = defaultdict(lambda: defaultdict(float))
    for _ in range(n):
        for turn, s in simulate(counts, rng).items():
            acc[turn]["lands"] += s["lands"]
            acc[turn]["usable"] += s["usable"]
            acc[turn]["spent"] += s["spent"]
            acc[turn]["wasted"] += s["wasted"]
            acc[turn]["cast"] += s["cast"]
            acc[turn]["p_cast"] += bool(s["cast"])
            acc[turn]["p_screw"] += bool(s["screwed"])
            acc[turn]["p_drop"] += bool(s["drop"])
    for turn in acc:
        for k in acc[turn]:
            acc[turn][k] /= n
    return acc


def deck_from_row(row: dict) -> dict[str, int]:
    """Card-name -> copy count, from one row of deck_identity.parquet."""
    frac = {
        feat2name[k]: v[0]
        for k, v in row.items()
        if k != "obs_id" and isinstance(v[0], (int, float)) and v[0] > 0
    }
    unit = min(frac.values())
    return {n: round(f / unit) for n, f in frac.items() if n in FACE}


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Simulate one deck's game script.")
    ap.add_argument("--row", type=int, default=0,
                    help="row index into deck_identity.parquet")
    ap.add_argument("--sims", type=int, default=N_SIMS)
    args = ap.parse_args(argv)

    table = pq.read_table(f"{ROOT}/data/processed/deck_identity.parquet")
    counts = deck_from_row(table.slice(args.row, 1).to_pydict())
    lands = {n: k for n, k in counts.items() if FACE[n]["is_land"]}
    tapped = sum(k for n, k in lands.items() if FACE[n]["tapped"])
    curve: Counter = Counter()
    for n, k in counts.items():
        if not FACE[n]["is_land"]:
            curve[FACE[n]["cmc"]] += k
    print(f"deck: {sum(counts.values())} cards, {sum(lands.values())} lands "
          f"({tapped} enter tapped), {sum(curve.values())} spells")
    print("curve: " + "  ".join(f"{c}cmc:{curve[c]}" for c in sorted(curve)))
    print()
    print(f"{args.sims} sims, seed {SEED}, ON THE PLAY, no mulligans, "
          f"turns 1-{TURNS}")
    print()

    s = script_of(counts, args.sims)
    print(f"{'turn':>4} {'lands':>7} {'usable':>7} {'P(drop)':>8} {'P(cast)':>8} "
          f"{'E[cast]':>8} {'E[spent]':>9} {'E[waste]':>9} {'util':>6} {'P(screw)':>9}")
    print("-" * 86)
    for turn in range(1, TURNS + 1):
        r = s[turn]
        util = r["spent"] / r["usable"] if r["usable"] else 0.0
        print(f"{turn:>4} {r['lands']:>7.2f} {r['usable']:>7.2f} {r['p_drop']:>8.1%} "
              f"{r['p_cast']:>8.1%} {r['cast']:>8.2f} {r['spent']:>9.2f} "
              f"{r['wasted']:>9.2f} {util:>6.1%} {r['p_screw']:>9.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
