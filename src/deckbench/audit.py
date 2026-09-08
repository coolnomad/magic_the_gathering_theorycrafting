"""Section-17 audit of the raw HOB game-level dataset.

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md`` section 17. This
module settles a single question -- *what one observation is* -- by measuring
the raw 17Lands game-level file and reporting. It builds no modeling table, no
features and no split, and it fits nothing.

Every reported number is computed from the file. Nothing about the file's shape
is baked into this source: the column families are discovered from the header,
and the row/draft/column totals are counted, never transcribed. Run it with::

    python -m deckbench.audit

which writes ``reports/modeling_data_audit.md`` and
``reports/modeling_data_audit.json``.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import struct
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path

# src/deckbench/audit.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_CSV = REPO_ROOT / "data" / "raw" / "game_data_public.HOB.PremierDraft.csv.gz"
SOURCE_MANIFEST = REPO_ROOT / "data" / "raw" / "source_manifest.json"
REPORTS_DIR = REPO_ROOT / "reports"
JSON_REPORT = REPORTS_DIR / "modeling_data_audit.json"
MD_REPORT = REPORTS_DIR / "modeling_data_audit.md"

# Card-column family prefixes. These are matched against the header to classify
# columns; they are prefixes, not a hardcoded list of the file's columns.
CARD_FAMILIES = ("deck_", "sideboard_", "opening_hand_", "drawn_", "tutored_")

# Semantic anchor columns the audit must name verbatim (benchmark sections 6-7).
DRAFT_ID_COL = "draft_id"
OUTCOME_COL = "won"
DRAFT_TIME_COL = "draft_time"
GAME_TIME_COL = "game_time"
RANK_COL = "rank"
WIN_RATE_BUCKET_COL = "user_game_win_rate_bucket"
N_GAMES_BUCKET_COL = "user_n_games_bucket"
BUILD_INDEX_COL = "build_index"
MATCH_NUMBER_COL = "match_number"
GAME_NUMBER_COL = "game_number"

# Skill-context columns whose within-draft constancy the audit checks.
SKILL_COLUMNS = (RANK_COL, WIN_RATE_BUCKET_COL, N_GAMES_BUCKET_COL)

# The 17Lands source entry in the manifest, for a declared-vs-observed check.
MANIFEST_SOURCE_ID = "17lands_hob_premier_draft"

# Minimum legal deck size in a sanctioned Limited event (comprehensive rule
# 100.2b). Limited imposes no maximum, so "outside the legal range" means below
# this floor. This is a rules constant, not a measurement of the file.
LEGAL_MIN_DECK_SIZE = 40

# Fixed float precision so the JSON summary is byte-identical across runs.
FLOAT_NDIGITS = 6

# Rows are read and processed in batches so the full column matrix is never
# resident at once; only per-draft aggregates accumulate.
CHUNK_ROWS = 20000


# One game's coordinates within its draft: the ordering keys plus the deck
# configuration digest and the build_index it was recorded under.
GameRow = tuple[str, int, int, str, str]


class RawFileMissing(FileNotFoundError):
    """Raised when the raw 17Lands CSV is absent from disk."""


def _require_raw_file() -> None:
    if not RAW_CSV.exists():
        raise RawFileMissing(
            f"Raw dataset not found: {RAW_CSV}. It is not tracked in git; "
            f"see {SOURCE_MANIFEST} for its URL and SHA256, re-download it, "
            "and verify the hash before running the audit."
        )


def _to_int(value: str) -> int:
    """Parse an integer field, treating blank as zero."""
    return int(value) if value else 0


def _classify_columns(header: list[str]) -> dict[str, list[str]]:
    """Split the header into card families and the non-card remainder."""
    families: dict[str, list[str]] = {fam: [] for fam in CARD_FAMILIES}
    non_card: list[str] = []
    for name in header:
        for fam in CARD_FAMILIES:
            if name.startswith(fam):
                families[fam].append(name)
                break
        else:
            non_card.append(name)
    families["__non_card__"] = non_card
    return families


def _iter_chunks(rows: Iterator[list[str]], size: int) -> Iterator[list[list[str]]]:
    """Yield the CSV body in row batches, never materializing the whole file."""
    batch: list[list[str]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _deck_digest(values: list[str], deck_indices: list[int]) -> tuple[str, int]:
    """Return a stable digest of the deck vector and its card total.

    Only non-zero slots enter the digest, keyed by their position in the deck
    column order, so the digest is deterministic across runs (blake2b is not
    hash-seeded) and cheap in memory.
    """
    hasher = hashlib.blake2b(digest_size=16)
    total = 0
    for slot, idx in enumerate(deck_indices):
        raw = values[idx]
        if raw == "0" or raw == "":
            continue
        count = int(raw)
        total += count
        hasher.update(struct.pack("<II", slot, count))
    return hasher.hexdigest(), total


def _load_manifest_reference() -> dict[str, int | None]:
    """Read the declared row/draft/column totals from the source manifest."""
    declared: dict[str, int | None] = {"rows": None, "drafts": None, "columns": None}
    if not SOURCE_MANIFEST.exists():
        return declared
    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    for source in payload.get("sources", []):
        if source.get("id") != MANIFEST_SOURCE_ID:
            continue
        for key in declared:
            value = source.get(key)
            declared[key] = int(value) if isinstance(value, int) else None
    return declared


class _Accumulator:
    """Single-pass tallies over the streamed rows."""

    def __init__(self, header: list[str]) -> None:
        self.index = {name: i for i, name in enumerate(header)}
        self.deck_indices = [
            i for i, name in enumerate(header) if name.startswith("deck_")
        ]
        self.present = {
            col: (col in self.index)
            for col in (
                DRAFT_ID_COL,
                OUTCOME_COL,
                DRAFT_TIME_COL,
                GAME_TIME_COL,
                RANK_COL,
                WIN_RATE_BUCKET_COL,
                N_GAMES_BUCKET_COL,
                BUILD_INDEX_COL,
                MATCH_NUMBER_COL,
                GAME_NUMBER_COL,
            )
        }
        self.n_columns = len(header)
        self.total_rows = 0
        self.malformed_rows = 0
        self.deck_size_counts: Counter[int] = Counter()
        self.draft_time_min: str | None = None
        self.draft_time_max: str | None = None
        # Per-draft game lists, keyed by draft id.
        self.games: dict[str, list[GameRow]] = defaultdict(list)
        # Per-draft skill values: col -> (first_value, varies).
        self.skill: dict[str, dict[str, tuple[str, bool]]] = defaultdict(dict)

    def add_row(self, row: list[str]) -> None:
        self.total_rows += 1
        if len(row) != self.n_columns:
            self.malformed_rows += 1
            return
        draft_id = row[self.index[DRAFT_ID_COL]]
        digest, deck_size = _deck_digest(row, self.deck_indices)
        self.deck_size_counts[deck_size] += 1

        if self.present[DRAFT_TIME_COL]:
            stamp = row[self.index[DRAFT_TIME_COL]]
            if stamp:
                if self.draft_time_min is None or stamp < self.draft_time_min:
                    self.draft_time_min = stamp
                if self.draft_time_max is None or stamp > self.draft_time_max:
                    self.draft_time_max = stamp

        game_time = row[self.index[GAME_TIME_COL]] if self.present[GAME_TIME_COL] else ""
        match_no = (
            _to_int(row[self.index[MATCH_NUMBER_COL]]) if self.present[MATCH_NUMBER_COL] else 0
        )
        game_no = (
            _to_int(row[self.index[GAME_NUMBER_COL]]) if self.present[GAME_NUMBER_COL] else 0
        )
        build_index = row[self.index[BUILD_INDEX_COL]] if self.present[BUILD_INDEX_COL] else ""
        self.games[draft_id].append((game_time, match_no, game_no, build_index, digest))

        draft_skill = self.skill[draft_id]
        for col in SKILL_COLUMNS:
            if not self.present[col]:
                continue
            value = row[self.index[col]]
            if col not in draft_skill:
                draft_skill[col] = (value, False)
            elif not draft_skill[col][1] and draft_skill[col][0] != value:
                draft_skill[col] = (draft_skill[col][0], True)


def _summarize_within_draft(acc: _Accumulator) -> dict[str, object]:
    """Reduce the per-draft game lists to the section-6 measurements."""
    total_drafts = len(acc.games)
    total_games = 0
    drafts_multi_deck = 0
    games_after_change = 0
    configs_per_draft: Counter[int] = Counter()

    build_index_nonconstant = 0
    deck_config_nonconstant = 0
    bi_determines_config = 0
    config_determines_bi = 0
    bijective = 0
    bi_varies_deck_constant = 0
    deck_varies_bi_constant = 0

    for rows in acc.games.values():
        total_games += len(rows)
        ordered = sorted(rows, key=lambda g: (g[0], g[1], g[2]))
        configs = [g[4] for g in ordered]
        build_indices = [g[3] for g in ordered]

        distinct_cfg = len(set(configs))
        distinct_bi = len(set(build_indices))
        distinct_pairs = len({(b, c) for b, c in zip(build_indices, configs, strict=True)})
        configs_per_draft[distinct_cfg] += 1
        if distinct_cfg > 1:
            drafts_multi_deck += 1
            deck_config_nonconstant += 1
        if distinct_bi > 1:
            build_index_nonconstant += 1
        if distinct_pairs == distinct_bi:
            bi_determines_config += 1
        if distinct_pairs == distinct_cfg:
            config_determines_bi += 1
        if distinct_pairs == distinct_bi == distinct_cfg:
            bijective += 1
        if distinct_bi > 1 and distinct_cfg == 1:
            bi_varies_deck_constant += 1
        if distinct_cfg > 1 and distinct_bi == 1:
            deck_varies_bi_constant += 1

        changed = False
        for i, cfg in enumerate(configs):
            if i > 0 and cfg != configs[i - 1]:
                changed = True
            if changed:
                games_after_change += 1

    skill_nonconstant = {
        col: sum(
            1
            for draft_skill in acc.skill.values()
            if col in draft_skill and draft_skill[col][1]
        )
        for col in SKILL_COLUMNS
        if acc.present[col]
    }

    return {
        "total_drafts": total_drafts,
        "total_games_from_draft_map": total_games,
        "within_draft_deck_variation": {
            "distinct_configs_per_draft_distribution": _counter_to_pairs(configs_per_draft),
            "drafts_with_more_than_one_deck": drafts_multi_deck,
            "fraction_drafts_with_more_than_one_deck": _fraction(drafts_multi_deck, total_drafts),
            "games_after_a_deck_change": games_after_change,
            "fraction_games_after_a_deck_change": _fraction(games_after_change, total_games),
        },
        "build_index_behavior": {
            "drafts_build_index_nonconstant": build_index_nonconstant,
            "drafts_deck_config_nonconstant": deck_config_nonconstant,
            "drafts_build_index_determines_deck_config": bi_determines_config,
            "drafts_deck_config_determines_build_index": config_determines_bi,
            "drafts_build_index_and_config_bijective": bijective,
            "drafts_build_index_varies_while_deck_constant": bi_varies_deck_constant,
            "drafts_deck_varies_while_build_index_constant": deck_varies_bi_constant,
        },
        "skill_columns_nonconstant_within_draft": dict(sorted(skill_nonconstant.items())),
    }


def _counter_to_pairs(counter: Counter[int]) -> list[list[int]]:
    """Render an int-keyed counter as a list of [value, count], value-sorted."""
    return [[value, counter[value]] for value in sorted(counter)]


def _fraction(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _summarize_deck_size(acc: _Accumulator) -> dict[str, object]:
    counts = acc.deck_size_counts
    total = sum(counts.values())
    below = sum(n for size, n in counts.items() if size < LEGAL_MIN_DECK_SIZE)
    modal_size = max(counts, key=lambda s: (counts[s], -s)) if counts else 0
    off_modal = total - counts.get(modal_size, 0)
    illegal_sizes = {size: n for size, n in counts.items() if size < LEGAL_MIN_DECK_SIZE}
    return {
        "distribution": _counter_to_pairs(counts),
        "min_observed": min(counts) if counts else 0,
        "max_observed": max(counts) if counts else 0,
        "modal_size": modal_size,
        "legal_min_deck_size": LEGAL_MIN_DECK_SIZE,
        "rows_below_legal_min": below,
        "illegal_deck_size_counts": _counter_to_pairs(Counter(illegal_sizes)),
        "card_count_consistency": {
            "note": (
                "No standalone deck-size column exists; deck size is defined as "
                "the sum of the deck_ columns. The consistency check is whether "
                "that sum lands on the modal legal size on every row."
            ),
            "rows_off_modal_size": off_modal,
            "rows_below_legal_min": below,
        },
    }


def run_audit() -> dict[str, object]:
    """Stream the raw file once and return the full audit summary."""
    _require_raw_file()
    with gzip.open(RAW_CSV, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        acc = _Accumulator(header)
        for chunk in _iter_chunks(reader, CHUNK_ROWS):
            for row in chunk:
                acc.add_row(row)

    families = _classify_columns(header)
    family_counts = {fam: len(families[fam]) for fam in CARD_FAMILIES}
    non_card = families["__non_card__"]
    declared = _load_manifest_reference()

    within = _summarize_within_draft(acc)
    deck_size = _summarize_deck_size(acc)

    summary: dict[str, object] = {
        "dataset": {
            "path": RAW_CSV.relative_to(REPO_ROOT).as_posix(),
            "total_games": acc.total_rows,
            "total_drafts": within["total_drafts"],
            "total_columns": acc.n_columns,
            "malformed_rows": acc.malformed_rows,
            "draft_time_min": acc.draft_time_min,
            "draft_time_max": acc.draft_time_max,
        },
        "manifest_declared": {
            "rows": declared["rows"],
            "drafts": declared["drafts"],
            "columns": declared["columns"],
        },
        "declared_vs_observed_match": {
            "rows": declared["rows"] == acc.total_rows,
            "drafts": declared["drafts"] == within["total_drafts"],
            "columns": declared["columns"] == acc.n_columns,
        },
        "column_census": {
            "total_columns": acc.n_columns,
            "card_family_counts": dict(sorted(family_counts.items())),
            "non_card_column_count": len(non_card),
            "non_card_columns": non_card,
        },
        "key_columns": {
            "draft_identifier": DRAFT_ID_COL,
            "per_game_outcome": OUTCOME_COL,
            "deck_contents": "deck_ column family",
            "draft_timestamp": DRAFT_TIME_COL,
            "per_game_timestamp": GAME_TIME_COL,
            "rank": RANK_COL,
            "user_historical_win_rate_bucket": WIN_RATE_BUCKET_COL,
            "user_games_played_bucket": N_GAMES_BUCKET_COL,
            "present": dict(sorted(acc.present.items())),
        },
        "player_identifier": {
            "persistent_player_id_exists": False,
            "statement": (
                "No persistent player identifier exists in the dataset. rank and "
                "opp_rank are six-level skill buckets, not player ids, and are not "
                "nominated as a substitute."
            ),
        },
        "within_draft": within,
        "deck_size": deck_size,
        "recommended_observational_unit": _recommend_unit(within),
    }
    return _round_floats(summary)  # type: ignore[return-value]


def _recommend_unit(within: dict[str, object]) -> dict[str, object]:
    variation = within["within_draft_deck_variation"]
    assert isinstance(variation, dict)
    frac_multi = float(variation["fraction_drafts_with_more_than_one_deck"])
    frac_after = float(variation["fraction_games_after_a_deck_change"])
    if frac_multi > 0:
        rationale = (
            f"The deck is recorded per game and it changes within a draft: "
            f"{frac_multi:.4f} of drafts carry more than one deck configuration and "
            f"{frac_after:.4f} of games are played after a deck change. Averaging a "
            "draft's games would blend distinct decks in exactly those drafts, so the "
            "observational unit is the game, keyed by draft_id + game_time. This "
            "follows benchmark section 6."
        )
    else:
        rationale = (
            "No draft carries more than one deck configuration, so game level and "
            "draft level coincide. The game unit is still recommended per benchmark "
            "section 6 because the deck is recorded per game."
        )
    return {"unit": "game", "rationale": rationale}


def _round_floats(obj: object) -> object:
    if isinstance(obj, float):
        return round(obj, FLOAT_NDIGITS)
    if isinstance(obj, dict):
        return {key: _round_floats(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(value) for value in obj]
    return obj


def write_reports(summary: dict[str, object]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    JSON_REPORT.write_text(text, encoding="utf-8", newline="\n")
    MD_REPORT.write_text(_render_markdown(summary), encoding="utf-8", newline="\n")


def _get(summary: dict[str, object], *path: str) -> object:
    node: object = summary
    for key in path:
        assert isinstance(node, dict)
        node = node[key]
    return node


def _render_markdown(summary: dict[str, object]) -> str:
    dataset = summary["dataset"]
    assert isinstance(dataset, dict)
    census = summary["column_census"]
    assert isinstance(census, dict)
    variation = _get(summary, "within_draft", "within_draft_deck_variation")
    assert isinstance(variation, dict)
    build = _get(summary, "within_draft", "build_index_behavior")
    assert isinstance(build, dict)
    skill_nc = _get(summary, "within_draft", "skill_columns_nonconstant_within_draft")
    assert isinstance(skill_nc, dict)
    deck_size = summary["deck_size"]
    assert isinstance(deck_size, dict)
    consistency = deck_size["card_count_consistency"]
    assert isinstance(consistency, dict)
    declared = summary["manifest_declared"]
    assert isinstance(declared, dict)
    match = summary["declared_vs_observed_match"]
    assert isinstance(match, dict)
    unit = summary["recommended_observational_unit"]
    assert isinstance(unit, dict)
    fam = census["card_family_counts"]
    assert isinstance(fam, dict)

    lines: list[str] = []
    lines.append("# Modeling data audit -- raw HOB game-level dataset")
    lines.append("")
    lines.append(
        "Section-17 audit of the 17Lands HOB Premier Draft file. Every number "
        "below is computed by `deckbench.audit` from the raw CSV. No modeling "
        "table, feature, split or model is produced here."
    )
    lines.append("")
    lines.append(f"Source file: `{dataset['path']}`")
    lines.append("")

    lines.append("## 1. Key columns, named verbatim")
    lines.append("")
    lines.append("| Role | Column |")
    lines.append("| --- | --- |")
    key_cols = summary["key_columns"]
    assert isinstance(key_cols, dict)
    for role, label in (
        ("Draft identifier", "draft_identifier"),
        ("Per-game outcome", "per_game_outcome"),
        ("Deck contents", "deck_contents"),
        ("Draft timestamp", "draft_timestamp"),
        ("Per-game timestamp", "per_game_timestamp"),
        ("Rank", "rank"),
        ("User historical win-rate bucket", "user_historical_win_rate_bucket"),
        ("User games-played bucket", "user_games_played_bucket"),
    ):
        lines.append(f"| {role} | `{key_cols[label]}` |")
    lines.append("")

    lines.append("## 2. Persistent player identifier")
    lines.append("")
    statement = _get(summary, "player_identifier", "statement")
    lines.append(str(statement))
    lines.append("")

    lines.append("## 3. Dataset totals (computed, not transcribed)")
    lines.append("")
    lines.append(f"- Total games (rows): **{dataset['total_games']}**")
    lines.append(f"- Total drafts (distinct `draft_id`): **{dataset['total_drafts']}**")
    lines.append(f"- Total columns: **{dataset['total_columns']}**")
    lines.append(f"- Malformed rows (wrong width): **{dataset['malformed_rows']}**")
    lines.append(
        f"- `draft_time` span: {dataset['draft_time_min']} .. {dataset['draft_time_max']}"
    )
    lines.append("")
    lines.append(
        "Manifest declares "
        f"rows={declared['rows']}, drafts={declared['drafts']}, "
        f"columns={declared['columns']}. "
        f"Observed matches declared: rows={match['rows']}, drafts={match['drafts']}, "
        f"columns={match['columns']}."
    )
    if not all(bool(v) for v in match.values()):
        lines.append("")
        lines.append(
            "> **Discrepancy.** At least one declared total does not match the file. "
            "Per the card, this is a finding, reported rather than reconciled silently."
        )
    lines.append("")

    lines.append("## 4. Column census by family")
    lines.append("")
    lines.append("| Family | Columns |")
    lines.append("| --- | --- |")
    for family in CARD_FAMILIES:
        lines.append(f"| `{family}` | {fam[family]} |")
    lines.append(f"| non-card | {census['non_card_column_count']} |")
    lines.append("")
    non_card = census["non_card_columns"]
    assert isinstance(non_card, list)
    lines.append("Non-card columns: " + ", ".join(f"`{c}`" for c in non_card))
    lines.append("")

    lines.append("## 5. Within-draft deck variation")
    lines.append("")
    lines.append(
        f"- Drafts with more than one deck configuration: "
        f"**{variation['drafts_with_more_than_one_deck']}** "
        f"({variation['fraction_drafts_with_more_than_one_deck']} of drafts)"
    )
    lines.append(
        f"- Games played after a deck change: "
        f"**{variation['games_after_a_deck_change']}** "
        f"({variation['fraction_games_after_a_deck_change']} of games)"
    )
    dist = variation["distinct_configs_per_draft_distribution"]
    assert isinstance(dist, list)
    lines.append(
        "- Distinct deck configurations per draft (configs: drafts): "
        + ", ".join(f"{pair[0]}: {pair[1]}" for pair in dist)
    )
    lines.append("")

    lines.append("## 6. `build_index` -- what it actually varies with")
    lines.append("")
    lines.append(
        f"- Drafts where `build_index` is non-constant: "
        f"{build['drafts_build_index_nonconstant']}"
    )
    lines.append(
        f"- Drafts where the deck config is non-constant: "
        f"{build['drafts_deck_config_nonconstant']}"
    )
    lines.append(
        f"- Drafts where `build_index` determines the deck config: "
        f"{build['drafts_build_index_determines_deck_config']}"
    )
    lines.append(
        f"- Drafts where the deck config determines `build_index`: "
        f"{build['drafts_deck_config_determines_build_index']}"
    )
    lines.append(
        f"- Drafts where `build_index` <-> deck config is bijective: "
        f"{build['drafts_build_index_and_config_bijective']}"
    )
    lines.append(
        f"- `build_index` varies while the deck is constant: "
        f"{build['drafts_build_index_varies_while_deck_constant']}"
    )
    lines.append(
        f"- Deck varies while `build_index` is constant: "
        f"{build['drafts_deck_varies_while_build_index_constant']}"
    )
    lines.append("")

    lines.append("## 7. Deck-size distribution and legality")
    lines.append("")
    lines.append(f"- Legal Limited minimum deck size: {deck_size['legal_min_deck_size']}")
    lines.append(
        f"- Observed deck size: min {deck_size['min_observed']}, "
        f"max {deck_size['max_observed']}, modal {deck_size['modal_size']}"
    )
    lines.append(f"- Rows below the legal minimum: **{deck_size['rows_below_legal_min']}**")
    sizes = deck_size["distribution"]
    assert isinstance(sizes, list)
    lines.append(
        "- Distribution (size: rows): "
        + ", ".join(f"{pair[0]}: {pair[1]}" for pair in sizes)
    )
    lines.append("")

    lines.append("## 8. Card-count consistency")
    lines.append("")
    lines.append(str(consistency["note"]))
    lines.append("")
    lines.append(f"- Rows off the modal deck size: **{consistency['rows_off_modal_size']}**")
    lines.append(f"- Rows below the legal minimum: **{consistency['rows_below_legal_min']}**")
    lines.append("")

    lines.append("## 9. Skill-variable constancy within draft")
    lines.append("")
    lines.append("| Column | Drafts where it is not constant |")
    lines.append("| --- | --- |")
    for col in sorted(skill_nc):
        lines.append(f"| `{col}` | {skill_nc[col]} |")
    lines.append("")

    lines.append("## 10. Recommended observational unit")
    lines.append("")
    lines.append(f"**Unit: {unit['unit']}.**")
    lines.append("")
    lines.append(str(unit["rationale"]))
    lines.append("")
    lines.append(
        "This is a recommendation; the operator ratifies the unit at card 007. "
        "The machine-readable form of every number above is in "
        "`reports/modeling_data_audit.json`."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    summary = run_audit()
    write_reports(summary)
    dataset = summary["dataset"]
    assert isinstance(dataset, dict)
    print(
        f"Audit complete: {dataset['total_games']} games, "
        f"{dataset['total_drafts']} drafts, {dataset['total_columns']} columns. "
        f"Wrote {JSON_REPORT.relative_to(REPO_ROOT).as_posix()} and "
        f"{MD_REPORT.relative_to(REPO_ROOT).as_posix()}."
    )


if __name__ == "__main__":
    main()
