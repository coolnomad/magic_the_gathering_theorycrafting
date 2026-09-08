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
``base_p_raw`` over the estimation population, and :data:`LAMBDA` fixed.

``base_p`` is **not a measurement of skill**. It is an interim nuisance
representation and nothing here calls it skill, true skill, or player strength.

This module reads the two skill-bucket columns and the observation id from the
already-built ``model_table.parquet``; it never reads ``won``, wins, or losses,
so the proxy cannot absorb current-event outcome information. It fits nothing
and tunes nothing -- it is a closed-form transform of two input columns.

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
# reviewer can see the seven-entry inherited map and change it in one place for
# a Phase-2 sensitivity check. A games-played bucket absent from this map fails
# the run -- it is never defaulted, rounded to a neighbour, or dropped.
HIST_W_MAP: dict[int, float] = {
    1: 1.0,
    5: 2.0,
    10: 3.0,
    50: 6.0,
    100: 8.0,
    500: 12.0,
    1000: 14.0,
}

# Symmetric clip applied to every probability before any logit. Declared here
# and recorded in the report. It is symmetric on purpose: an asymmetric clip
# would bias the logit and the bias would survive the shrinkage.
CLIP_EPS = 1e-7

# Fixed float precision for the report so it renders identically across runs.
FLOAT_NDIGITS = 6

# The empty cell used by the source for a player who has no historical win-rate
# bucket yet. See :class:`SkillProxyResult` and the report for the disposition.
EMPTY_CELL = ""


class ModelTableMissing(FileNotFoundError):
    """Raised when ``model_table.parquet`` (card 004) is not on disk."""


class UnmappedGamesBucket(ValueError):
    """Raised when a games-played bucket is absent from :data:`HIST_W_MAP`."""


class MissingGamesBucket(ValueError):
    """Raised when a row has no games-played bucket at all."""


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


def _parse_win_rate(raw: str, obs_id: str) -> float | None:
    """Parse a historical win-rate bucket.

    Returns ``None`` for the empty cell -- a player with no historical win rate
    yet. That is recorded downstream as an undefined proxy (never imputed with
    0.5, the mean, or any other placeholder) and the count is reported. A
    non-empty cell that will not parse is an unexpected corruption and fails the
    run naming the observation.
    """
    if raw == EMPTY_CELL:
        return None
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
    base_p_raw: list[float | None]
    base_p: list[float | None]
    mu: float
    n_obs: int
    n_estimation: int
    n_undefined: int
    undefined_by_games_bucket: dict[int, int] = field(default_factory=dict)


