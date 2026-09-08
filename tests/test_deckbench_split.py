"""Tests for the frozen benchmark split (:mod:`deckbench.split`).

The split is checked against the properties the benchmark makes load-bearing:
every observation gets exactly one partition, no draft straddles a partition or
fold boundary, `rank` is never read for grouping, and two runs are byte-identical
with the randomness pinned to a declared seed. The synthetic model table is small
and hand-constructed so the partition and fold arithmetic is checkable by eye.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from deckbench import split

ROOT = Path(__file__).resolve().parent.parent

# --- Synthetic model table --------------------------------------------------
# Ten drafts, two games each, timestamps strictly increasing by draft so the
# time-based holdout cut is unambiguous. With HOLDOUT_FRACTION 0.20 and 10
# drafts, round(2.0) = 2 drafts (the latest two) go to holdout.
_N_DRAFTS = 10


def _synthetic_rows() -> tuple[list[str], list[str], list[str]]:
    obs_ids: list[str] = []
    draft_ids: list[str] = []
    draft_times: list[str] = []
    for i in range(_N_DRAFTS):
        did = f"draft{i:02d}"
        dtime = f"2026-08-{10 + i:02d} 12:00:00"
        for g in range(2):
            obs_ids.append(f"obs{i:02d}{g}")
            draft_ids.append(did)
            draft_times.append(dtime)
    return obs_ids, draft_ids, draft_times


def _write_model_table(path: Path) -> None:
    obs_ids, draft_ids, draft_times = _synthetic_rows()
    table = pa.table(
        {
            "obs_id": pa.array(obs_ids, type=pa.string()),
            "draft_id": pa.array(draft_ids, type=pa.string()),
            "draft_time": pa.array(draft_times, type=pa.string()),
            # rank is present so the "never read" guard actually bites.
            "rank": pa.array(["silver"] * len(obs_ids), type=pa.string()),
            "won": pa.array(["True"] * len(obs_ids), type=pa.string()),
        }
    )
    pq.write_table(table, path, compression="snappy")


def _audit_payload(persistent: bool = False) -> dict[str, object]:
    return {"player_identifier": {"persistent_player_id_exists": persistent}}


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    model_table = processed / "model_table.parquet"
    _write_model_table(model_table)
    # The other manifest members must exist to be hashed; content is irrelevant.
    (processed / "deck_identity.parquet").write_bytes(b"deck-identity-stub")
    (processed / "card_identity_manifest.csv").write_bytes(b"card-manifest-stub")
    (processed / "skill_features.parquet").write_bytes(b"skill-stub")
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps(_audit_payload()), encoding="utf-8")
    split_dir = tmp_path / "data" / "splits"
    report = tmp_path / "split_and_seal.md"

    monkeypatch.setattr(split, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(split, "AUDIT_JSON", audit)
    monkeypatch.setattr(split, "PROCESSED_DIR", processed)
    monkeypatch.setattr(split, "MODEL_TABLE_PARQUET", model_table)
    monkeypatch.setattr(split, "DECK_IDENTITY_PARQUET", processed / "deck_identity.parquet")
    monkeypatch.setattr(split, "CARD_MANIFEST_CSV", processed / "card_identity_manifest.csv")
    monkeypatch.setattr(split, "SKILL_FEATURES_PARQUET", processed / "skill_features.parquet")
    monkeypatch.setattr(split, "MODEL_SPLIT_PARQUET", processed / "model_split.parquet")
    monkeypatch.setattr(split, "SHA256_MANIFEST", processed / "MANIFEST.sha256")
    monkeypatch.setattr(split, "SPLIT_DIR", split_dir)
    monkeypatch.setattr(split, "SPLIT_MANIFEST", split_dir / "split_manifest.json")
    monkeypatch.setattr(split, "REPORT_MD", report)
    return model_table


# --------------------------------------------------------------------------
# Every observation gets exactly one partition; nothing unassigned or doubled.
# --------------------------------------------------------------------------


def test_every_observation_assigned_exactly_one_partition(wired: Path) -> None:
    result = split.build_split()
    assert len(result.partitions) == result.n_obs
    assert set(result.partitions) == {split.DEV, split.HOLDOUT}
    assert result.n_dev_rows + result.n_holdout_rows == result.n_obs
    # No row is unassigned (every entry is one of the two labels).
    for p in result.partitions:
        assert p in (split.DEV, split.HOLDOUT)


def test_partitions_are_draft_disjoint(wired: Path) -> None:
    result = split.build_split()
    dev = {d for d, p in zip(result.draft_ids, result.partitions, strict=True) if p == split.DEV}
    hold = {
        d for d, p in zip(result.draft_ids, result.partitions, strict=True) if p == split.HOLDOUT
    }
    assert dev & hold == set(), "a draft appears in both partitions"


def test_latest_drafts_are_the_holdout(wired: Path) -> None:
    # 10 drafts, 0.20 -> 2 holdout drafts, the two latest by time (draft08, 09).
    result = split.build_split()
    assert result.n_holdout_drafts == 2
    hold = {
        d for d, p in zip(result.draft_ids, result.partitions, strict=True) if p == split.HOLDOUT
    }
    assert hold == {"draft08", "draft09"}
    # The holdout starts strictly after dev ends: a clean time boundary.
    assert result.dev_time_max < result.holdout_time_min


# --------------------------------------------------------------------------
# Folds: every dev row has a fold, no draft spans two folds, holdout has none.
# --------------------------------------------------------------------------


def test_every_dev_row_has_a_fold_and_holdout_has_none(wired: Path) -> None:
    result = split.build_split()
    for p, f in zip(result.partitions, result.folds, strict=True):
        if p == split.DEV:
            assert 0 <= f < result.k_folds
        else:
            assert f == split.HOLDOUT_FOLD


def test_no_draft_spans_two_folds(wired: Path) -> None:
    result = split.build_split()
    by_draft: dict[str, set[int]] = {}
    for d, p, f in zip(result.draft_ids, result.partitions, result.folds, strict=True):
        if p == split.DEV:
            by_draft.setdefault(d, set()).add(f)
    for draft, folds in by_draft.items():
        assert len(folds) == 1, f"draft {draft} spans folds {folds}"


def test_fold_assignment_is_seed_deterministic() -> None:
    # Same (seed, draft) -> same fold; a different seed generally moves it.
    a = split.fold_for("draft42", split.SEED, split.K_FOLDS)
    b = split.fold_for("draft42", split.SEED, split.K_FOLDS)
    assert a == b
    assert 0 <= a < split.K_FOLDS


# --------------------------------------------------------------------------
# rank is never used as a grouping key, player id, or stratifier.
# --------------------------------------------------------------------------


def test_columns_read_excludes_rank(wired: Path) -> None:
    assert "rank" not in split.columns_read()


def test_build_never_requests_rank(wired: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    original = split.pq.read_table

    def spy(path: object, columns: list[str] | None = None, **kw: object) -> object:
        seen.append(list(columns or []))
        return original(path, columns=columns, **kw)

    monkeypatch.setattr(split.pq, "read_table", spy)
    split.build_split()
    assert seen, "build_split did not read the model table"
    for cols in seen:
        assert "rank" not in cols
        assert set(cols) == set(split.columns_read())


# --------------------------------------------------------------------------
# Determinism and the twin pins.
# --------------------------------------------------------------------------


def test_two_builds_are_byte_identical(wired: Path) -> None:
    result = split.build_split()
    split.write_split_parquet(result)
    first = split.MODEL_SPLIT_PARQUET.read_bytes()
    result2 = split.build_split()
    split.write_split_parquet(result2)
    assert split.MODEL_SPLIT_PARQUET.read_bytes() == first


def test_split_manifest_pins_everything_required(wired: Path) -> None:
    split.build()
    manifest = json.loads(split.SPLIT_MANIFEST.read_text(encoding="utf-8"))
    # SHA256 of the parquet, and it is the real hash.
    actual = hashlib.sha256(split.MODEL_SPLIT_PARQUET.read_bytes()).hexdigest()
    assert manifest["split_sha256"] == actual
    # Row counts per partition, fold sizes, rule, reason, seed.
    assert manifest["rows_per_partition"]["dev"] + manifest["rows_per_partition"]["holdout"] == 20
    assert set(manifest["fold_sizes"]) == {"0", "1", "2", "3", "4"}
    assert manifest["rule"] == "time_based_holdout"
    assert isinstance(manifest["reason"], str) and manifest["reason"]
    assert manifest["seed"] == split.SEED
    # The weaker-control finding is recorded, not hidden.
    assert manifest["persistent_player_id_exists"] is False


def test_manifest_reason_records_weaker_leakage_control(wired: Path) -> None:
    split.build()
    manifest = json.loads(split.SPLIT_MANIFEST.read_text(encoding="utf-8"))
    reason = manifest["reason"].lower()
    assert "weaker" in reason
    assert "player" in reason
    # rank is explicitly disavowed as a grouping key.
    assert "rank" in reason


def test_sha256_manifest_root_relative_and_five_members(wired: Path) -> None:
    split.build()
    listed: dict[str, str] = {}
    for line in split.SHA256_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(" *", 1)
        listed[name] = digest
    assert set(listed) == {
        "data/processed/model_table.parquet",
        "data/processed/deck_identity.parquet",
        "data/processed/card_identity_manifest.csv",
        "data/processed/skill_features.parquet",
        "data/processed/model_split.parquet",
    }
    for name in listed:
        assert "/" in name, "manifest regressed to a bare filename"
    for name, digest in listed.items():
        actual = hashlib.sha256((split.REPO_ROOT / name).read_bytes()).hexdigest()
        assert actual == digest, f"manifest hash stale for {name}"


def test_manifest_fails_when_a_member_is_absent(wired: Path) -> None:
    split.build()
    split.SKILL_FEATURES_PARQUET.unlink()
    with pytest.raises(split.ManifestMemberMissing):
        split.write_sha256_manifest()


def test_verify_passes_on_a_fresh_build(wired: Path) -> None:
    split.build()
    split.verify()  # must not raise


def test_verify_fails_when_parquet_tampered(wired: Path) -> None:
    split.build()
    # Corrupt the on-disk parquet; the byte-identity rebuild check must catch it.
    split.MODEL_SPLIT_PARQUET.write_bytes(b"not a parquet")
    with pytest.raises(split.SplitVerificationError):
        split.verify()


# --------------------------------------------------------------------------
# Player-grouped preference: the flag is honoured, and an unnamed column fails.
# --------------------------------------------------------------------------


def test_player_grouped_selected_when_flag_set_but_column_unnamed(
    wired: Path,
) -> None:
    split.AUDIT_JSON.write_text(json.dumps(_audit_payload(persistent=True)), encoding="utf-8")
    with pytest.raises(split.PlayerIdColumnUnknown):
        split.partition_rule()


def test_time_based_rule_when_no_player_id(wired: Path) -> None:
    assert split.partition_rule() == "time_based_holdout"


# --------------------------------------------------------------------------
# Real-data acceptance (read-only; skipped when the model table is absent).
# --------------------------------------------------------------------------

_REAL_PRESENT = split.MODEL_TABLE_PARQUET.exists() and split.AUDIT_JSON.exists()
requires_real = pytest.mark.skipif(
    not _REAL_PRESENT, reason="real model_table.parquet / audit not on disk"
)


@requires_real
def test_real_data_split_is_draft_disjoint_and_sized() -> None:
    # Read-only: build_split does not write, so this touches no tracked file.
    # The split is recomputed on the re-frozen population (card 008): 241,561
    # games across 43,102 drafts, the null-skill drafts already excluded upstream.
    result = split.build_split()
    assert result.n_obs == 241561
    assert result.n_drafts == 43102
    assert result.n_dev_rows + result.n_holdout_rows == result.n_obs
    dev = {d for d, p in zip(result.draft_ids, result.partitions, strict=True) if p == split.DEV}
    hold = {
        d for d, p in zip(result.draft_ids, result.partitions, strict=True) if p == split.HOLDOUT
    }
    assert dev & hold == set()
    # ~20% of drafts held out.
    assert 0.18 < result.holdout_fraction_drafts < 0.22
