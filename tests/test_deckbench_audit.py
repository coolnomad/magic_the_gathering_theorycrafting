"""Tests for the section-17 raw-data audit (:mod:`deckbench.audit`).

These run the real audit against the raw 17Lands file when it is present and
skip cleanly when it is absent (it is not tracked in git). The determinism and
anti-hardcoding checks are the load-bearing ones: card 003 exists to prove the
audit *computes* its numbers rather than restating them, and that card 004 can
consume a stable summary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deckbench import audit

RAW_PRESENT = audit.RAW_CSV.exists()
requires_raw = pytest.mark.skipif(not RAW_PRESENT, reason="raw 17Lands CSV not on disk")


@pytest.fixture(scope="module")
def summary() -> dict[str, object]:
    return audit.run_audit()


def _module_source() -> str:
    return Path(audit.__file__).read_text(encoding="utf-8")


def test_missing_raw_file_fails_with_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit, "RAW_CSV", tmp_path / "absent.csv.gz")
    with pytest.raises(audit.RawFileMissing) as excinfo:
        audit.run_audit()
    message = str(excinfo.value)
    assert "absent.csv.gz" in message
    assert "source_manifest.json" in message


def test_column_classification_uses_prefixes_not_a_list() -> None:
    header = [
        "draft_id",
        "won",
        "deck_Balin, Loremaster",
        "sideboard_Balin, Loremaster",
        "opening_hand_Balin, Loremaster",
        "drawn_Balin, Loremaster",
        "tutored_Balin, Loremaster",
        "draft_time",
    ]
    families = audit._classify_columns(header)
    assert families["deck_"] == ["deck_Balin, Loremaster"]
    assert families["__non_card__"] == ["draft_id", "won", "draft_time"]


def test_deck_digest_is_order_and_value_sensitive() -> None:
    deck_idx = [0, 1, 2]
    d1, total1 = audit._deck_digest(["2", "0", "1"], deck_idx)
    d2, total2 = audit._deck_digest(["2", "0", "1"], deck_idx)
    d3, _ = audit._deck_digest(["1", "0", "2"], deck_idx)
    assert d1 == d2  # stable
    assert total1 == 3 and total2 == 3
    assert d1 != d3  # different vectors, different digest


@requires_raw
def test_totals_are_positive_and_coherent(summary: dict[str, object]) -> None:
    dataset = summary["dataset"]
    assert isinstance(dataset, dict)
    assert dataset["total_games"] > 0
    assert dataset["total_drafts"] > 0
    assert dataset["total_columns"] > 0
    # Every game belongs to exactly one draft: the two row counts must agree.
    within = summary["within_draft"]
    assert isinstance(within, dict)
    assert within["total_games_from_draft_map"] == dataset["total_games"]
    assert within["total_drafts"] == dataset["total_drafts"]


@requires_raw
def test_no_persistent_player_id_claimed(summary: dict[str, object]) -> None:
    player = summary["player_identifier"]
    assert isinstance(player, dict)
    assert player["persistent_player_id_exists"] is False


@requires_raw
def test_required_key_columns_named_and_present(summary: dict[str, object]) -> None:
    key = summary["key_columns"]
    assert isinstance(key, dict)
    assert key["draft_identifier"] == "draft_id"
    assert key["per_game_outcome"] == "won"
    assert key["rank"] == "rank"
    present = key["present"]
    assert isinstance(present, dict)
    # The skill buckets the benchmark section 3 assumes must actually exist.
    assert present["user_game_win_rate_bucket"] is True
    assert present["user_n_games_bucket"] is True


@requires_raw
def test_deck_size_flags_illegal_rows(summary: dict[str, object]) -> None:
    deck_size = summary["deck_size"]
    assert isinstance(deck_size, dict)
    assert deck_size["legal_min_deck_size"] == audit.LEGAL_MIN_DECK_SIZE
    # rows_below_legal_min must equal the total of the flagged illegal buckets.
    illegal = deck_size["illegal_deck_size_counts"]
    assert isinstance(illegal, list)
    assert deck_size["rows_below_legal_min"] == sum(pair[1] for pair in illegal)


@requires_raw
def test_json_report_is_byte_identical_across_two_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "run1"
    second = tmp_path / "run2"
    for out in (first, second):
        out.mkdir()
        monkeypatch.setattr(audit, "REPORTS_DIR", out)
        monkeypatch.setattr(audit, "JSON_REPORT", out / "modeling_data_audit.json")
        monkeypatch.setattr(audit, "MD_REPORT", out / "modeling_data_audit.md")
        audit.write_reports(audit.run_audit())
    a = (first / "modeling_data_audit.json").read_bytes()
    b = (second / "modeling_data_audit.json").read_bytes()
    assert a == b


@requires_raw
def test_module_source_has_no_hardcoded_totals(summary: dict[str, object]) -> None:
    """The observed totals must be computed, never typed into the source."""
    dataset = summary["dataset"]
    assert isinstance(dataset, dict)
    source = _module_source()
    for field in ("total_games", "total_drafts", "total_columns"):
        literal = str(dataset[field])
        assert literal not in source, f"observed {field}={literal} appears as a literal in audit.py"


@requires_raw
def test_emitted_json_matches_run_audit(summary: dict[str, object]) -> None:
    """The written report reflects the same computation the API returns."""
    if not audit.JSON_REPORT.exists():
        pytest.skip("report not yet generated; run `python -m deckbench.audit`")
    on_disk = json.loads(audit.JSON_REPORT.read_text(encoding="utf-8"))
    assert on_disk["dataset"]["total_games"] == summary["dataset"]["total_games"]  # type: ignore[index]
