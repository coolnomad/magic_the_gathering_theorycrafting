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

This module is also where the **modeling population** is defined (card 008). A
game whose historical win-rate bucket is empty cannot be scored by the R0
representation, whose only feature is ``base_p``, so such games are excluded
here -- once, at the source -- and every downstream table (:mod:`deckbench.identity`,
:mod:`deckbench.skill`, :mod:`deckbench.split`) inherits the same population
rather than re-deriving the exclusion. The excluded set is derived from the data,
never hardcoded, and the exclusion is outcome-independent: it consults the
pre-draft skill covariate, never ``won``. The audit records that the empty
buckets fall on whole drafts; the run **fails** if it ever finds a draft only
partially affected, because that would break the equivalence between excluding
games and excluding drafts.

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
from collections import defaultdict
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

# The audit key under which the historical win-rate bucket column is named. The
# modeling population excludes games with an empty value in this column; the
# column's actual name is read from the audit, not assumed, so a different file
# with a differently-named bucket is handled by the same code.
SKILL_WIN_RATE_AUDIT_KEY = "user_historical_win_rate_bucket"

# The value a source cell carries when a player has no historical win-rate
# bucket yet. It is the emptiness that marks a game for exclusion; it is never
# imputed or filled.
EMPTY_CELL = ""

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


class PartiallyNullDraft(ValueError):
    """Raised when a draft has both null and non-null historical win-rate rows.

    The population exclusion drops whole drafts whose games all lack a
    historical win-rate bucket. A draft that is only partially affected would
    make "exclude games" and "exclude drafts" different operations, so it stops
    the run rather than being resolved by a silent tie-break.
    """


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


def win_rate_column() -> str | None:
    """The historical win-rate bucket column name from the audit, or ``None``.

    Card 003 established what the skill columns are actually called; the
    population exclusion takes the win-rate column's name from the audit's
    ``key_columns`` block rather than assuming it. Returns ``None`` when the
    audit is absent or does not name the column -- in which case no exclusion is
    applied and the population is just the zero-size-filtered set. That branch is
    for a header that carries no such column at all (the synthetic fixtures); on
    the real file the audit names it and the exclusion runs.
    """
    if not AUDIT_JSON.exists():
        return None
    payload = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    key_columns = payload.get("key_columns")
    if not isinstance(key_columns, dict):
        return None
    column = key_columns.get(SKILL_WIN_RATE_AUDIT_KEY)
    return column if isinstance(column, str) and column else None


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
    null_skill_excluded_rows: int
    null_skill_excluded_drafts: int
    kept_rows: int
    kept_drafts: int
    key_collisions: int
    n_non_card_columns: int
    n_deck_columns: int
    skill_bucket_column: str


def _iter_observations() -> Iterator[Observation]:
    handle, reader, header = open_raw_reader()
    try:
        layout = build_layout(header)
        for row in reader:
            yield resolve_observation(row, layout)
    finally:
        handle.close()


def _win_rate_index(non_card_columns: tuple[str, ...]) -> int | None:
    """Index of the historical win-rate column within the metadata columns.

    ``None`` when the audit does not name the column, or names one absent from
    this header. Both cases mean the null-skill exclusion cannot apply, so the
    population is just the zero-size-filtered set. On the real file the column is
    named and present, so the exclusion runs.
    """
    column = win_rate_column()
    if column is None or column not in non_card_columns:
        return None
    return non_card_columns.index(column)


def _exclude_null_skill_drafts(
    observations: list[Observation], wr_index: int
) -> tuple[list[Observation], int, int]:
    """Drop every game belonging to a draft with no historical win-rate bucket.

    A draft is excluded when *all* of its games carry an empty bucket. The run
    fails naming the offender if any draft is only partially affected, since the
    equivalence between excluding games and excluding drafts rests on that not
    happening. Returns the surviving observations plus the excluded row and
    draft counts. The criterion is the pre-draft win-rate covariate; ``won`` is
    never consulted.
    """
    per_draft: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    for obs in observations:
        draft_id = obs.sort_key[0]
        if obs.non_card[wr_index] == EMPTY_CELL:
            per_draft[draft_id][0] += 1
        else:
            per_draft[draft_id][1] += 1

    partial = sorted(
        draft_id
        for draft_id, (n_null, n_present) in per_draft.items()
        if n_null > 0 and n_present > 0
    )
    if partial:
        raise PartiallyNullDraft(
            f"{len(partial)} draft(s) have both null and non-null historical "
            f"win-rate buckets; the first is {partial[0]!r}. Excluding games and "
            "excluding drafts are no longer the same operation, so the run stops "
            "rather than choosing a tie-break silently."
        )

    excluded_drafts = {
        draft_id for draft_id, (n_null, _n_present) in per_draft.items() if n_null > 0
    }
    kept = [obs for obs in observations if obs.sort_key[0] not in excluded_drafts]
    excluded_rows = len(observations) - len(kept)
    return kept, excluded_rows, len(excluded_drafts)


