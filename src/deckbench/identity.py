"""Build the true card-identity representation from the raw HOB dataset.

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md`` (card 004). The
representation is

    D_ij = count of card j in deck i / deck size i

one row per observation, one column per card, derived from the ``deck_`` column
family. This is the R1 representation the benchmark defines -- and precisely the
one the quarantined pipeline got wrong when it shipped a rank-bucket indicator
matrix under this name (see ``attic/haiku-2026-09-07/README.md``).

Nothing about the card set is hardcoded: the columns are discovered from the
raw header via :mod:`deckbench.table`, the same code that a second set with
different cards would run unchanged. This module never reads the outcome
column; its only inputs are the observation key and the ``deck_`` counts.

Run it with::

    python -m deckbench.identity

which writes ``data/processed/deck_identity.parquet``, the per-card manifest
``data/processed/card_identity_manifest.csv``, and regenerates
``data/processed/MANIFEST.sha256`` over both tables and the manifest.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from deckbench import table
from deckbench.table import (
    DECK_PREFIX,
    PROCESSED_DIR,
    REPO_ROOT,
    Layout,
    build_layout,
    make_obs_id,
    open_raw_reader,
    parse_count,
)

DECK_IDENTITY_PARQUET = PROCESSED_DIR / "deck_identity.parquet"
CARD_MANIFEST_CSV = PROCESSED_DIR / "card_identity_manifest.csv"
SHA256_MANIFEST = PROCESSED_DIR / "MANIFEST.sha256"
REPORT_MD = REPO_ROOT / "reports" / "model_table_build.md"

# Fixed prefix for a cleaned feature name. The card name follows, slugged to a
# safe identifier; the verbatim source column is recorded alongside so the
# clean name round-trips back to the exact original string.
FEATURE_PREFIX = "card_"

# Row sums are integer counts over an integer deck size, so the true value is
# exactly 1. Only float division introduces error; this bound is generous
# against that and any row breaching it fails the run. The worst observed
# deviation is reported so the next card sees the headroom.
ROW_SUM_TOLERANCE = 1e-9

# Fixed precision for the presence fraction in the manifest, so the CSV is
# byte-identical across runs.
FRACTION_NDIGITS = 6

def manifest_members() -> tuple[Path, ...]:
    """The files covered by the sha256 manifest, in a fixed order.

    Resolved lazily (not captured at import) so a rebuild -- or a test that
    redirects the output paths -- always hashes the current artifacts.
    """
    return (CARD_MANIFEST_CSV, DECK_IDENTITY_PARQUET, table.MODEL_TABLE_PARQUET)


class RowSumOutOfTolerance(ValueError):
    """Raised when a card-fraction row does not sum to 1 within tolerance."""


class FeatureNameCollision(ValueError):
    """Raised when two source columns slug to the same clean feature name."""


def clean_feature_name(source_column: str) -> str:
    """Slug a ``deck_<card>`` source column into a safe feature identifier.

    The transform is deterministic and the reverse is recorded (not computed):
    the manifest stores the verbatim source column beside this name, because
    card names carry commas and apostrophes that no slug can round-trip on its
    own. Uniqueness of the slug across the set is enforced by the builder.
    """
    if not source_column.startswith(DECK_PREFIX):
        raise ValueError(f"not a deck column: {source_column!r}")
    card = source_column[len(DECK_PREFIX) :]
    slug = re.sub(r"[^0-9a-z]+", "_", card.lower()).strip("_")
    return f"{FEATURE_PREFIX}{slug}"


def feature_source_columns(header: list[str]) -> tuple[str, ...]:
    """The raw columns this module turns into features: the deck family only.

    Used by the disjointness guard: the outcome column is provably not among
    these, and nothing here derives from wins or losses.
    """
    return build_layout(header).deck_columns


def columns_read(header: list[str]) -> tuple[str, ...]:
    """Every raw column this module reads: the key columns and the deck family.

    The outcome column is not in this set -- the identity builder never touches
    it.
    """
    return table.KEY_COLUMNS + build_layout(header).deck_columns


@dataclass
class IdentityResult:
    """The built representation plus the numbers the report and manifest need."""

    obs_ids: list[str]
    feature_names: list[str]
    source_columns: list[str]
    fractions: np.ndarray
    total_counts: list[int]
    present_counts: list[int]
    n_obs: int
    worst_row_sum_deviation: float


def _feature_names(layout: Layout) -> tuple[list[str], list[str]]:
    """Return (feature_names, source_columns) in header order, enforcing 1-1."""
    source_columns = list(layout.deck_columns)
    feature_names = [clean_feature_name(col) for col in source_columns]
    collisions: dict[str, list[str]] = {}
    for name, col in zip(feature_names, source_columns, strict=True):
        collisions.setdefault(name, []).append(col)
    clashes = {name: cols for name, cols in collisions.items() if len(cols) > 1}
    if clashes:
        raise FeatureNameCollision(
            f"clean feature names are not injective: {clashes}"
        )
    return feature_names, source_columns


def build_representation() -> IdentityResult:
    """Stream the raw file and build the normalized card-fraction matrix.

    Only the observation key and the ``deck_`` counts are read; the outcome and
    every other metadata column are ignored. The modeling population is **not**
    re-derived here: it is taken from :func:`deckbench.table.population_obs_ids`,
    which drops zero-size decks and excludes the null-skill drafts (card 008), so
    this table inherits exactly the model table's obs-id set rather than
    filtering independently. A row whose obs id is not in that population is
    skipped before its fraction is computed, so an excluded row never divides by
    a zero deck size.
    """
    population = table.population_obs_ids()
    handle, reader, header = open_raw_reader()
    try:
        layout = build_layout(header)
        deck_indices = layout.deck_indices
        key_indices = layout.key_indices
        obs_ids: list[str] = []
        sort_keys: list[tuple[str, str, int, int]] = []
        count_rows: list[list[int]] = []
        for row in reader:
            counts = [parse_count(row[i]) for i in deck_indices]
            if sum(counts) == 0:
                continue  # zero-size deck: no representation, dropped upstream
            key_parts = tuple(row[i] for i in key_indices)
            obs_id = make_obs_id(key_parts)
            if obs_id not in population:
                continue  # not in the modeling population (inherited, not re-derived)
            obs_ids.append(obs_id)
            draft_id, game_time, match_no, game_no = key_parts
            sort_keys.append(
                (draft_id, game_time, table._to_int(match_no), table._to_int(game_no))
            )
            count_rows.append(counts)
    finally:
        handle.close()

    feature_names, source_columns = _feature_names(layout)

    order = sorted(range(len(obs_ids)), key=lambda k: sort_keys[k])
    obs_ids = [obs_ids[k] for k in order]
    matrix = np.array([count_rows[k] for k in order], dtype=np.int64)

    n_obs = int(matrix.shape[0])
    deck_sizes = matrix.sum(axis=1)
    fractions = matrix / deck_sizes[:, None]

    row_sums = fractions.sum(axis=1)
    deviations = np.abs(row_sums - 1.0)
    worst = float(deviations.max()) if n_obs else 0.0
    if worst > ROW_SUM_TOLERANCE:
        bad = int(np.argmax(deviations))
        raise RowSumOutOfTolerance(
            f"observation {obs_ids[bad]} card fractions sum to "
            f"{float(row_sums[bad])!r}, off by {worst} > {ROW_SUM_TOLERANCE}"
        )
    if n_obs and float(fractions.min()) < 0.0:
        raise ValueError("a card fraction is negative; deck counts must be >= 0")

    total_counts = [int(v) for v in matrix.sum(axis=0)]
    present_counts = [int(v) for v in (matrix > 0).sum(axis=0)]

    return IdentityResult(
        obs_ids=obs_ids,
        feature_names=feature_names,
        source_columns=source_columns,
        fractions=fractions,
        total_counts=total_counts,
        present_counts=present_counts,
        n_obs=n_obs,
        worst_row_sum_deviation=worst,
    )


def _identity_table(result: IdentityResult) -> pa.Table:
    """Assemble the parquet table: obs_id then one float column per card."""
    columns: dict[str, object] = {
        "obs_id": pa.array(result.obs_ids, type=pa.string())
    }
    for pos, name in enumerate(result.feature_names):
        columns[name] = pa.array(result.fractions[:, pos], type=pa.float64())
    return pa.table(columns)


def write_identity_parquet(result: IdentityResult) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(_identity_table(result), DECK_IDENTITY_PARQUET, compression="snappy")


def write_card_manifest(result: IdentityResult) -> None:
    """Write the per-card manifest CSV in header (feature) order.

    A card that never appears stays in the manifest with a count of zero, so the
    feature space is reproducible from the manifest alone.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    denom = result.n_obs or 1
    with CARD_MANIFEST_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["source_column", "feature_name", "total_count", "fraction_present"]
        )
        for pos, name in enumerate(result.feature_names):
            present_fraction = round(result.present_counts[pos] / denom, FRACTION_NDIGITS)
            writer.writerow(
                [
                    result.source_columns[pos],
                    name,
                    result.total_counts[pos],
                    f"{present_fraction:.{FRACTION_NDIGITS}f}",
                ]
            )


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_sha256_manifest() -> None:
    """Regenerate ``MANIFEST.sha256`` over the three artifacts of this card.

    Written in ``sha256sum`` binary format with bare filenames, so the set is
    verified with ``sha256sum -c MANIFEST.sha256`` from within
    ``data/processed``. This is the tracked pin that lets a rebuild be checked
    byte-for-byte, the role ``frozen_manifest.json`` plays for the graph.
    """
    header = [
        "# Hash manifest for the card-004 modeling artifacts.",
        "#",
        "# The parquet/csv blobs are gitignored and regenerable from data/raw via",
        "#   python -m deckbench.table && python -m deckbench.identity",
        "# This manifest is tracked so a rebuild is checked byte-for-byte. Verify",
        "# from inside data/processed with:  sha256sum -c MANIFEST.sha256",
        "#",
    ]
    lines = [f"{_sha256(path)} *{path.name}" for path in manifest_members()]
    SHA256_MANIFEST.write_text(
        "\n".join(header + lines) + "\n", encoding="utf-8", newline="\n"
    )


