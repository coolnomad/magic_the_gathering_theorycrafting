"""Tests for the card-identity representation (:mod:`deckbench.identity`).

A synthetic gzipped CSV drives the whole build so the fraction arithmetic,
the join to the model table, the manifest, reversibility of feature names and
byte-determinism are all checked without the 16MB raw file. The anti-hardcoding
and outcome-disjointness guards are the load-bearing ones: they encode the two
lessons from the quarantined pipeline -- the representation must be derived
from the header, not a card list, and no feature may come from the outcome.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from deckbench import identity, table

ROOT = Path(__file__).resolve().parent.parent
RAW_PRESENT = table.RAW_CSV.exists()
requires_raw = pytest.mark.skipif(not RAW_PRESENT, reason="raw 17Lands CSV not on disk")

_META = ["draft_id", "game_time", "match_number", "game_number", "won", "rank"]
_HEADER = _META + [
    "deck_Ada, the First",
    "deck_Bob's Bane",
    "deck_Ceceli",  # never maindecked -> stays in manifest with count 0
    "sideboard_Ada, the First",
    "opening_hand_Ada, the First",
    "drawn_Ada, the First",
    "tutored_Ada, the First",
]
_ROWS = [
    ["d1", "2026-01-01 10:00:00", "1", "1", "True", "gold", "2", "1", "0", "9", "3", "1", "0"],
    ["d2", "2026-01-02 09:00:00", "1", "1", "False", "plat", "0", "5", "0", "0", "0", "0", "0"],
    # zero-size deck -> dropped from both tables
    ["d2", "2026-01-02 09:30:00", "2", "1", "False", "plat", "0", "0", "0", "0", "0", "0", "0"],
    ["d3", "2026-01-03 12:00:00", "7", "1", "True", "gold", "3", "1", "0", "0", "0", "0", "0"],
]


def _write_gzip_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw = tmp_path / "synthetic.csv.gz"
    _write_gzip_csv(raw, _HEADER, _ROWS)
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps({"recommended_observational_unit": {"unit": "game"}}), encoding="utf-8"
    )
    processed = tmp_path / "processed"
    report = tmp_path / "report.md"
    monkeypatch.setattr(table, "RAW_CSV", raw)
    monkeypatch.setattr(table, "AUDIT_JSON", audit)
    monkeypatch.setattr(table, "PROCESSED_DIR", processed)
    monkeypatch.setattr(table, "MODEL_TABLE_PARQUET", processed / "model_table.parquet")
    monkeypatch.setattr(table, "REPORT_MD", report)
    monkeypatch.setattr(identity, "PROCESSED_DIR", processed)
    monkeypatch.setattr(identity, "DECK_IDENTITY_PARQUET", processed / "deck_identity.parquet")
    monkeypatch.setattr(identity, "CARD_MANIFEST_CSV", processed / "card_identity_manifest.csv")
    monkeypatch.setattr(identity, "SHA256_MANIFEST", processed / "MANIFEST.sha256")
    monkeypatch.setattr(identity, "REPORT_MD", report)
    return raw


# --------------------------------------------------------------------------
# Feature-name reversibility and injectivity.
# --------------------------------------------------------------------------


def test_clean_feature_name_is_a_safe_identifier() -> None:
    assert identity.clean_feature_name("deck_Bob's Bane") == "card_bob_s_bane"
    assert identity.clean_feature_name("deck_Ada, the First") == "card_ada_the_first"
    with pytest.raises(ValueError):
        identity.clean_feature_name("sideboard_Ada, the First")


def test_feature_name_collision_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two distinct source columns that slug to the same clean name.
    header = _META + ["deck_Ada, the First", "deck_Ada the First"]
    rows = [["d1", "t", "1", "1", "True", "g", "1", "1"]]
    raw = tmp_path / "clash.csv.gz"
    _write_gzip_csv(raw, header, rows)
    monkeypatch.setattr(table, "RAW_CSV", raw)
    with pytest.raises(identity.FeatureNameCollision):
        identity.build_representation()


# --------------------------------------------------------------------------
# Outcome disjointness: the identity builder never reads `won`.
# --------------------------------------------------------------------------


def test_identity_never_reads_the_outcome_column() -> None:
    read = identity.columns_read(_HEADER)
    features = identity.feature_source_columns(_HEADER)
    assert table.OUTCOME_COL not in read
    assert table.OUTCOME_COL not in features
    assert set(features).isdisjoint({table.OUTCOME_COL})
    # Every column the builder reads is either the key or a deck column.
    for col in read:
        assert col in table.KEY_COLUMNS or col.startswith(table.DECK_PREFIX)


# --------------------------------------------------------------------------
# Anti-hardcoding: no card name, no per-card branch in the module source.
# --------------------------------------------------------------------------


def _card_names() -> list[str]:
    names: list[str] = []
    path = ROOT / "data" / "normalized" / "cards.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            names.append(json.loads(line)["name"])
    return names


def test_identity_source_contains_no_card_name() -> None:
    source = (ROOT / "src" / "deckbench" / "identity.py").read_text(encoding="utf-8").lower()
    found = [name for name in _card_names() if name.lower() in source]
    assert not found, f"card names hardcoded in identity.py: {found[:5]}"


def test_table_source_contains_no_card_name() -> None:
    source = (ROOT / "src" / "deckbench" / "table.py").read_text(encoding="utf-8").lower()
    found = [name for name in _card_names() if name.lower() in source]
    assert not found, f"card names hardcoded in table.py: {found[:5]}"


# --------------------------------------------------------------------------
# End-to-end on the synthetic file.
# --------------------------------------------------------------------------


def test_fractions_nonnegative_and_sum_to_one(wired: Path) -> None:
    result = identity.build_representation()
    assert result.worst_row_sum_deviation <= identity.ROW_SUM_TOLERANCE
    frac = result.fractions
    assert float(frac.min()) >= 0.0
    # d1: deck (2,1,0)/3 -> row sums to 1 exactly in this construction
    assert abs(float(frac.sum(axis=1).min()) - 1.0) <= identity.ROW_SUM_TOLERANCE


def test_identity_columns_are_obs_id_then_features_in_header_order(wired: Path) -> None:
    table.build_model_table()
    result = identity.build()
    tbl = pq.read_table(identity.DECK_IDENTITY_PARQUET)
    assert tbl.column_names == ["obs_id", *result.feature_names]
    assert result.feature_names == [
        "card_ada_the_first",
        "card_bob_s_bane",
        "card_ceceli",
    ]


def test_join_to_model_table_has_no_unmatched_rows(wired: Path) -> None:
    table.build_model_table()
    identity.build()
    mt = pq.read_table(table.MODEL_TABLE_PARQUET, columns=["obs_id"]).column("obs_id").to_pylist()
    di = (
        pq.read_table(identity.DECK_IDENTITY_PARQUET, columns=["obs_id"])
        .column("obs_id")
        .to_pylist()
    )
    assert mt == di  # same order, same set -> no unmatched either direction
    assert len(mt) == len(set(mt))


def test_manifest_records_verbatim_source_and_reverses(wired: Path) -> None:
    table.build_model_table()
    identity.build()
    rows = list(csv.reader(identity.CARD_MANIFEST_CSV.open(encoding="utf-8")))
    assert rows[0] == ["source_column", "feature_name", "total_count", "fraction_present"]
    body = rows[1:]
    assert len(body) == 3  # one row per deck column, header order

    by_feature: dict[str, str] = {}
    for source_column, feature_name, _total, _frac in body:
        # source -> clean is the pure function; clean -> source is the record.
        assert identity.clean_feature_name(source_column) == feature_name
        assert source_column not in by_feature.values()
        by_feature[feature_name] = source_column
    assert len(by_feature) == len(body)  # injective
    # The verbatim source keeps commas and apostrophes intact.
    assert "deck_Bob's Bane" in by_feature.values()
    assert "deck_Ada, the First" in by_feature.values()


def test_unmaindecked_card_kept_at_count_zero(wired: Path) -> None:
    table.build_model_table()
    identity.build()
    rows = list(csv.reader(identity.CARD_MANIFEST_CSV.open(encoding="utf-8")))[1:]
    ceceli = next(r for r in rows if r[0] == "deck_Ceceli")
    assert ceceli[2] == "0"  # total_count
    assert ceceli[3] == "0.000000"  # fraction_present


def test_sha256_manifest_covers_all_three_artifacts(wired: Path) -> None:
    table.build_model_table()
    identity.build()
    listed: dict[str, str] = {}
    for line in identity.SHA256_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(" *", 1)
        listed[name] = digest
    assert set(listed) == {
        "model_table.parquet",
        "deck_identity.parquet",
        "card_identity_manifest.csv",
    }
    for name, digest in listed.items():
        actual = hashlib.sha256((identity.PROCESSED_DIR / name).read_bytes()).hexdigest()
        assert actual == digest, f"manifest hash stale for {name}"


def test_two_builds_are_byte_identical(wired: Path) -> None:
    r1 = identity.build_representation()
    identity.write_identity_parquet(r1)
    identity.write_card_manifest(r1)
    first_parquet = identity.DECK_IDENTITY_PARQUET.read_bytes()
    first_csv = identity.CARD_MANIFEST_CSV.read_bytes()

    r2 = identity.build_representation()
    identity.write_identity_parquet(r2)
    identity.write_card_manifest(r2)
    assert identity.DECK_IDENTITY_PARQUET.read_bytes() == first_parquet
    assert identity.CARD_MANIFEST_CSV.read_bytes() == first_csv


# --------------------------------------------------------------------------
# Real-data acceptance (skipped when the raw file is absent).
# --------------------------------------------------------------------------


@requires_raw
def test_real_representation_is_normalized_and_matches_model_table() -> None:
    result = identity.build_representation()
    assert result.n_obs > 0
    assert len(result.feature_names) == 193
    assert result.worst_row_sum_deviation <= identity.ROW_SUM_TOLERANCE
    assert float(result.fractions.min()) >= 0.0