def collect_observations() -> tuple[list[Observation], BuildStats]:
    """Stream the file, define the modeling population, and return it sorted.

    Two exclusions define the population: a zero-size deck (no card-fraction
    representation, would divide by zero) is dropped, and a game with no
    historical win-rate bucket is excluded together with the rest of its draft
    (card 008). Row order is fixed by :attr:`Observation.sort_key` so the parquet
    output is byte-reproducible and joins to the identity table on ``obs_id`` in
    the same order. Every drop count is reported, never silently swallowed.
    """
    unit = observational_unit()
    # Layout for the column positions (cheap reopen; the streaming pass below
    # does not surface the header). This also validates the raw file exists.
    handle, _reader, header = open_raw_reader()
    handle.close()
    non_card_columns = build_layout(header).non_card_columns

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

    wr_index = _win_rate_index(non_card_columns)
    excluded_rows = 0
    excluded_drafts = 0
    if wr_index is not None:
        kept, excluded_rows, excluded_drafts = _exclude_null_skill_drafts(kept, wr_index)

    kept.sort(key=lambda o: o.sort_key)
    kept_drafts = len({o.sort_key[0] for o in kept})
    stats = BuildStats(
        unit=unit,
        total_rows=total,
        zero_size_dropped=dropped,
        null_skill_excluded_rows=excluded_rows,
        null_skill_excluded_drafts=excluded_drafts,
        kept_rows=len(kept),
        kept_drafts=kept_drafts,
        key_collisions=collisions,
        n_non_card_columns=n_non_card,
        n_deck_columns=n_deck,
        skill_bucket_column=win_rate_column() or "",
    )
    return kept, stats


def population_obs_ids() -> set[str]:
    """The obs-id set of the modeling population, defined once here.

    The downstream card-identity representation reads this rather than
    re-deriving the exclusion, so the null-skill drop lives in exactly one place
    and every table carries the same population.
    """
    observations, _stats = collect_observations()
    return {obs.obs_id for obs in observations}


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
        "## Modeling population -- null-skill exclusion (card 008)",
        "",
        "A game with an empty historical win-rate bucket (column "
        f"`{stats.skill_bucket_column}`) cannot be scored by the benchmark's R0 "
        "representation, whose only feature is `base_p`. The operator decided at "
        "the phase-1 review that this exclusion lands here, at the point the "
        "modeling population is defined, so every downstream table inherits one "
        "coherent population rather than each filtering independently. The "
        "criterion is a pre-draft covariate; `won` is never consulted.",
        "",
        f"- Games excluded (empty win-rate bucket): "
        f"**{stats.null_skill_excluded_rows}**",
        f"- Drafts excluded (every game null): "
        f"**{stats.null_skill_excluded_drafts}**",
        "",
        "The excluded set is derived from the data at run time, never hardcoded. "
        "Each excluded draft is **entirely** null: the build fails if it ever "
        "finds a draft only partially affected, because that would make "
        "excluding games and excluding drafts different operations. Here every "
        "affected draft is fully null, so the two are the same and no tie-break "
        "rule is needed.",
        "",
        "## Row accounting",
        "",
        f"- Raw rows read: **{stats.total_rows}**",
        f"- Zero-size decks dropped: **{stats.zero_size_dropped}** "
        f"({frac_dropped} of rows)",
        f"- Null-skill games excluded: **{stats.null_skill_excluded_rows}** "
        f"across **{stats.null_skill_excluded_drafts}** drafts",
        f"- Observations kept: **{stats.kept_rows}** across "
        f"**{stats.kept_drafts}** drafts",
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
        f"Model table built: {stats.kept_rows} observations across "
        f"{stats.kept_drafts} drafts "
        f"({stats.zero_size_dropped} zero-size decks and "
        f"{stats.null_skill_excluded_rows} null-skill games in "
        f"{stats.null_skill_excluded_drafts} drafts dropped from "
        f"{stats.total_rows} rows), {stats.n_non_card_columns} metadata columns. "
        f"Wrote {MODEL_TABLE_PARQUET.relative_to(REPO_ROOT).as_posix()}."
    )


if __name__ == "__main__":
    main()