def append_report(result: IdentityResult) -> None:
    """Append the identity-representation section to the shared build report."""
    existing = REPORT_MD.read_text(encoding="utf-8") if REPORT_MD.exists() else ""
    n_zero_cards = sum(1 for c in result.total_counts if c == 0)
    section = [
        "",
        "## Card-identity representation",
        "",
        "Card 004, part 2. `deckbench.identity` builds "
        "`D_ij = count(card j in deck i) / deck size i` from the `deck_` family "
        "-- one row per observation, one column per card. It reads only the "
        "observation key and the deck counts; the outcome column is never "
        "touched, so no feature can derive from wins or losses.",
        "",
        f"- Observations (rows): **{result.n_obs}**",
        f"- Card features (columns): **{len(result.feature_names)}**",
        f"- Cards never maindecked (kept at count 0): **{n_zero_cards}**",
        "",
        "### Feature names and reversibility",
        "",
        "Each source column such as `deck_<Name, With A Comma>` (card names carry "
        "commas and apostrophes) becomes a clean identifier such as "
        "`card_name_with_a_comma`. The slug alone cannot "
        "recover the comma and apostrophe, so the manifest "
        "`card_identity_manifest.csv` records the **verbatim source column** "
        "beside every clean name; the mapping is enforced to be one-to-one and "
        "the round trip is tested. A card absent from the whole dataset keeps "
        "its row with `total_count = 0`, so the feature space is reproducible "
        "from the manifest alone.",
        "",
        "### Row-sum tolerance",
        "",
        f"Fractions are integer counts over an integer deck size, so each row's "
        f"true sum is exactly 1; only float division perturbs it. The tolerance "
        f"is **{ROW_SUM_TOLERANCE:g}** and any row breaching it fails the run. "
        f"The worst deviation observed here was "
        f"**{result.worst_row_sum_deviation:.3e}**, well inside the bound.",
        "",
        "### Join and determinism",
        "",
        "`deck_identity.parquet` shares the model table's obs-id set exactly -- "
        "it inherits the population from `deckbench.table.population_obs_ids` "
        "(the zero-size drop and the null-skill exclusion), rather than "
        "re-deriving either -- and is written in the same fixed row order, so the "
        "two join on `obs_id` with no unmatched rows in either direction. Columns "
        "are fixed as `obs_id` then the card features in header order. "
        "`data/processed/MANIFEST.sha256` is regenerated over the model table, "
        "the identity table and the card manifest.",
        "",
    ]
    REPORT_MD.write_text(existing + "\n".join(section), encoding="utf-8", newline="\n")


def build() -> IdentityResult:
    """Build the identity table, the manifest CSV, and refresh the sha manifest."""
    result = build_representation()
    write_identity_parquet(result)
    write_card_manifest(result)
    write_sha256_manifest()
    append_report(result)
    return result


def main() -> None:
    result = build()
    print(
        f"Card-identity representation built: {result.n_obs} observations x "
        f"{len(result.feature_names)} card features "
        f"(worst row-sum deviation {result.worst_row_sum_deviation:.3e}). "
        f"Wrote {DECK_IDENTITY_PARQUET.relative_to(REPO_ROOT).as_posix()}, "
        f"{CARD_MANIFEST_CSV.relative_to(REPO_ROOT).as_posix()} and "
        f"{SHA256_MANIFEST.relative_to(REPO_ROOT).as_posix()}."
    )


if __name__ == "__main__":
    main()
