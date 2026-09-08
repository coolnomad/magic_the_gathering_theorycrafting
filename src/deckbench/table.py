"""Build the game-level modeling table from the raw HOB dataset.

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md`` (card 004). This
module turns the raw 17Lands CSV into ``data/processed/model_table.parquet`` --
one row per observation, carrying the observation id, the metadata columns the
audit identified, and the deck size. It builds no card-fraction features (that
is :mod:`deckbench.identity`), no skill proxy (card 005), no split (card 006),
and fits nothing.

The observational unit is not re-derived here: it is read from
``reports/modeling_data_audit.json`` and must be ``game``. The observation key
is discovered to be ``(draft_id, game_time, match_number, game_number)`` --
``(draft_id, game_time)`` alone is *not* unique in this file, and the collision
count is reported rather than silently deduplicated.

Nothing about the file's card set is baked into this source: the column
families are matched by prefix against the header, exactly as the audit does.
Run it with::

    python -m deckbench.table

which writes the parquet table and refreshes the build report.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

# src/deckbench/table.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_CSV = REPO_ROOT / "data" / "raw" / "game_data_public.HOB.PremierDraft.csv.gz"
SOURCE_MANIFEST = REPO_ROOT / "data" / "raw" / "source_manifest.json"
AUDIT_JSON = REPO_ROOT / "reports" / "modeling_data_audit.json"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MODEL_TABLE_PARQUET = PROCESSED_DIR / "model_table.parquet"
REPORT_MD = REPO_ROOT / "reports" / "model_table_build.md"

# Card-column family prefixes, matched against the header. These are prefixes,
# not a hardcoded list of this file's columns; a different set has different
# cards behind the same prefixes.
CARD_FAMILIES: tuple[str, ...] = (
    "deck_",
    "sideboard_",
    "opening_hand_",
    "drawn_",
    "tutored_",
)

# The one family that constitutes the played deck. Documented in the report.
DECK_PREFIX = "deck_"

# The columns that jointly identify one observation. The audit recommends
# keying by draft_id + game_time; that pair is not unique in this file, so the
# match/game number are added to make the key injective. See the build report.
KEY_COLUMNS: tuple[str, ...] = (
    "draft_id",
    "game_time",
    "match_number",
    "game_number",
)

# The per-game outcome column. Carried in the model table (it is the label the
# later cards predict); it is never turned into a deck feature.
OUTCOME_COL = "won"

# blake2b is not hash-seeded, so an obs id is stable across runs and machines.
OBS_ID_DIGEST_SIZE = 16
# Field separator inside the obs-id preimage: a control byte that cannot occur
# in a draft id, timestamp or integer, so the key parts cannot be confused.
OBS_ID_SEP = "\x1f"

# Fixed float precision for the report so it renders identically across runs.
FLOAT_NDIGITS = 6


class RawFileMissing(FileNotFoundError):
    """Raised when the raw 17Lands CSV is absent from disk."""


class UnexpectedObservationalUnit(ValueError):
    """Raised when the ratified unit in the audit JSON is not ``game``."""


class UnresolvableRow(ValueError):
    """Raised when a row's deck counts cannot be parsed. Names the obs id."""


def _require_raw_file() -> None:
    if not RAW_CSV.exists():
        raise RawFileMissing(
            f"Raw dataset not found: {RAW_CSV}. It is not tracked in git; "
            f"see {SOURCE_MANIFEST} for its URL and SHA256, re-download it, "
            "and verify the hash before running the build."
        )


