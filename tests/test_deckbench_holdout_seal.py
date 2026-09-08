"""Tests for the holdout seal (:mod:`deckbench.holdout`).

Every property this card promises is machine-observable, and this is where each
is decided: a tampered split raises, a refused read leaves the ledger
byte-identical, a permitted read appends exactly one line, a repeat is refused
unless flagged, the ledger is append-only, and the unsealed dev path never
returns a holdout row. All reads in these tests go through the module under test,
never around it, and every ledger written here lives in a temp file so the real
`cycle/holdout_ledger.jsonl` is never touched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from deckbench import holdout

ROOT = Path(__file__).resolve().parent.parent


# --- Synthetic split + manifest --------------------------------------------


def _write_split(path: Path) -> None:
    table = pa.table(
        {
            "obs_id": pa.array(["d0", "d1", "h0", "h1"], type=pa.string()),
            "draft_id": pa.array(["da", "db", "hc", "hd"], type=pa.string()),
            "partition": pa.array(["dev", "dev", "holdout", "holdout"], type=pa.string()),
            "fold": pa.array([0, 1, -1, -1], type=pa.int32()),
        }
    )
    pq.write_table(table, path, compression="snappy")


def _write_manifest(manifest_path: Path, split_path: Path) -> None:
    sha = hashlib.sha256(split_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps({"split_sha256": sha}, sort_keys=True) + "\n", encoding="utf-8"
    )


@pytest.fixture
def sealed(tmp_path: Path) -> dict[str, Path]:
    """A valid split + manifest + fresh temp ledger, wired by explicit paths."""
    split_path = tmp_path / "model_split.parquet"
    manifest_path = tmp_path / "split_manifest.json"
    ledger_path = tmp_path / "holdout_ledger.jsonl"
    _write_split(split_path)
    _write_manifest(manifest_path, split_path)
    return {"split": split_path, "manifest": manifest_path, "ledger": ledger_path}


def _load(sealed: dict[str, Path], card_id: str, reason: str, *, repeat: bool = False) -> pa.Table:
    return holdout.load_holdout(
        card_id,
        reason,
        repeat=repeat,
        split_parquet=sealed["split"],
        split_manifest=sealed["manifest"],
        ledger_path=sealed["ledger"],
    )


def _ledger_lines(sealed: dict[str, Path]) -> list[str]:
    if not sealed["ledger"].exists():
        return []
    return [ln for ln in sealed["ledger"].read_text(encoding="utf-8").splitlines() if ln.strip()]


# --------------------------------------------------------------------------
# Fail closed: a tampered split parquet raises HoldoutSealError.
# --------------------------------------------------------------------------


def test_tampered_split_raises_seal_error(sealed: dict[str, Path]) -> None:
    # Tamper a COPY of the split so its bytes no longer match the pinned hash.
    tampered = sealed["split"].with_name("tampered.parquet")
    tampered.write_bytes(sealed["split"].read_bytes() + b"\x00tamper")
    with pytest.raises(holdout.HoldoutSealError):
        holdout.load_holdout(
            "007",
            "attempt after tampering",
            split_parquet=tampered,
            split_manifest=sealed["manifest"],
            ledger_path=sealed["ledger"],
        )
    # And nothing was written to the ledger by a refused read.
    assert _ledger_lines(sealed) == []


def test_missing_manifest_raises_seal_error(sealed: dict[str, Path]) -> None:
    sealed["manifest"].unlink()
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, "007", "manifest gone")
    assert _ledger_lines(sealed) == []


def test_missing_split_parquet_raises_seal_error(sealed: dict[str, Path]) -> None:
    sealed["split"].unlink()
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, "007", "split gone")
    assert _ledger_lines(sealed) == []


# --------------------------------------------------------------------------
# A missing/empty/malformed card id or reason is refused, and writes nothing.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad_id", ["", "   ", "7", "abc", "0007", "07a"])
def test_bad_card_id_refused(sealed: dict[str, Path], bad_id: str) -> None:
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, bad_id, "a good reason")
    assert _ledger_lines(sealed) == []


@pytest.mark.parametrize("bad_reason", ["", "   "])
def test_missing_reason_refused(sealed: dict[str, Path], bad_reason: str) -> None:
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, "007", bad_reason)
    assert _ledger_lines(sealed) == []


def test_refusal_leaves_ledger_byte_identical(sealed: dict[str, Path]) -> None:
    # Seed one permitted read so the ledger is non-empty, then attempt a refused
    # read and assert the ledger is unchanged byte-for-byte.
    _load(sealed, "007", "first legitimate read")
    before = sealed["ledger"].read_bytes()
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, "", "refused: empty card id")
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, "008", "")  # refused: empty reason
    assert sealed["ledger"].read_bytes() == before


# --------------------------------------------------------------------------
# A permitted read appends exactly one well-formed line.
# --------------------------------------------------------------------------


def test_permitted_read_appends_one_line_with_required_fields(
    sealed: dict[str, Path],
) -> None:
    table = _load(sealed, "007", "phase-1 external evaluation")
    lines = _ledger_lines(sealed)
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["card_id"] == "007"
    assert record["reason"] == "phase-1 external evaluation"
    assert record["is_repeat"] is False
    # Timestamp, git commit, and the split hash that was read are all recorded.
    assert record["timestamp"]
    assert record["git_commit"]
    expected_sha = hashlib.sha256(sealed["split"].read_bytes()).hexdigest()
    assert record["split_sha256"] == expected_sha
    # And the returned rows are the holdout partition only.
    assert set(table.column("partition").to_pylist()) == {"holdout"}
    assert table.column("obs_id").to_pylist() == ["h0", "h1"]


# --------------------------------------------------------------------------
# One read per card id by default; a flagged repeat is allowed and recorded.
# --------------------------------------------------------------------------


def test_second_read_same_card_refused_without_repeat(sealed: dict[str, Path]) -> None:
    _load(sealed, "007", "first read")
    before = sealed["ledger"].read_bytes()
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, "007", "second read, no repeat flag")
    # The refused repeat wrote nothing.
    assert sealed["ledger"].read_bytes() == before
    assert len(_ledger_lines(sealed)) == 1


def test_flagged_repeat_allowed_and_marked(sealed: dict[str, Path]) -> None:
    _load(sealed, "007", "first read")
    _load(sealed, "007", "second read after a crashed run", repeat=True)
    lines = _ledger_lines(sealed)
    assert len(lines) == 2
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first["is_repeat"] is False
    assert second["is_repeat"] is True


def test_a_different_card_id_is_not_a_repeat(sealed: dict[str, Path]) -> None:
    _load(sealed, "007", "card 007 read")
    _load(sealed, "008", "card 008 read")  # different card: allowed, not a repeat
    lines = _ledger_lines(sealed)
    assert len(lines) == 2
    assert json.loads(lines[1])["is_repeat"] is False


# --------------------------------------------------------------------------
# The ledger is append-only: earlier lines never change.
# --------------------------------------------------------------------------


def test_ledger_is_append_only(sealed: dict[str, Path]) -> None:
    _load(sealed, "007", "read one")
    after_one = _ledger_lines(sealed)
    _load(sealed, "008", "read two")
    _load(sealed, "007", "read three", repeat=True)
    after_three = _ledger_lines(sealed)
    # Every earlier line survives unchanged, in order, as a prefix.
    assert after_three[: len(after_one)] == after_one
    assert len(after_three) == 3


# --------------------------------------------------------------------------
# load_dev: no ledger, no card id, and never a holdout row.
# --------------------------------------------------------------------------


def test_load_dev_touches_no_ledger_and_needs_no_card_id(sealed: dict[str, Path]) -> None:
    table = holdout.load_dev(split_parquet=sealed["split"])
    assert not sealed["ledger"].exists() or _ledger_lines(sealed) == []
    assert set(table.column("partition").to_pylist()) == {"dev"}


def test_load_dev_never_returns_a_holdout_row(sealed: dict[str, Path]) -> None:
    dev = holdout.load_dev(split_parquet=sealed["split"])
    held = _load(sealed, "007", "get the holdout ids for the disjointness check")
    dev_ids = set(dev.column("obs_id").to_pylist())
    hold_ids = set(held.column("obs_id").to_pylist())
    assert dev_ids & hold_ids == set()


# --------------------------------------------------------------------------
# The seal does not silently swallow a verification failure.
# --------------------------------------------------------------------------


def test_manifest_without_pinned_hash_raises(sealed: dict[str, Path]) -> None:
    sealed["manifest"].write_text(json.dumps({"note": "no hash here"}), encoding="utf-8")
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, "007", "manifest missing its hash")
    assert _ledger_lines(sealed) == []


def test_unparseable_manifest_raises(sealed: dict[str, Path]) -> None:
    sealed["manifest"].write_text("{ not json", encoding="utf-8")
    with pytest.raises(holdout.HoldoutSealError):
        _load(sealed, "007", "manifest corrupt")
    assert _ledger_lines(sealed) == []
