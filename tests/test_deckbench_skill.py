"""Tests for the reliability-adjusted skill proxy (:mod:`deckbench.skill`).

The proxy is a closed-form transform, so it is checked against **arithmetic**,
not against its own output: the expected ``base_p`` is recomputed by hand in the
test from the written formula. The load-bearing guards encode this card's
centre -- a missing bucket is never imputed with a placeholder, an unmapped
games bucket fails the run, and the module never reads the outcome column, so
the proxy cannot absorb current-event information.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from deckbench import skill

ROOT = Path(__file__).resolve().parent.parent

# --- Synthetic model table --------------------------------------------------
# Three rows in the estimation population plus one with an absent historical
# bucket. base_p_raw over the estimation population is {0.4, 0.6, 0.6} but the
# duplicate 0.6 is chosen so mu is a clean 0.5 only in the two-value case; here
# we keep it simple and assert mu against an explicit mean.
_OBS = ["a", "b", "c", "d"]
_WIN_RATE = ["0.4", "0.6", "0.5", ""]  # d: empty historical bucket -> null
_N_GAMES = ["10", "1000", "50", "1"]  # hist_w 3, 14, 6, 1
_WON = ["True", "False", "True", "True"]  # present so the disjointness test bites


def _write_model_table(path: Path) -> None:
    table = pa.table(
        {
            "obs_id": pa.array(_OBS, type=pa.string()),
            "user_game_win_rate_bucket": pa.array(_WIN_RATE, type=pa.string()),
            "user_n_games_bucket": pa.array(_N_GAMES, type=pa.string()),
            "won": pa.array(_WON, type=pa.string()),
        }
    )
    pq.write_table(table, path, compression="snappy")


def _audit_payload() -> dict[str, object]:
    return {
        "key_columns": {
            "user_historical_win_rate_bucket": "user_game_win_rate_bucket",
            "user_games_played_bucket": "user_n_games_bucket",
        },
        "within_draft": {
            "skill_columns_nonconstant_within_draft": {
                "rank": 5420,
                "user_game_win_rate_bucket": 0,
                "user_n_games_bucket": 0,
            }
        },
    }


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    model_table = processed / "model_table.parquet"
    _write_model_table(model_table)
    # The other manifest members must exist to be hashed; content is irrelevant.
    (processed / "deck_identity.parquet").write_bytes(b"deck-identity-stub")
    (processed / "card_identity_manifest.csv").write_bytes(b"card-manifest-stub")
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps(_audit_payload()), encoding="utf-8")
    report = tmp_path / "skill_proxy.md"

    monkeypatch.setattr(skill, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(skill, "AUDIT_JSON", audit)
    monkeypatch.setattr(skill, "PROCESSED_DIR", processed)
    monkeypatch.setattr(skill, "MODEL_TABLE_PARQUET", model_table)
    monkeypatch.setattr(skill, "DECK_IDENTITY_PARQUET", processed / "deck_identity.parquet")
    monkeypatch.setattr(skill, "CARD_MANIFEST_CSV", processed / "card_identity_manifest.csv")
    monkeypatch.setattr(skill, "SKILL_FEATURES_PARQUET", processed / "skill_features.parquet")
    monkeypatch.setattr(skill, "SHA256_MANIFEST", processed / "MANIFEST.sha256")
    monkeypatch.setattr(skill, "REPORT_MD", report)
    return model_table


# --------------------------------------------------------------------------
# The formula, checked against hand arithmetic.
# --------------------------------------------------------------------------


def _hand_base_p(base_p_raw: float, hist_w: float, mu: float) -> float:
    """Independent re-derivation of the estimator, from the written formula."""

    def clip(p: float) -> float:
        return min(1.0 - skill.CLIP_EPS, max(skill.CLIP_EPS, p))

    def lg(p: float) -> float:
        c = clip(p)
        return math.log(c / (1.0 - c))

    z = (hist_w * lg(base_p_raw) + skill.LAMBDA * lg(mu)) / (hist_w + skill.LAMBDA)
    return 1.0 / (1.0 + math.exp(-z))


def test_base_p_matches_hand_computation(wired: Path) -> None:
    result = skill.build_proxy()
    # mu is the mean of base_p_raw over the estimation population {a, b, c}.
    expected_mu = (0.4 + 0.6 + 0.5) / 3
    assert result.mu == pytest.approx(expected_mu)

    by_id = dict(zip(result.obs_ids, result.base_p, strict=True))
    assert by_id["a"] == pytest.approx(_hand_base_p(0.4, 3.0, expected_mu))
    assert by_id["b"] == pytest.approx(_hand_base_p(0.6, 14.0, expected_mu))
    assert by_id["c"] == pytest.approx(_hand_base_p(0.5, 6.0, expected_mu))


def test_base_p_literal_when_mu_is_one_half() -> None:
    # A fully worked case: mu = 0.5 => logit(mu) = 0, so the shrinkage term
    # vanishes and base_p = invlogit(hist_w/(hist_w+LAMBDA) * logit(base_p_raw)).
    # base_p_raw = 0.4, hist_w = 3, LAMBDA = 5:
    #   logit(0.4) = ln(0.4/0.6) = -0.4054651081
    #   z = 3 * -0.4054651081 / 8 = -0.1520494155
    #   base_p = 1/(1+e^0.1520494155) = 0.4620607112
    got = skill.compute_base_p(base_p_raw=0.4, hist_w=3.0, mu=0.5)
    assert got == pytest.approx(0.4620607112, abs=1e-9)


# --------------------------------------------------------------------------
# Limiting cases: hist_w large -> base_p_raw; hist_w -> 0 -> mu.
# --------------------------------------------------------------------------


def test_large_hist_w_approaches_base_p_raw() -> None:
    got = skill.compute_base_p(base_p_raw=0.62, hist_w=1e9, mu=0.30)
    assert got == pytest.approx(0.62, abs=1e-6)


def test_near_zero_hist_w_approaches_mu() -> None:
    got = skill.compute_base_p(base_p_raw=0.62, hist_w=1e-9, mu=0.30)
    assert got == pytest.approx(0.30, abs=1e-6)


# --------------------------------------------------------------------------
# Symmetric clipping, with the bound as a named constant.
# --------------------------------------------------------------------------


def test_clip_is_symmetric_and_bounded() -> None:
    assert skill.clip_prob(0.0) == skill.CLIP_EPS
    assert skill.clip_prob(1.0) == 1.0 - skill.CLIP_EPS
    assert skill.clip_prob(0.5) == 0.5
    # Symmetry: the clipped logits at the two ends are exact negatives.
    assert skill.logit(0.0) == pytest.approx(-skill.logit(1.0), abs=1e-9)


def test_logit_of_exact_zero_and_one_do_not_raise() -> None:
    assert skill.logit(0.0) < 0.0
    assert skill.logit(1.0) > 0.0


# --------------------------------------------------------------------------
# The centre of the card: missing / unmapped buckets are never defaulted.
# --------------------------------------------------------------------------


def test_unmapped_games_bucket_fails_naming_the_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()
    mt = processed / "model_table.parquet"
    pa_tbl = pa.table(
        {
            "obs_id": pa.array(["x"], type=pa.string()),
            "user_game_win_rate_bucket": pa.array(["0.5"], type=pa.string()),
            "user_n_games_bucket": pa.array(["7"], type=pa.string()),  # 7 not in map
        }
    )
    pq.write_table(pa_tbl, mt)
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps(_audit_payload()), encoding="utf-8")
    monkeypatch.setattr(skill, "MODEL_TABLE_PARQUET", mt)
    monkeypatch.setattr(skill, "AUDIT_JSON", audit)
    with pytest.raises(skill.UnmappedGamesBucket) as exc:
        skill.build_proxy()
    assert "7" in str(exc.value)


def test_missing_games_bucket_fails_naming_the_observation() -> None:
    with pytest.raises(skill.MissingGamesBucket) as exc:
        skill._parse_games_bucket("", "obs-42")
    assert "obs-42" in str(exc.value)


def test_unparseable_win_rate_fails_naming_the_observation() -> None:
    with pytest.raises(skill.UnparseableSkillBucket) as exc:
        skill._parse_win_rate("not-a-number", "obs-99")
    assert "obs-99" in str(exc.value)


def test_absent_historical_bucket_is_null_never_imputed(wired: Path) -> None:
    # Row 'd' has an empty historical win-rate bucket. It must NOT be filled
    # with 0.5, with mu, or with any other value, and must NOT enter mu.
    result = skill.build_proxy()
    by_raw = dict(zip(result.obs_ids, result.base_p_raw, strict=True))
    by_p = dict(zip(result.obs_ids, result.base_p, strict=True))
    assert by_raw["d"] is None
    assert by_p["d"] is None
    assert result.n_undefined == 1
    assert result.undefined_by_games_bucket == {1: 1}
    # mu is the mean over {a, b, c} only; the absent row cannot drag it.
    assert result.n_estimation == 3
    assert result.mu == pytest.approx((0.4 + 0.6 + 0.5) / 3)
    # The absent row is null (asserted above), never the 0.5 or mu placeholder
    # the quarantined pipeline used.
    assert by_p["d"] is None


# --------------------------------------------------------------------------
# Outcome disjointness: the proxy never reads `won`, wins, or losses.
# --------------------------------------------------------------------------


def test_columns_read_excludes_the_outcome(wired: Path) -> None:
    read = skill.columns_read()
    for forbidden in ("won", "wins", "losses"):
        assert forbidden not in read


def test_build_never_requests_the_outcome_column(
    wired: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []
    original = skill.pq.read_table

    def spy(path: object, columns: list[str] | None = None, **kw: object) -> object:
        seen.append(list(columns or []))
        return original(path, columns=columns, **kw)

    monkeypatch.setattr(skill.pq, "read_table", spy)
    skill.build_proxy()
    assert seen, "build_proxy did not read the model table"
    for cols in seen:
        for forbidden in ("won", "wins", "losses"):
            assert forbidden not in cols
        assert set(cols) == set(skill.columns_read())


def test_output_columns_do_not_name_the_proxy_skill(wired: Path) -> None:
    # The card forbids describing base_p as skill / true skill / player strength
    # in the column names. The saved columns are the id and the two proxy values;
    # none is named skill or strength.
    skill.build()
    names = pq.read_table(skill.SKILL_FEATURES_PARQUET).column_names
    assert names == ["obs_id", "base_p_raw", "base_p"]
    for name in names:
        assert "skill" not in name
        assert "strength" not in name


# --------------------------------------------------------------------------
# Outputs: both values saved, complete join, determinism, manifest.
# --------------------------------------------------------------------------


def test_parquet_saves_both_raw_and_shrunk(wired: Path) -> None:
    skill.build()
    tbl = pq.read_table(skill.SKILL_FEATURES_PARQUET)
    assert tbl.column_names == ["obs_id", "base_p_raw", "base_p"]


def test_join_to_model_table_has_no_unmatched_rows(wired: Path) -> None:
    skill.build()
    mt = pq.read_table(skill.MODEL_TABLE_PARQUET, columns=["obs_id"]).column("obs_id").to_pylist()
    sf = (
        pq.read_table(skill.SKILL_FEATURES_PARQUET, columns=["obs_id"])
        .column("obs_id")
        .to_pylist()
    )
    assert mt == sf  # same order, same set -> no unmatched either direction
    assert len(sf) == len(set(sf))


def test_two_builds_are_byte_identical(wired: Path) -> None:
    result = skill.build_proxy()
    skill.write_proxy_parquet(result)
    first = skill.SKILL_FEATURES_PARQUET.read_bytes()
    result2 = skill.build_proxy()
    skill.write_proxy_parquet(result2)
    assert skill.SKILL_FEATURES_PARQUET.read_bytes() == first


def test_manifest_is_root_relative_and_covers_four_members(wired: Path) -> None:
    skill.build()
    listed: dict[str, str] = {}
    for line in skill.SHA256_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(" *", 1)
        listed[name] = digest
    assert set(listed) == {
        "data/processed/model_table.parquet",
        "data/processed/deck_identity.parquet",
        "data/processed/card_identity_manifest.csv",
        "data/processed/skill_features.parquet",
    }
    # Paths are root-relative, not bare filenames.
    for name in listed:
        assert "/" in name
    # And the digests describe the real files.
    for name, digest in listed.items():
        actual = hashlib.sha256((skill.REPO_ROOT / name).read_bytes()).hexdigest()
        assert actual == digest, f"manifest hash stale for {name}"


def test_manifest_fails_when_a_member_is_absent(wired: Path) -> None:
    skill.DECK_IDENTITY_PARQUET.unlink()
    with pytest.raises(skill.ManifestMemberMissing):
        skill.write_sha256_manifest()


def test_skill_column_names_from_audit(wired: Path) -> None:
    assert skill.skill_column_names() == (
        "user_game_win_rate_bucket",
        "user_n_games_bucket",
    )


# --------------------------------------------------------------------------
# Real-data acceptance (read-only; skipped when the model table is absent).
# --------------------------------------------------------------------------

_REAL_PRESENT = skill.MODEL_TABLE_PARQUET.exists() and skill.AUDIT_JSON.exists()
requires_real = pytest.mark.skipif(
    not _REAL_PRESENT, reason="real model_table.parquet / audit not on disk"
)


@requires_real
def test_real_data_counts_and_no_writes() -> None:
    # Read-only: build_proxy does not write, so this touches no tracked file.
    result = skill.build_proxy()
    assert result.n_obs == 241727
    assert result.n_estimation + result.n_undefined == result.n_obs
    # The finding this card surfaces: 166 absent historical win-rate buckets,
    # all in the lowest games-played buckets.
    assert result.n_undefined == 166
    assert set(result.undefined_by_games_bucket) <= {1, 5}
    assert 0.0 < result.mu < 1.0