def observational_unit() -> str:
    """Return the unit ratified by the audit, refusing to re-derive it.

    The audit report is the single source of truth for the observational unit
    (benchmark section 17 and this card's requirements). Only ``game`` is
    implemented; anything else stops the run rather than guessing.
    """
    if not AUDIT_JSON.exists():
        raise FileNotFoundError(
            f"Audit report not found: {AUDIT_JSON}. Run `python -m deckbench.audit` "
            "first; card 004 consumes the unit it ratifies."
        )
    payload = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    unit = payload["recommended_observational_unit"]["unit"]
    if unit != "game":
        raise UnexpectedObservationalUnit(
            f"Audit ratified observational unit {unit!r}; only 'game' is "
            "implemented. This builder does not aggregate games into decks."
        )
    return str(unit)


@dataclass(frozen=True)
class Layout:
    """Header-derived column positions, computed once per file."""

    header: tuple[str, ...]
    deck_columns: tuple[str, ...]
    deck_indices: tuple[int, ...]
    non_card_columns: tuple[str, ...]
    non_card_indices: tuple[int, ...]
    key_indices: tuple[int, ...]


def build_layout(header: list[str]) -> Layout:
    """Classify a header into deck columns, metadata columns and the key."""
    index = {name: i for i, name in enumerate(header)}
    missing = [col for col in KEY_COLUMNS if col not in index]
    if missing:
        raise KeyError(f"raw header is missing key columns: {missing}")

    deck_columns: list[str] = []
    deck_indices: list[int] = []
    non_card_columns: list[str] = []
    non_card_indices: list[int] = []
    for i, name in enumerate(header):
        if name.startswith(DECK_PREFIX):
            deck_columns.append(name)
            deck_indices.append(i)
        elif any(name.startswith(fam) for fam in CARD_FAMILIES):
            # sideboard_/opening_hand_/drawn_/tutored_ -- excluded from both the
            # deck and the metadata, for the reasons documented in the report.
            continue
        else:
            non_card_columns.append(name)
            non_card_indices.append(i)

    return Layout(
        header=tuple(header),
        deck_columns=tuple(deck_columns),
        deck_indices=tuple(deck_indices),
        non_card_columns=tuple(non_card_columns),
        non_card_indices=tuple(non_card_indices),
        key_indices=tuple(index[col] for col in KEY_COLUMNS),
    )


def make_obs_id(key_parts: tuple[str, ...]) -> str:
    """Return a stable observation id from the injective key parts."""
    hasher = hashlib.blake2b(digest_size=OBS_ID_DIGEST_SIZE)
    hasher.update(OBS_ID_SEP.join(key_parts).encode("utf-8"))
    return hasher.hexdigest()


def parse_count(raw: str) -> int:
    """Parse one deck cell. Blank means zero; a non-integer is unresolvable.

    Nothing is imputed or defaulted: a cell that is neither blank nor an integer
    raises, so the caller can fail the run naming the observation.
    """
    if raw == "":
        return 0
    return int(raw)


def open_raw_reader() -> tuple[TextIO, Iterator[list[str]], list[str]]:
    """Open the gzipped CSV and return the handle, reader and header row."""
    _require_raw_file()
    handle = gzip.open(RAW_CSV, "rt", newline="", encoding="utf-8")
    reader = csv.reader(handle)
    header = next(reader)
    return handle, reader, header


@dataclass(frozen=True)
class Observation:
    """One resolved game: its id, sort key, metadata and deck vector."""

    obs_id: str
    sort_key: tuple[str, str, int, int]
    non_card: tuple[str, ...]
    deck_counts: tuple[int, ...]
    deck_size: int


def _to_int(raw: str) -> int:
    return int(raw) if raw else 0


def resolve_observation(row: list[str], layout: Layout) -> Observation:
    """Turn one raw row into an :class:`Observation`, or raise if unresolvable."""
    key_parts = tuple(row[i] for i in layout.key_indices)
    obs_id = make_obs_id(key_parts)
    draft_id, game_time, match_no, game_no = key_parts
    try:
        deck_counts = tuple(parse_count(row[i]) for i in layout.deck_indices)
    except ValueError as exc:  # non-integer deck cell -> name the observation
        raise UnresolvableRow(
            f"observation {obs_id} (key={key_parts}) has an unparseable deck "
            f"count: {exc}"
        ) from exc
    non_card = tuple(row[i] for i in layout.non_card_indices)
    return Observation(
        obs_id=obs_id,
        sort_key=(draft_id, game_time, _to_int(match_no), _to_int(game_no)),
        non_card=non_card,
        deck_counts=deck_counts,
        deck_size=sum(deck_counts),
    )