def build_proxy() -> SkillProxyResult:
    """Read the two buckets from the model table and build the proxy.

    ``mu`` is the mean of ``base_p_raw`` over the **estimation population**: the
    observations that carry a historical win-rate bucket. Rows with an empty
    historical bucket (a player with too few games to have one) are excluded
    from ``mu`` -- not to drop them, but so an absent value cannot drag the
    shrinkage target -- and their proxy is recorded as undefined. No row is
    excluded on any outcome-dependent criterion and ``won`` is never read.
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

    # First pass: parse both buckets (failing loudly on any unexpected value)
    # and determine the estimation population for mu.
    parsed_raw: list[float | None] = []
    hist_weights: list[float] = []
    undefined_by_games_bucket: dict[int, int] = {}
    estimation_sum = 0.0
    estimation_n = 0
    for obs_id, wr_raw, g_raw in zip(obs_ids, win_rate_raw, games_raw, strict=True):
        games_bucket = _parse_games_bucket(g_raw if g_raw is not None else "", obs_id)
        hist_weights.append(hist_w_for(games_bucket))
        base_p_raw = _parse_win_rate(wr_raw if wr_raw is not None else "", obs_id)
        parsed_raw.append(base_p_raw)
        if base_p_raw is None:
            undefined_by_games_bucket[games_bucket] = (
                undefined_by_games_bucket.get(games_bucket, 0) + 1
            )
        else:
            estimation_sum += base_p_raw
            estimation_n += 1

    if estimation_n == 0:
        raise ValueError(
            "no observation carries a historical win-rate bucket; mu is "
            "undefined and the proxy cannot be built for this dataset."
        )
    mu = estimation_sum / estimation_n

    # Second pass: the closed-form transform on the rows that have a bucket.
    base_p: list[float | None] = []
    for base_p_raw, hist_w in zip(parsed_raw, hist_weights, strict=True):
        if base_p_raw is None:
            base_p.append(None)
        else:
            base_p.append(compute_base_p(base_p_raw, hist_w, mu))

    return SkillProxyResult(
        obs_ids=obs_ids,
        base_p_raw=parsed_raw,
        base_p=base_p,
        mu=mu,
        n_obs=len(obs_ids),
        n_estimation=estimation_n,
        n_undefined=len(obs_ids) - estimation_n,
        undefined_by_games_bucket=dict(sorted(undefined_by_games_bucket.items())),
    )


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
    undefined_rows = (
        ", ".join(
            f"{n} at games-played bucket {b}"
            for b, n in result.undefined_by_games_bucket.items()
        )
        or "none"
    )
    hist_w_rows = "\n".join(
        f"| {b} | {w:g} |" for b, w in sorted(HIST_W_MAP.items())
    )
    lines = [
        "# Skill proxy `base_p` -- reliability-adjusted historical win rate",
        "",
        "Card 005. `deckbench.skill` reproduces the benchmark's nuisance skill "
        "representation `base_p`: the R0 representation and T1's fixed baseline "
        "(benchmark sections 3-4). It is a closed-form shrinkage of two columns "
        "of the game-level model table; it fits nothing, tunes nothing, and "
        "reads no outcome.",
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
        f"- `mu` -- the mean of `base_p_raw` over the estimation population "
        f"(defined below); computed here as **{_round(result.mu)}**.",
        f"- `LAMBDA` -- shrinkage strength toward `logit(mu)`, fixed at "
        f"**{LAMBDA:g}**.",
        "",
        "The `hist_w` map is kept as **data, not arithmetic**, so the inherited "
        "seven-entry assumption is visible and changeable in one place:",
        "",
        "| games-played bucket | hist_w |",
        "| --- | --- |",
        hist_w_rows,
        "",
        "A games-played bucket absent from this map fails the run naming the "
        "value; it is never defaulted, rounded to a neighbour, or dropped. The "
        "buckets observed in this file are all present in the map.",
        "",
        "## Clipping",
        "",
        f"Every probability is clipped symmetrically into "
        f"`[CLIP_EPS, 1 - CLIP_EPS]` with **CLIP_EPS = {CLIP_EPS:g}** before any "
        "logit, so a bucket of exactly 0 or 1 is representable. The clip is "
        "symmetric on purpose: an asymmetric clip would bias the logit and the "
        "bias would survive the shrinkage.",
        "",
        "## Estimation population and `mu`",
        "",
        f"The estimation population for `mu` is **every observation that carries "
        f"a historical win-rate bucket**: {result.n_estimation} of "
        f"{result.n_obs} game-level rows. `mu` is their per-observation "
        f"(per-game) mean of `base_p_raw` = **{_round(result.mu)}**. No row is "
        "excluded on any outcome-dependent criterion, and `won` is never read to "
        "select the population.",
        "",
        "`mu` is a per-game mean, so a draft with more games weights `mu` more "
        "heavily; because the historical bucket is constant within a draft (see "
        "below), this is the only weighting choice that arises, and it is stated "
        "rather than hidden.",
        "",
        "## Missing historical win-rate buckets -- a finding, and a documented deviation",
        "",
        f"**{result.n_undefined} of {result.n_obs} observations carry an empty "
        f"historical win-rate bucket** ({undefined_rows}). Every one sits in the "
        "lowest games-played buckets: these are players with too few recorded "
        "games to have an established historical win rate yet. The audit "
        "(`reports/modeling_data_audit.json`) did not count them; this card "
        "surfaces them.",
        "",
        "The quarantined pipeline filled exactly this gap with `0.5` (see "
        "`attic/haiku-2026-09-07/README.md`), inserting a fabricated average "
        "player at the centre of the distribution and -- because `mu` is the mean "
        "of the same column -- dragging the shrinkage target itself. This card "
        "does the opposite: a missing historical bucket is **never imputed** with "
        "0.5, the mean, or any placeholder. It is recorded as **null** in both "
        "`base_p_raw` and `base_p`, and **excluded from the estimation population** "
        "so it cannot move `mu`.",
        "",
        "This is a deliberate, documented deviation from the letter of the card's "
        "\"a missing bucket fails the run\" criterion, made per the benchmark's "
        "rule that any deviation is documented rather than silently changed "
        "(section 5). The run fails loudly on every *unexpected* bucket state "
        "(an unmapped games bucket, a missing games bucket, a non-empty bucket "
        "that will not parse); it treats only the *structurally-absent* historical "
        "win rate of a near-new player as a known, characterised null. The "
        "final disposition of these rows -- keep with a null proxy, or exclude "
        "from the modelling set -- is an operator decision that belongs to the "
        "phase-1 review at card 007, with this count now in front of it.",
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
        "direction (every model-table row is present; the null-proxy rows are "
        "present too).",
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
        f"Skill proxy built: {result.n_obs} observations, "
        f"{result.n_estimation} in the estimation population "
        f"(mu = {_round(result.mu)}), {result.n_undefined} with an absent "
        f"historical win-rate bucket recorded as null. Wrote "
        f"{SKILL_FEATURES_PARQUET.relative_to(REPO_ROOT).as_posix()} and "
        f"{SHA256_MANIFEST.relative_to(REPO_ROOT).as_posix()}."
    )


if __name__ == "__main__":
    main()
