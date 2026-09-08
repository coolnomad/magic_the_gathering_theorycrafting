"""Reproduce the reliability-adjusted skill proxy ``base_p`` (card 005).

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md``. ``base_p`` is the
benchmark's R0 representation and T1's fixed baseline. It is **reproduced, not
improved**: if the skill estimate moved at the same time as the deck
representation, the target-formulation experiment (T0/T1/T2) would measure both
at once and answer neither. The estimator is inherited verbatim from the R
implementation.

The transform is a reliability-weighted shrinkage of a player's historical
game-win-rate bucket toward the population mean, in logit space::

    base_p = invlogit( (hist_w * logit(base_p_raw) + LAMBDA * logit(mu))
                       / (hist_w + LAMBDA) )

with ``base_p_raw`` the historical win-rate bucket, ``hist_w`` set by the
games-played bucket through :data:`HIST_W_MAP`, ``mu`` the mean of
``base_p_raw`` over the modeling population, and :data:`LAMBDA` fixed.

``base_p`` is **not a measurement of skill**. It is an interim nuisance
representation and nothing here calls it skill, true skill, or player strength.

This module reads the two skill-bucket columns and the observation id from the
already-built ``model_table.parquet``; it never reads ``won``, wins, or losses,
so the proxy cannot absorb current-event outcome information. It fits nothing
and tunes nothing -- it is a closed-form transform of two input columns.

The modeling population no longer carries a null win-rate bucket (card 008 moved
that exclusion upstream to :mod:`deckbench.table`). So every row here has a
bucket, ``mu`` is the mean over the whole population, and a null win-rate bucket
in the population is now a defect that **stops the run** -- card 005's
structurally-absent carve-out is gone rather than left dormant. The set of
games-played buckets the run accepts is *derived from the data*; the weight
attached to each is the inherited modeling assumption, declared as data in
:data:`HIST_W_MAP`, and a bucket observed with no declared weight still fails.

Run it with::

    python -m deckbench.skill

which writes ``data/processed/skill_features.parquet`` and rewrites
``data/processed/MANIFEST.sha256`` (with repository-root-relative paths, so it
verifies from the repo root) over card 004's three artifacts plus this one.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

# src/deckbench/skill.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_JSON = REPO_ROOT / "reports" / "modeling_data_audit.json"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MODEL_TABLE_PARQUET = PROCESSED_DIR / "model_table.parquet"
DECK_IDENTITY_PARQUET = PROCESSED_DIR / "deck_identity.parquet"
CARD_MANIFEST_CSV = PROCESSED_DIR / "card_identity_manifest.csv"
SKILL_FEATURES_PARQUET = PROCESSED_DIR / "skill_features.parquet"
SHA256_MANIFEST = PROCESSED_DIR / "MANIFEST.sha256"
REPORT_MD = REPO_ROOT / "reports" / "skill_proxy.md"

# The observation id and the outcome column, matched to the model table so the
# disjointness guard can prove this module never reads the outcome.
OBS_ID_COL = "obs_id"
OUTCOME_COL = "won"

# Shrinkage strength toward the population mean, in logit space. Inherited from
# the R implementation; a modelling assumption, not a derivation.
LAMBDA = 5.0

# Reliability weight of the historical win-rate bucket, keyed by the
# games-played bucket. Declared as DATA, not inlined in the arithmetic, so a
# reviewer can see the inherited map and change it in one place for a Phase-2
# sensitivity check. The keys are exactly the buckets this dataset contains --
# the inherited `1000` entry, which never occurs here, was dropped at card 008
# because it declared a weight for a bucket the data does not have. The *set* of
# accepted buckets is derived from the data at run time (see
# :func:`accepted_games_buckets`); this map supplies the weights, and a games
# bucket observed with no weight fails the run -- it is never defaulted, rounded
# to a neighbour, or dropped.
HIST_W_MAP: dict[int, float] = {
    1: 1.0,
    5: 2.0,
    10: 3.0,
    50: 6.0,
    100: 8.0,
    500: 12.0,
}

# Symmetric clip applied to every probability before any logit. Declared here
# and recorded in the report. It is symmetric on purpose: an asymmetric clip
# would bias the logit and the bias would survive the shrinkage.
CLIP_EPS = 1e-7

# Fixed float precision for the report so it renders identically across runs.
FLOAT_NDIGITS = 6

# The empty cell the source uses for a missing bucket. In the frozen modeling
# population it must not occur: the null-win-rate games were excluded upstream
# (card 008). If one is seen here it is an unexpected defect and stops the run.
EMPTY_CELL = ""


class ModelTableMissing(FileNotFoundError):
    """Raised when ``model_table.parquet`` (card 004) is not on disk."""


class UnmappedGamesBucket(ValueError):
    """Raised when a games-played bucket is absent from :data:`HIST_W_MAP`."""


class MissingGamesBucket(ValueError):
    """Raised when a row has no games-played bucket at all."""


class MissingWinRateBucket(ValueError):
    """Raised when a population row has no historical win-rate bucket.

    The null-win-rate games are excluded from the modeling population upstream
    (card 008), so this must never fire on the frozen data. It is the stricter
    rule that replaced card 005's structurally-absent carve-out: in the
    population, a null win-rate bucket is a defect, not an expected value.
    """


class UnparseableSkillBucket(ValueError):
    """Raised when a non-empty skill bucket cannot be parsed as a number."""


class ManifestMemberMissing(FileNotFoundError):
    """Raised when a file the sha256 manifest must cover is absent."""


def skill_column_names() -> tuple[str, str]:
    """Return ``(win_rate_column, games_played_column)`` from the audit JSON.

    The names are taken from ``reports/modeling_data_audit.json`` rather than
    hardcoded: card 003 established what the skill columns are actually called
    and whether they exist at all. If either is absent from the audit's
    ``key_columns`` block, the run stops rather than guessing a substitute --
    ``rank`` is a skill bucket, not a player id, and is never nominated here.
    """
    if not AUDIT_JSON.exists():
        raise FileNotFoundError(
            f"Audit report not found: {AUDIT_JSON}. Run `python -m deckbench.audit` "
            "first; this card takes the skill column names from it."
        )
    payload = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    key_columns = payload["key_columns"]
    win_rate = key_columns.get("user_historical_win_rate_bucket")
    games_played = key_columns.get("user_games_played_bucket")
    if not isinstance(win_rate, str) or not isinstance(games_played, str):
        raise KeyError(
            "audit JSON does not name both skill buckets "
            "(user_historical_win_rate_bucket, user_games_played_bucket); "
            "card 003 must establish they exist before this card runs. Do not "
            "substitute rank and do not invent a proxy from current-event results."
        )
    return win_rate, games_played


def columns_read() -> tuple[str, ...]:
    """Every model-table column this module reads: the id and the two buckets.

    The outcome column is provably not in this set; the disjointness test asserts
    exactly that.
    """
    win_rate, games_played = skill_column_names()
    return (OBS_ID_COL, win_rate, games_played)


def clip_prob(p: float) -> float:
    """Clip a probability symmetrically into ``[CLIP_EPS, 1 - CLIP_EPS]``."""
    return min(1.0 - CLIP_EPS, max(CLIP_EPS, p))


def logit(p: float) -> float:
    """Logit of ``p`` after the symmetric clip, so 0 and 1 are representable."""
    pc = clip_prob(p)
    return math.log(pc / (1.0 - pc))


def invlogit(z: float) -> float:
    """Inverse logit (logistic)."""
    return 1.0 / (1.0 + math.exp(-z))


def hist_w_for(games_played_bucket: int) -> float:
    """Reliability weight for a games-played bucket, or fail naming the value."""
    try:
        return HIST_W_MAP[games_played_bucket]
    except KeyError as exc:
        raise UnmappedGamesBucket(
            f"games-played bucket {games_played_bucket!r} is absent from the "
            f"hist_w map {sorted(HIST_W_MAP)}; the inherited map is wrong for "
            "this dataset. It is never defaulted, rounded to a neighbour, or "
            "dropped -- report the observed bucket values and stop."
        ) from exc


def compute_base_p(base_p_raw: float, hist_w: float, mu: float) -> float:
    """The closed-form shrinkage. Pure arithmetic on three real inputs.

    ``base_p_raw`` and ``mu`` are clipped symmetrically before the logit; the
    weighted logit-space average is shrunk toward ``logit(mu)`` with weight
    ``LAMBDA`` and mapped back through the logistic.
    """
    numerator = hist_w * logit(base_p_raw) + LAMBDA * logit(mu)
    denominator = hist_w + LAMBDA
    return invlogit(numerator / denominator)


def _parse_games_bucket(raw: str, obs_id: str) -> int:
    """Parse a games-played bucket to an int, failing loudly and by name."""
    if raw == EMPTY_CELL:
        raise MissingGamesBucket(
            f"observation {obs_id} has no games-played bucket; it is never "
            "filled with a placeholder."
        )
    try:
        return int(raw)
    except ValueError as exc:
        raise UnparseableSkillBucket(
            f"observation {obs_id} has an unparseable games-played bucket {raw!r}"
        ) from exc


def _parse_win_rate(raw: str, obs_id: str) -> float:
    """Parse a historical win-rate bucket, failing on any null or garbage.

    In the frozen modeling population every row carries a bucket -- the
    null-win-rate games were excluded upstream (card 008). So an empty cell here
    is not an expected value to carve out; it is a defect that stops the run
    naming the observation. This is the stricter rule that replaced card 005's
    structurally-absent carve-out. A non-empty cell that will not parse is an
    unexpected corruption and likewise fails naming the observation.
    """
    if raw == EMPTY_CELL:
        raise MissingWinRateBucket(
            f"observation {obs_id} has no historical win-rate bucket. Null "
            "buckets are excluded from the modeling population upstream (card "
            "008); one appearing here is a defect, never imputed and never "
            "carved out."
        )
    try:
        return float(raw)
    except ValueError as exc:
        raise UnparseableSkillBucket(
            f"observation {obs_id} has an unparseable win-rate bucket {raw!r}"
        ) from exc


@dataclass
class SkillProxyResult:
    """The built proxy table plus the numbers the report needs."""

    obs_ids: list[str]
    base_p_raw: list[float]
    base_p: list[float]
    mu: float
    n_obs: int
    observed_games_buckets: list[int] = field(default_factory=list)


def build_proxy() -> SkillProxyResult:
    """Read the two buckets from the model table and build the proxy.

    Every population row carries a historical win-rate bucket (the null ones
    were excluded upstream at card 008), so ``mu`` is the mean of ``base_p_raw``
    over the **whole population** and there is no undefined proxy to record. A
    null win-rate bucket in the population fails the run. The set of games-played
    buckets is *derived from the data* -- whatever the population contains -- and
    each must have a declared weight in :data:`HIST_W_MAP` or the run stops
    naming the value. No row is excluded on any outcome-dependent criterion and
    ``won`` is never read.
    """
    if not MODEL_TABLE_PARQUET.exists():
        raise ModelTableMissing(
            f"Model table not found: {MODEL_TABLE_PARQUET}. Build it first with "
            "`python -m deckbench.table && python -m deckbench.identity` (cards 004)."
        )
    win_rate_col, games_played_col = skill_column_names()
    table = pq.read_table(
        MODEL_TABLE_PARQUET, columns=[OBS_ID_COL, win_rate_col, games_played_col]
    )
    obs_ids: list[str] = table.column(OBS_ID_COL).to_pylist()
    win_rate_raw: list[str] = table.column(win_rate_col).to_pylist()
    games_raw: list[str] = table.column(games_played_col).to_pylist()

    # First pass: parse both buckets (failing loudly on any null or unexpected
    # value), gather the observed games-played buckets, and sum for mu.
    base_p_raw: list[float] = []
    hist_weights: list[float] = []
    observed_buckets: set[int] = set()
    population_sum = 0.0
    for obs_id, wr_raw, g_raw in zip(obs_ids, win_rate_raw, games_raw, strict=True):
        games_bucket = _parse_games_bucket(g_raw if g_raw is not None else "", obs_id)
        observed_buckets.add(games_bucket)
        hist_weights.append(hist_w_for(games_bucket))
        raw_value = _parse_win_rate(wr_raw if wr_raw is not None else "", obs_id)
        base_p_raw.append(raw_value)
        population_sum += raw_value

    if not obs_ids:
        raise ValueError(
            "the modeling population is empty; mu is undefined and the proxy "
            "cannot be built."
        )
    mu = population_sum / len(obs_ids)

    # Second pass: the closed-form transform on every row.
    base_p = [
        compute_base_p(raw_value, hist_w, mu)
        for raw_value, hist_w in zip(base_p_raw, hist_weights, strict=True)
    ]

    return SkillProxyResult(
        obs_ids=obs_ids,
        base_p_raw=base_p_raw,
        base_p=base_p,
        mu=mu,
        n_obs=len(obs_ids),
        observed_games_buckets=sorted(observed_buckets),
    )


def accepted_games_buckets(result: SkillProxyResult) -> list[int]:
    """The games-played buckets the run accepted -- derived from the data.

    This is exactly the set observed in the modeling population (every one of
    which had a declared weight, or the build would have failed). It is not a
    hardcoded list; the population determines it, and the report and tests key
    off it.
    """
    return list(result.observed_games_buckets)


def _proxy_table(result: SkillProxyResult) -> pa.Table:
    """Assemble the parquet: obs_id, base_p_raw, base_p (both values saved)."""
    return pa.table(
        {
            OBS_ID_COL: pa.array(result.obs_ids, type=pa.string()),
            "base_p_raw": pa.array(result.base_p_raw, type=pa.float64()),
            "base_p": pa.array(result.base_p, type=pa.float64()),
        }
    )


def write_proxy_parquet(result: SkillProxyResult) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(_proxy_table(result), SKILL_FEATURES_PARQUET, compression="snappy")


def manifest_members() -> tuple[Path, ...]:
    """Files covered by the sha256 manifest, in a fixed order.

    Card 004's three artifacts are preserved and this card's is added. Resolved
    lazily so a rebuild -- or a test redirecting the paths -- hashes the current
    files.
    """
    return (
        MODEL_TABLE_PARQUET,
        DECK_IDENTITY_PARQUET,
        CARD_MANIFEST_CSV,
        SKILL_FEATURES_PARQUET,
    )


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_sha256_manifest() -> None:
    """Rewrite ``MANIFEST.sha256`` with repository-root-relative paths.

    Card 004 wrote bare filenames, so ``sha256sum -c`` only verified from inside
    ``data/processed``. The orchestrator runs every check from the repository
    root, so the paths are written relative to the root
    (``data/processed/model_table.parquet``, not ``model_table.parquet``); then
    ``sha256sum -c data/processed/MANIFEST.sha256`` verifies from where the
    tooling actually runs. All four members must exist, or the run fails naming
    the missing one rather than pinning a partial set.
    """
    members = manifest_members()
    missing = [m for m in members if not m.exists()]
    if missing:
        raise ManifestMemberMissing(
            "cannot write the manifest; these members are absent: "
            + ", ".join(m.relative_to(REPO_ROOT).as_posix() for m in missing)
        )
    header = [
        "# Hash manifest for the card-004 and card-005 modeling artifacts.",
        "#",
        "# The parquet/csv blobs are gitignored and regenerable from data/raw via",
        "#   python -m deckbench.table && python -m deckbench.identity && \\",
        "#   python -m deckbench.skill",
        "# This manifest is tracked so a rebuild is checked byte-for-byte. Paths",
        "# are repository-root-relative; verify from the repository root with:",
        "#   sha256sum -c data/processed/MANIFEST.sha256",
        "#",
    ]
    lines = [
        f"{_sha256(path)} *{path.relative_to(REPO_ROOT).as_posix()}" for path in members
    ]
    SHA256_MANIFEST.write_text(
        "\n".join(header + lines) + "\n", encoding="utf-8", newline="\n"
    )


def _round(value: float) -> float:
    return round(value, FLOAT_NDIGITS)


def _within_draft_note() -> str:
    """Describe skill-column within-draft variation, read from the audit JSON."""
    if not AUDIT_JSON.exists():
        return "Audit JSON absent; within-draft variation not reported."
    payload = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    nonconstant = payload["within_draft"]["skill_columns_nonconstant_within_draft"]
    win_rate_col, games_played_col = skill_column_names()
    wr_var = nonconstant.get(win_rate_col, 0)
    gp_var = nonconstant.get(games_played_col, 0)
    rank_var = nonconstant.get("rank", 0)
    return (
        f"The audit reports the two buckets this card uses are **constant within "
        f"every draft** (`{win_rate_col}` non-constant in {wr_var} drafts, "
        f"`{games_played_col}` in {gp_var}). The proxy is computed per observation "
        f"directly from that observation's own row, so no within-draft "
        f"reconciliation rule is needed: each game inherits its player's buckets "
        f"unchanged. (`rank`, which this card does not use, varies within "
        f"{rank_var} drafts.)"
    )


def write_report(result: SkillProxyResult) -> None:
    """Write the human-readable report for the skill proxy."""
    win_rate_col, games_played_col = skill_column_names()
    hist_w_rows = "\n".join(
        f"| {b} | {w:g} |" for b, w in sorted(HIST_W_MAP.items())
    )
    observed = ", ".join(str(b) for b in result.observed_games_buckets)
    lines = [
        "# Skill proxy `base_p` -- reliability-adjusted historical win rate",
        "",
        "Card 005 (re-frozen at card 008). `deckbench.skill` reproduces the "
        "benchmark's nuisance skill representation `base_p`: the R0 "
        "representation and T1's fixed baseline (benchmark sections 3-4). It is a "
        "closed-form shrinkage of two columns of the game-level model table; it "
        "fits nothing, tunes nothing, and reads no outcome.",
        "",
        "> **`base_p` is not a measurement of skill.** It is an interim nuisance "
        "representation reproduced verbatim from the inherited R implementation so "
        "that the T1-vs-T2 comparison stays interpretable (benchmark section 3). "
        "Nothing here -- code, column names, or prose -- calls it skill, true "
        "skill, or player strength.",
        "",
        f"Source table: `{MODEL_TABLE_PARQUET.relative_to(REPO_ROOT).as_posix()}`",
        f"Output: `{SKILL_FEATURES_PARQUET.relative_to(REPO_ROOT).as_posix()}`",
        "",
        "## The estimator",
        "",
        "```",
        "base_p = invlogit( (hist_w * logit(base_p_raw) + LAMBDA * logit(mu))",
        "                   / (hist_w + LAMBDA) )",
        "```",
        "",
        f"- `base_p_raw` -- the historical game-win-rate bucket, column "
        f"`{win_rate_col}`.",
        f"- `hist_w` -- reliability weight set by the games-played bucket "
        f"(`{games_played_col}`) through the inherited map below.",
        f"- `mu` -- the mean of `base_p_raw` over the modeling population "
        f"(defined below); computed here as **{_round(result.mu)}**.",
        f"- `LAMBDA` -- shrinkage strength toward `logit(mu)`, fixed at "
        f"**{LAMBDA:g}**.",
        "",
        "## Games-played buckets -- observed set and inherited weights",
        "",
        "The set of games-played buckets the run accepts is **derived from the "
        f"data**: the population contains buckets `{{{observed}}}`, and the run "
        "processes exactly those. The *weight* attached to each is the inherited "
        "modeling assumption, kept as **data, not arithmetic**, so it is visible "
        "and changeable in one place:",
        "",
        "| games-played bucket | hist_w |",
        "| --- | --- |",
        hist_w_rows,
        "",
        "A games-played bucket observed with no declared weight fails the run "
        "naming the value; it is never defaulted, rounded to a neighbour, or "
        "dropped. At card 008 the inherited `1000` entry was removed from the "
        "map: it declared a weight for a bucket this dataset does not contain and "
        "so was never exercised. The map's keys are now exactly the buckets the "
        "population presents.",
        "",
        "## Clipping",
        "",
        f"Every probability is clipped symmetrically into "
        f"`[CLIP_EPS, 1 - CLIP_EPS]` with **CLIP_EPS = {CLIP_EPS:g}** before any "
        "logit, so a bucket of exactly 0 or 1 is representable. The clip is "
        "symmetric on purpose: an asymmetric clip would bias the logit and the "
        "bias would survive the shrinkage.",
        "",
        "## Modeling population and `mu`",
        "",
        f"Every one of the **{result.n_obs}** population rows carries a historical "
        "win-rate bucket -- the null-win-rate games were excluded upstream at "
        "card 008, at the point the model table defines the population. So `mu` "
        "is the per-observation (per-game) mean of `base_p_raw` over the **whole "
        f"population** = **{_round(result.mu)}**. No row is excluded on any "
        "outcome-dependent criterion, and `won` is never read to select the "
        "population.",
        "",
        "This value is unchanged from the pre-008 freeze (`mu = 0.546211`). That "
        "is expected, not a coincidence: card 005 already computed `mu` over the "
        "rows that carried a bucket -- the same 241,561 rows that now constitute "
        "the whole population -- so removing the 166 null-bucket games removed "
        "exactly the rows that were never in the mean. The old and new `mu` "
        "coincide by construction.",
        "",
        "`mu` is a per-game mean, so a draft with more games weights `mu` more "
        "heavily; because the historical bucket is constant within a draft (see "
        "below), this is the only weighting choice that arises, and it is stated "
        "rather than hidden.",
        "",
        "## No null win-rate buckets (card 008 removed the carve-out)",
        "",
        "Card 005 permitted a structurally-absent historical win-rate bucket as a "
        "counted null, because failing on it would have made that card's own "
        "output unsatisfiable. Card 008 excluded those games from the modeling "
        "population upstream, so the branch is unreachable -- and unreachable "
        "safety behaviour is worse than none. It is **removed**: a null win-rate "
        "bucket in the population is now a defect that stops the run naming the "
        "observation, restoring the original intent of card 005's criterion that "
        "any null in the population is a defect. The quarantined pipeline filled "
        "exactly this gap with `0.5` (see `attic/haiku-2026-09-07/README.md`), "
        "dragging the shrinkage target with a fabricated average player; nothing "
        "here imputes a missing bucket with 0.5, the mean, or any placeholder.",
        "",
        "## Within-draft variation of the skill columns",
        "",
        _within_draft_note(),
        "",
        "## Outputs and provenance",
        "",
        f"- `skill_features.parquet` -- columns `{OBS_ID_COL}`, `base_p_raw`, "
        "`base_p`. **Both** the input bucket and the shrunk value are saved, not "
        "just the shrunk value. Keyed on the observation id; it joins to "
        "`model_table.parquet` on that id with no unmatched rows in either "
        "direction -- both tables carry exactly the modeling population, and "
        "neither `base_p_raw` nor `base_p` contains a null.",
        "- The proxy is emitted as its own table rather than mutating "
        "`model_table.parquet`, so card 004's artifact stays byte-stable and the "
        "provenance stays legible.",
        "- `MANIFEST.sha256` is rewritten with repository-root-relative paths "
        "over card 004's three artifacts and this card's, so "
        "`sha256sum -c data/processed/MANIFEST.sha256` verifies from the "
        "repository root.",
        "",
        "## Determinism",
        "",
        "The transform is closed-form Python arithmetic in a fixed row order "
        "(the model table's order), so two consecutive runs produce a "
        "byte-identical parquet. The hash is pinned in "
        "`data/processed/MANIFEST.sha256`.",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def build() -> SkillProxyResult:
    """Build the proxy table, rewrite the sha manifest, and write the report."""
    result = build_proxy()
    write_proxy_parquet(result)
    write_sha256_manifest()
    write_report(result)
    return result


def main() -> None:
    result = build()
    print(
        f"Skill proxy built: {result.n_obs} observations, mu = "
        f"{_round(result.mu)}, over games-played buckets "
        f"{result.observed_games_buckets} (no null win-rate buckets remain). "
        f"Wrote {SKILL_FEATURES_PARQUET.relative_to(REPO_ROOT).as_posix()} and "
        f"{SHA256_MANIFEST.relative_to(REPO_ROOT).as_posix()}."
    )


if __name__ == "__main__":
    main()