@dataclass
class BuildStats:
    """Counts and findings from one table build, for the report."""

    unit: str
    total_rows: int
    zero_size_dropped: int
    kept_rows: int
    key_collisions: int
    n_non_card_columns: int
    n_deck_columns: int


def _iter_observations() -> Iterator[Observation]:
    handle, reader, header = open_raw_reader()
    try:
        layout = build_layout(header)
        for row in reader:
            yield resolve_observation(row, layout)
    finally:
        handle.close()


def collect_observations() -> tuple[list[Observation], BuildStats]:
    """Stream the file, drop zero-size decks, and return sorted observations.

    Row order is fixed by :attr:`Observation.sort_key` so the parquet output is
    byte-reproducible and joins to the identity table on ``obs_id`` in the same
    order. The count of dropped zero-size decks and of duplicate keys are
    reported, never silently swallowed.
    """
    unit = observational_unit()
    kept: list[Observation] = []
    seen: set[str] = set()
    total = 0
    dropped = 0
    collisions = 0
    n_non_card = 0
    n_deck = 0
    for obs in _iter_observations():
        total += 1
        n_non_card = len(obs.non_card)
        n_deck = len(obs.deck_counts)
        if obs.deck_size == 0:
            dropped += 1
            continue
        if obs.obs_id in seen:
            collisions += 1
        else:
            seen.add(obs.obs_id)
        kept.append(obs)

    if collisions:
        raise UnresolvableRow(
            f"{collisions} observation ids collided; the key "
            f"{KEY_COLUMNS} is not injective on this file"
        )

    kept.sort(key=lambda o: o.sort_key)
    stats = BuildStats(
        unit=unit,
        total_rows=total,
        zero_size_dropped=dropped,
        kept_rows=len(kept),
        key_collisions=collisions,
        n_non_card_columns=n_non_card,
        n_deck_columns=n_deck,
    )
    return kept, stats


def _model_table(observations: list[Observation], layout: Layout) -> pa.Table:
    """Assemble the pyarrow table with a fixed column order."""
    columns: dict[str, object] = {
        "obs_id": pa.array([o.obs_id for o in observations], type=pa.string())
    }
    for pos, name in enumerate(layout.non_card_columns):
        columns[name] = pa.array(
            [o.non_card[pos] for o in observations], type=pa.string()
        )
    columns["deck_size"] = pa.array(
        [o.deck_size for o in observations], type=pa.int32()
    )
    return pa.table(columns)


def build_model_table() -> BuildStats:
    """Build and write ``model_table.parquet``; return the build stats."""
    observations, stats = collect_observations()
    # Re-derive the layout from the header for the column order (the streaming
    # pass discarded it). The header is small; reopening is cheap.
    handle, _reader, header = open_raw_reader()
    handle.close()
    layout = build_layout(header)
    table = _model_table(observations, layout)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, MODEL_TABLE_PARQUET, compression="snappy")
    return stats


def _round(value: float) -> float:
    return round(value, FLOAT_NDIGITS)


