"""Tests for the game-level modeling table (:mod:`deckbench.table`).

Two layers. A small synthetic gzipped CSV exercises the whole build path fast
and deterministically -- classification, keying, the zero-size-deck drop, the
duplicate-key guard, and byte-level determinism. A handful of ``requires_raw``
checks then run the real build so the acceptance holds on the actual 17Lands
file when it is present (it is not tracked in git).
"""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from deckbench import table

RAW_PRESENT = table.RAW_CSV.exists()
requires_raw = pytest.mark.skipif(not RAW_PRESENT, reason="raw 17Lands CSV not on disk")


# --------------------------------------------------------------------------
# Synthetic fixture: a tiny file with every column family represented.
# --------------------------------------------------------------------------

_META = ["draft_id", "game_time", "match_number", "game_number", "won", "rank"]
# deck_C is deliberately zero everywhere (an unmaindecked card); one row is a
# zero-size deck (all deck_ == 0); the last two rows share (draft_id, game_time)
# and differ only by match_number, exactly the real collision shape.
_HEADER = _META + [
    "deck_Ada, the First",
    "deck_Bob's Bane",
    "deck_Ceceli",
    "sideboard_Ada, the First",
    "opening_hand_Ada, the First",
    "drawn_Ada, the First",
    "tutored_Ada, the First",
]
_ROWS = [
    ["d1", "2026-01-01 10:00:00", "1", "1", "True", "gold", "2", "1", "0", "9", "3", "1", "0"],
    ["d1", "2026-01-01 11:00:00", "2", "1", "False", "gold", "1", "3", "0", "0", "0", "0", "0"],
    ["d2", "2026-01-02 09:00:00", "1", "1", "True", "plat", "2", "2", "0", "5", "2", "0", "0"],
    # zero-size deck -> dropped
    ["d2", "2026-01-02 09:30:00", "2", "1", "False", "plat", "0", "0", "0", "0", "0", "0", "0"],
    # collision pair on (draft_id, game_time), disambiguated by match_number
    ["d3", "2026-01-03 12:00:00", "7", "1", "True", "gold", "4", "0", "0", "0", "0", "0", "0"],
    ["d3", "2026-01-03 12:00:00", "8", "1", "False", "gold", "1", "1", "0", "0", "0", "0", "0"],
]


def _write_gzip_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw = tmp_path / "synthetic.csv.gz"
    _write_gzip_csv(raw, _HEADER, _ROWS)
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps({"recommended_observational_unit": {"unit": "game"}}),
        encoding="utf-8",
    )
    processed = tmp_path / "processed"
    monkeypatch.setattr(table, "RAW_CSV", raw)
    monkeypatch.setattr(table, "AUDIT_JSON", audit)
    monkeypatch.setattr(table, "PROCESSED_DIR", processed)
    monkeypatch.setattr(table, "MODEL_TABLE_PARQUET", processed / "model_table.parquet")
    monkeypatch.setattr(table, "REPORT_MD", tmp_path / "report.md")
    return raw


# --------------------------------------------------------------------------
# Pure-function unit tests (no file needed).
# --------------------------------------------------------------------------


def test_build_layout_uses_prefixes_not_a_card_list() -> None:
    layout = table.build_layout(_HEADER)
    assert layout.deck_columns == (
        "deck_Ada, the First",
        "deck_Bob's Bane",
        "deck_Ceceli",
    )
    # Every non-deck card family is neither a feature nor a metadata column.
    assert layout.non_card_columns == tuple(_META)
    for excluded in ("sideboard_", "opening_hand_", "drawn_", "tutored_"):
        assert not any(c.startswith(excluded) for c in layout.non_card_columns)


def test_build_layout_requires_key_columns() -> None:
    with pytest.raises(KeyError):
        table.build_layout(["draft_id", "game_time", "won"])  # missing match/game number


def test_make_obs_id_stable_and_injective() -> None:
    a = table.make_obs_id(("d1", "t", "1", "1"))
    b = table.make_obs_id(("d1", "t", "1", "1"))
    c = table.make_obs_id(("d1", "t", "2", "1"))
    assert a == b
    assert a != c
    # The separator prevents field-boundary ambiguity.
    assert table.make_obs_id(("a", "b")) != table.make_obs_id(("ab", ""))


def test_parse_count_blank_is_zero_and_garbage_raises() -> None:
    assert table.parse_count("") == 0
    assert table.parse_count("3") == 3
    with pytest.raises(ValueError):
        table.parse_count("two")


def test_missing_raw_file_fails_with_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(table, "RAW_CSV", tmp_path / "absent.csv.gz")
    with pytest.raises(table.RawFileMissing) as excinfo:
        table.open_raw_reader()
    assert "source_manifest.json" in str(excinfo.value)


def test_non_game_unit_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps({"recommended_observational_unit": {"unit": "draft"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(table, "AUDIT_JSON", audit)
    with pytest.raises(table.UnexpectedObservationalUnit):
        table.observational_unit()


# --------------------------------------------------------------------------
# Synthetic end-to-end tests.
# --------------------------------------------------------------------------


def test_zero_size_deck_dropped_and_counted(synthetic: Path) -> None:
    observations, stats = table.collect_observations()
    assert stats.total_rows == len(_ROWS)
    assert stats.zero_size_dropped == 1  # the all-zero deck_ row
    assert stats.kept_rows == len(_ROWS) - 1
    assert len(observations) == stats.kept_rows


def test_deck_size_is_the_deck_column_sum(synthetic: Path) -> None:
    observations, _ = table.collect_observations()
    by_sort = {o.sort_key: o for o in observations}
    # d1/10:00 -> 2 + 1 + 0 = 3
    assert by_sort[("d1", "2026-01-01 10:00:00", 1, 1)].deck_size == 3
    # d3/12:00 match 7 -> 4
    assert by_sort[("d3", "2026-01-03 12:00:00", 7, 1)].deck_size == 4


def test_collision_pair_keeps_both_rows(synthetic: Path) -> None:
    observations, stats = table.collect_observations()
    assert stats.key_collisions == 0  # the 4-tuple key disambiguates them
    ids = [o.obs_id for o in observations]
    assert len(ids) == len(set(ids))  # obs ids unique


def test_duplicate_full_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "dup.csv.gz"
    dup = [
        _ROWS[0],
        list(_ROWS[0]),  # identical 4-tuple key -> genuine collision
    ]
    _write_gzip_csv(raw, _HEADER, dup)
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps({"recommended_observational_unit": {"unit": "game"}}), encoding="utf-8"
    )
    monkeypatch.setattr(table, "RAW_CSV", raw)
    monkeypatch.setattr(table, "AUDIT_JSON", audit)
    with pytest.raises(table.UnresolvableRow):
        table.collect_observations()


def test_model_table_columns_and_one_row_per_observation(synthetic: Path) -> None:
    stats = table.build_model_table()
    tbl = pq.read_table(table.MODEL_TABLE_PARQUET)
    assert tbl.num_rows == stats.kept_rows
    names = tbl.column_names
    assert names[0] == "obs_id"
    assert names[-1] == "deck_size"
    # every metadata column carried, no card-family column carried (deck_size
    # is the computed sum, not a card column, despite its deck_ prefix)
    for meta in _META:
        assert meta in names
    carried = set(names) - {"obs_id", "deck_size"}
    assert not any(c.startswith(fam) for c in carried for fam in table.CARD_FAMILIES)
    obs_ids = tbl.column("obs_id").to_pylist()
    assert len(obs_ids) == len(set(obs_ids))


def test_two_builds_are_byte_identical(synthetic: Path) -> None:
    table.build_model_table()
    first = table.MODEL_TABLE_PARQUET.read_bytes()
    table.build_model_table()
    second = table.MODEL_TABLE_PARQUET.read_bytes()
    assert first == second


# --------------------------------------------------------------------------
# Null-skill exclusion: the modeling population defined here (card 008).
# --------------------------------------------------------------------------

# A synthetic file that carries the two skill-bucket columns, so the exclusion
# has something to key on. d1/d2 have a historical win-rate bucket; d4 is wholly
# null and is excluded together with its whole draft.
_WR_META = [
    "draft_id",
    "game_time",
    "match_number",
    "game_number",
    "won",
    "rank",
    "user_game_win_rate_bucket",
    "user_n_games_bucket",
]
_WR_HEADER = _WR_META + ["deck_Ada, the First", "deck_Bob's Bane"]
_WR_ROWS = [
    ["d1", "2026-01-01 10:00:00", "1", "1", "True", "gold", "0.55", "10", "2", "1"],
    ["d1", "2026-01-01 11:00:00", "2", "1", "False", "gold", "0.55", "10", "1", "3"],
    ["d2", "2026-01-02 09:00:00", "1", "1", "True", "plat", "0.60", "50", "2", "2"],
    # d4: every game null in the win-rate bucket -> the whole draft is excluded
    ["d4", "2026-01-04 09:00:00", "1", "1", "False", "gold", "", "10", "3", "1"],
    ["d4", "2026-01-04 10:00:00", "2", "1", "True", "gold", "", "10", "1", "1"],
]


def _skill_audit(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "recommended_observational_unit": {"unit": "game"},
                "key_columns": {
                    "user_historical_win_rate_bucket": "user_game_win_rate_bucket",
                    "user_games_played_bucket": "user_n_games_bucket",
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def wr_synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw = tmp_path / "wr_synthetic.csv.gz"
    _write_gzip_csv(raw, _WR_HEADER, _WR_ROWS)
    audit = tmp_path / "audit.json"
    _skill_audit(audit)
    monkeypatch.setattr(table, "RAW_CSV", raw)
    monkeypatch.setattr(table, "AUDIT_JSON", audit)
    return raw


def test_null_skill_draft_is_excluded_and_counted(wr_synthetic: Path) -> None:
    observations, stats = table.collect_observations()
    assert stats.skill_bucket_column == "user_game_win_rate_bucket"
    assert stats.total_rows == len(_WR_ROWS)
    assert stats.zero_size_dropped == 0
    assert stats.null_skill_excluded_rows == 2  # d4's two games
    assert stats.null_skill_excluded_drafts == 1  # the draft d4
    assert stats.kept_rows == 3
    assert stats.kept_drafts == 2  # d1, d2
    # d4 is gone entirely; no game of an excluded draft survives.
    assert {o.sort_key[0] for o in observations} == {"d1", "d2"}


def test_population_obs_ids_excludes_null_drafts(wr_synthetic: Path) -> None:
    pop = table.population_obs_ids()
    assert len(pop) == 3
    # The obs ids of the kept rows are exactly the population.
    kept, _ = table.collect_observations()
    assert pop == {o.obs_id for o in kept}


def test_partial_null_draft_fails_naming_the_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Make d4 partially null: one game keeps a bucket. Excluding games and
    # excluding drafts are then no longer the same operation, and the run stops.
    rows = [list(r) for r in _WR_ROWS]
    wr_index = _WR_META.index("user_game_win_rate_bucket")
    rows[3][wr_index] = "0.5"  # d4 game 1 now has a bucket; game 2 still null
    raw = tmp_path / "partial.csv.gz"
    _write_gzip_csv(raw, _WR_HEADER, rows)
    audit = tmp_path / "audit.json"
    _skill_audit(audit)
    monkeypatch.setattr(table, "RAW_CSV", raw)
    monkeypatch.setattr(table, "AUDIT_JSON", audit)
    with pytest.raises(table.PartiallyNullDraft) as excinfo:
        table.collect_observations()
    assert "d4" in str(excinfo.value)


def test_exclusion_is_outcome_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Flipping every `won` value must not change which games are excluded: the
    # criterion is the pre-draft win-rate bucket, never the outcome.
    won_index = _WR_META.index("won")

    def _population(rows: list[list[str]]) -> set[str]:
        raw = tmp_path / f"case_{rows[0][won_index]}.csv.gz"
        _write_gzip_csv(raw, _WR_HEADER, rows)
        audit = tmp_path / "audit.json"
        _skill_audit(audit)
        monkeypatch.setattr(table, "RAW_CSV", raw)
        monkeypatch.setattr(table, "AUDIT_JSON", audit)
        return table.population_obs_ids()

    base = [list(r) for r in _WR_ROWS]
    flipped = [list(r) for r in _WR_ROWS]
    for row in flipped:
        row[won_index] = "False" if row[won_index] == "True" else "True"
    assert _population(base) == _population(flipped)


# --------------------------------------------------------------------------
# Real-data acceptance (skipped when the raw file is absent).
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_stats() -> table.BuildStats:
    observations, stats = table.collect_observations()
    # obs ids are globally unique on the real file
    ids = [o.obs_id for o in observations]
    assert len(ids) == len(set(ids))
    return stats


@requires_raw
def test_real_unit_is_game_from_audit() -> None:
    assert table.observational_unit() == "game"


@requires_raw
def test_real_totals_coherent(real_stats: table.BuildStats) -> None:
    assert real_stats.unit == "game"
    assert real_stats.total_rows > 0
    # The population is the raw rows minus both exclusions (zero-size decks and
    # null-skill drafts); card 008 added the second.
    assert real_stats.kept_rows == (
        real_stats.total_rows
        - real_stats.zero_size_dropped
        - real_stats.null_skill_excluded_rows
    )
    assert real_stats.key_collisions == 0
    assert real_stats.n_deck_columns == 193


@requires_raw
def test_real_null_skill_exclusion_matches_operator_decision(
    real_stats: table.BuildStats,
) -> None:
    # The figures the operator decision rests on, recomputed from the raw file:
    # 166 null-win-rate games in 59 wholly-null drafts, leaving 241,561 games
    # across 43,102 drafts. The code derives these; this test is the acceptance
    # check that they are what the card expected.
    assert real_stats.skill_bucket_column == "user_game_win_rate_bucket"
    assert real_stats.total_rows == 241727
    assert real_stats.zero_size_dropped == 0
    assert real_stats.null_skill_excluded_rows == 166
    assert real_stats.null_skill_excluded_drafts == 59
    assert real_stats.kept_rows == 241561
    assert real_stats.kept_drafts == 43102