def write_report(stats: BuildStats) -> None:
    """Write the human-readable build report for the model table."""
    frac_dropped = _round(stats.zero_size_dropped / stats.total_rows) if stats.total_rows else 0.0
    lines = [
        "# Model table build -- game-level modeling table",
        "",
        "Card 004, part 1. `deckbench.table` turns the raw 17Lands HOB Premier "
        "Draft file into one row of outcome and metadata per observation. No "
        "card fractions, skill proxy, split or model are produced here.",
        "",
        f"Source file: `{RAW_CSV.relative_to(REPO_ROOT).as_posix()}`",
        f"Output: `{MODEL_TABLE_PARQUET.relative_to(REPO_ROOT).as_posix()}`",
        "",
        "## Observational unit",
        "",
        f"**Unit: {stats.unit}.** Read verbatim from "
        "`reports/modeling_data_audit.json` "
        "(`recommended_observational_unit.unit`); it is not re-derived or "
        "overridden here. The audit ratified the game as the unit because the "
        "deck changes within a draft, so averaging a draft's games would blend "
        "distinct decks.",
        "",
        "## Observation key",
        "",
        "The audit recommends keying by `draft_id` + `game_time`. That pair is "
        "**not unique** in this file: five game rows share a `(draft_id, "
        "game_time)` with another row, distinguishable only by `match_number`. "
        "The observation key is therefore the injective 4-tuple "
        f"`{', '.join(KEY_COLUMNS)}`, and `obs_id` is a blake2b digest of it. "
        "The run fails if any two rows still collide on that key.",
        "",
        "## Column families -- included and excluded",
        "",
        "Every family the audit found is accounted for explicitly:",
        "",
        "| Family | Disposition | Reason |",
        "| --- | --- | --- |",
        "| `deck_` | **included** | The maindeck the player registered for this "
        "game. This is the deck whose strength the benchmark (R1) represents. |",
        "| `sideboard_` | excluded | Cards held out of the played 40; not part of "
        "the deck that played this game. |",
        "| `opening_hand_` | excluded | A per-game *realisation* of draws from the "
        "deck, not the deck's composition; it is downstream of the shuffle. |",
        "| `drawn_` | excluded | Same: cards actually drawn during the game, a "
        "realised outcome rather than the static deck. Reachability lives in the "
        "R3 game-script representation, not in R1 identity. |",
        "| `tutored_` | excluded | Cards fetched during play; another realised "
        "in-game event, not deck construction. |",
        "",
        "The non-card metadata columns (draft id, timestamps, outcome, ranks, "
        "colours, turn counts, skill buckets, ...) are carried verbatim as "
        "strings; typing them is left to the cards that consume them.",
        "",
        "## Row accounting",
        "",
        f"- Raw rows read: **{stats.total_rows}**",
        f"- Zero-size decks dropped: **{stats.zero_size_dropped}** "
        f"({frac_dropped} of rows)",
        f"- Observations kept: **{stats.kept_rows}**",
        f"- Duplicate-key collisions after keying: **{stats.key_collisions}**",
        f"- Metadata columns carried: **{stats.n_non_card_columns}** "
        "(plus `obs_id` and `deck_size`)",
        f"- Deck card columns summed for deck size: **{stats.n_deck_columns}**",
        "",
        "A zero-size deck carries no card-fraction representation (its row sum "
        "would divide by zero), so such rows are dropped from both tables and "
        "the count is reported here rather than silently discarded.",
        "",
        "## Determinism",
        "",
        "Rows are written in a fixed order (`draft_id`, `game_time`, "
        "`match_number`, `game_number`) and columns in a fixed order (`obs_id`, "
        "the metadata columns in header order, then `deck_size`). Two "
        "consecutive builds produce byte-identical parquet. The hash is pinned "
        "in `data/processed/MANIFEST.sha256`, regenerated by "
        "`deckbench.identity`.",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> None:
    stats = build_model_table()
    write_report(stats)
    print(
        f"Model table built: {stats.kept_rows} observations "
        f"({stats.zero_size_dropped} zero-size decks dropped from "
        f"{stats.total_rows} rows), {stats.n_non_card_columns} metadata columns. "
        f"Wrote {MODEL_TABLE_PARQUET.relative_to(REPO_ROOT).as_posix()}."
    )


if __name__ == "__main__":
    main()
