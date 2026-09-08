"""Freeze the one train/test split every benchmark model will share (card 006).

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md`` (sections 7 and 17).
This module partitions the game-level model table into a **development** set and
an **external holdout**, assigns cross-fitting folds inside development, writes
the assignment once, and pins it by hash. It fits nothing, builds no feature, and
computes no metric -- it produces a partition and, together with
:mod:`deckbench.holdout`, a gate.

The split is a deterministic function of the model table it reads and the
declared seed, so the modeling population is defined entirely upstream: card 008
excluded the null-skill drafts in :mod:`deckbench.table`, and this module simply
reads the already-excluded ``model_table.parquet`` and **recomputes** the split
on that population -- the holdout fraction and the five fold sizes are derived
fresh, never filtered down from an earlier split. Re-running it after the
re-freeze is all that is needed to re-derive the split byte-for-byte.

The partitioning rules the benchmark fixes, and how this card follows them:

* **Split by draft, never by game row** (section 7). Every partition and every
  fold is assigned at the ``draft_id`` level, so no draft's games straddle a
  boundary. This is asserted by test, not merely intended.
* **Preference order for the grouping key** (section 7). If card 003 had found a
  persistent player identifier, the split would group by it so the same player
  could not appear on both sides. The audit
  (``reports/modeling_data_audit.json``) records that **no persistent player
  identifier exists**, so the fallback applies: a time-based external holdout of
  approximately the latest 20 percent of drafts. That is a weaker leakage
  control than player grouping -- the same player can appear in both partitions
  under different drafts -- and the manifest says so rather than presenting the
  two as equivalent.
* **``rank`` is never a grouping key, a player id, or a stratifier.** ``rank`` is
  a six-level skill bucket, not a player id (audit ``player_identifier``). This
  module never reads it; :func:`columns_read` is the whole set of model-table
  columns it touches, and a test asserts ``rank`` is not among them.

Run it with::

    python -m deckbench.split            # build and pin
    python -m deckbench.split --verify   # rebuild and check byte-identity

which writes ``data/processed/model_split.parquet``,
``data/splits/split_manifest.json``, refreshes
``data/processed/MANIFEST.sha256`` (repository-root-relative paths), and writes
``reports/split_and_seal.md``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

# src/deckbench/split.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_JSON = REPO_ROOT / "reports" / "modeling_data_audit.json"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MODEL_TABLE_PARQUET = PROCESSED_DIR / "model_table.parquet"
DECK_IDENTITY_PARQUET = PROCESSED_DIR / "deck_identity.parquet"
CARD_MANIFEST_CSV = PROCESSED_DIR / "card_identity_manifest.csv"
SKILL_FEATURES_PARQUET = PROCESSED_DIR / "skill_features.parquet"
MODEL_SPLIT_PARQUET = PROCESSED_DIR / "model_split.parquet"
SHA256_MANIFEST = PROCESSED_DIR / "MANIFEST.sha256"
SPLIT_DIR = REPO_ROOT / "data" / "splits"
SPLIT_MANIFEST = SPLIT_DIR / "split_manifest.json"
REPORT_MD = REPO_ROOT / "reports" / "split_and_seal.md"

# The three model-table columns this module reads. The outcome column and, in
# particular, ``rank`` are provably not in this set; the split is drawn from the
# observation id, the draft it belongs to, and the draft's timestamp -- nothing
# else. The disjointness test asserts exactly this.
OBS_ID_COL = "obs_id"
DRAFT_ID_COL = "draft_id"
DRAFT_TIME_COL = "draft_time"

# Partition labels. ``dev`` is everything the modelling phase may look at freely;
# ``holdout`` is opened only through the sealed path in :mod:`deckbench.holdout`.
DEV = "dev"
HOLDOUT = "holdout"

# The fold sentinel for a holdout row: it carries no cross-fitting fold, because
# cross-fitting happens inside development only.
HOLDOUT_FOLD = -1

# Fraction of drafts held out as the external test set. Approximately the latest
# 20 percent by draft time (benchmark section 7's time-based fallback). Declared
# here so the target is visible and changeable in one place.
HOLDOUT_FRACTION = 0.20

# Number of cross-fitting folds inside development (benchmark section 3's T2
# cross-fitting). Declared, recorded in the manifest.
K_FOLDS = 5

# The seed for the fold assignment. Fold membership is a deterministic hash of
# ``(SEED, draft_id)`` -- there is no RNG state to carry -- so two runs produce a
# byte-identical parquet. The seed is recorded in the manifest so the assignment
# is reproducible and auditable.
SEED = 20260908


class ModelTableMissing(FileNotFoundError):
    """Raised when ``model_table.parquet`` (card 004) is not on disk."""


class ManifestMemberMissing(FileNotFoundError):
    """Raised when a file the sha256 manifest must cover is absent."""


class PlayerIdColumnUnknown(ValueError):
    """Raised when the audit claims a player id exists but names no column.

    The benchmark prefers player-grouped splitting when a persistent player
    identifier exists. The audit for this dataset records that none does, so the
    time-based fallback is taken. This guard exists so that if a future audit
    flips the flag without naming the column, the run stops rather than silently
    grouping by the wrong thing.
    """


class SplitVerificationError(RuntimeError):
    """Raised by ``--verify`` when the on-disk split is not reproducible."""


def columns_read() -> tuple[str, ...]:
    """Every model-table column this module reads: id, draft id, draft time.

    ``rank`` and the outcome column are provably not in this set; the
    disjointness test asserts it.
    """
    return (OBS_ID_COL, DRAFT_ID_COL, DRAFT_TIME_COL)


def _persistent_player_id_exists() -> bool:
    """Read from the audit whether a persistent player identifier exists.

    The split's grouping key follows the benchmark's preference order, and the
    branch point is this audited fact -- not a guess made here.
    """
    if not AUDIT_JSON.exists():
        raise FileNotFoundError(
            f"Audit report not found: {AUDIT_JSON}. Run `python -m deckbench.audit` "
            "first; this card takes the player-identifier finding from it."
        )
    payload = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    return bool(payload["player_identifier"]["persistent_player_id_exists"])


def partition_rule() -> str:
    """Return the grouping rule chosen for this dataset, per the audit.

    ``player_grouped`` if a persistent player id exists, else
    ``time_based_holdout``. The player-grouped branch requires a nominated id
    column in the audit; absent one, it fails rather than guessing.
    """
    if _persistent_player_id_exists():
        payload = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        column = payload["player_identifier"].get("player_id_column")
        if not isinstance(column, str) or not column:
            raise PlayerIdColumnUnknown(
                "audit says a persistent player identifier exists but names no "
                "player_id_column; refusing to guess a grouping key. Nominate the "
                "column in the audit before using the player-grouped split."
            )
        return "player_grouped"
    return "time_based_holdout"


def fold_for(draft_id: str, seed: int, k: int) -> int:
    """Deterministic cross-fitting fold for a dev draft.

    A hash of ``(seed, draft_id)`` reduced mod ``k``. Keyed on the draft, so
    every game of a draft lands in the same fold and no draft spans two folds.
    Deterministic given the seed, so the parquet is byte-reproducible.
    """
    digest = hashlib.blake2b(f"{seed}:{draft_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % k


@dataclass
class SplitResult:
    """The per-observation assignment plus the numbers the manifest needs."""

    obs_ids: list[str]
    draft_ids: list[str]
    partitions: list[str]
    folds: list[int]
    rule: str
    seed: int
    k_folds: int
    n_obs: int
    n_drafts: int
    n_dev_drafts: int
    n_holdout_drafts: int
    n_dev_rows: int
    n_holdout_rows: int
    holdout_fraction_drafts: float
    holdout_fraction_rows: float
    dev_time_min: str
    dev_time_max: str
    holdout_time_min: str
    holdout_time_max: str
    persistent_player_id_exists: bool
    fold_sizes: dict[int, int] = field(default_factory=dict)


def build_split() -> SplitResult:
    """Read the model table and assign each observation a partition and fold.

    Only ``obs_id``, ``draft_id`` and ``draft_time`` are read. Drafts are ordered
    by their timestamp; the latest ~20 percent become the external holdout; the
    remainder are development and each draft is hashed into one of ``K_FOLDS``
    folds. Row order is the model table's own order, so the parquet is
    byte-reproducible and joins to it on ``obs_id`` unchanged.
    """
    if not MODEL_TABLE_PARQUET.exists():
        raise ModelTableMissing(
            f"Model table not found: {MODEL_TABLE_PARQUET}. Build it first with "
            "`python -m deckbench.table` (card 004)."
        )
    rule = partition_rule()
    if rule != "time_based_holdout":
        raise PlayerIdColumnUnknown(
            f"grouping rule {rule!r} is selected but only the time-based holdout "
            "is implemented for this dataset; a player-grouped split needs the "
            "nominated id column wired through."
        )
    persistent = _persistent_player_id_exists()

    table = pq.read_table(MODEL_TABLE_PARQUET, columns=list(columns_read()))
    obs_ids: list[str] = table.column(OBS_ID_COL).to_pylist()
    draft_ids: list[str] = table.column(DRAFT_ID_COL).to_pylist()
    draft_times: list[str] = table.column(DRAFT_TIME_COL).to_pylist()

    # One representative timestamp per draft. draft_time is constant within a
    # draft in this file; taking the min is deterministic either way and never
    # lets a single draft straddle the time cut, because the whole draft is
    # assigned by this one value.
    rep_time: dict[str, str] = {}
    for did, dtime in zip(draft_ids, draft_times, strict=True):
        prev = rep_time.get(did)
        if prev is None or dtime < prev:
            rep_time[did] = dtime

    # Order drafts by (time, draft_id). Timestamps are 'YYYY-MM-DD HH:MM:SS', so
    # lexicographic order is chronological. draft_id breaks ties deterministically.
    ordered_drafts = sorted(rep_time, key=lambda d: (rep_time[d], d))
    n_drafts = len(ordered_drafts)
    n_holdout_drafts = round(HOLDOUT_FRACTION * n_drafts)
    # Guard the degenerate ends so both partitions are non-empty.
    n_holdout_drafts = max(1, min(n_drafts - 1, n_holdout_drafts))
    holdout_drafts = set(ordered_drafts[n_drafts - n_holdout_drafts :])

    partitions: list[str] = []
    folds: list[int] = []
    fold_sizes: dict[int, int] = {f: 0 for f in range(K_FOLDS)}
    n_dev_rows = 0
    n_holdout_rows = 0
    for did in draft_ids:
        if did in holdout_drafts:
            partitions.append(HOLDOUT)
            folds.append(HOLDOUT_FOLD)
            n_holdout_rows += 1
        else:
            fold = fold_for(did, SEED, K_FOLDS)
            partitions.append(DEV)
            folds.append(fold)
            fold_sizes[fold] += 1
            n_dev_rows += 1

    dev_reps = [rep_time[d] for d in ordered_drafts if d not in holdout_drafts]
    holdout_reps = [rep_time[d] for d in ordered_drafts if d in holdout_drafts]
    n_obs = len(obs_ids)

    return SplitResult(
        obs_ids=obs_ids,
        draft_ids=draft_ids,
        partitions=partitions,
        folds=folds,
        rule=rule,
        seed=SEED,
        k_folds=K_FOLDS,
        n_obs=n_obs,
        n_drafts=n_drafts,
        n_dev_drafts=n_drafts - n_holdout_drafts,
        n_holdout_drafts=n_holdout_drafts,
        n_dev_rows=n_dev_rows,
        n_holdout_rows=n_holdout_rows,
        holdout_fraction_drafts=round(n_holdout_drafts / n_drafts, 6) if n_drafts else 0.0,
        holdout_fraction_rows=round(n_holdout_rows / n_obs, 6) if n_obs else 0.0,
        dev_time_min=min(dev_reps) if dev_reps else "",
        dev_time_max=max(dev_reps) if dev_reps else "",
        holdout_time_min=min(holdout_reps) if holdout_reps else "",
        holdout_time_max=max(holdout_reps) if holdout_reps else "",
        persistent_player_id_exists=persistent,
        fold_sizes=dict(sorted(fold_sizes.items())),
    )


def _split_table(result: SplitResult) -> pa.Table:
    """Assemble the parquet: obs_id, draft_id, partition, fold (fixed order)."""
    return pa.table(
        {
            OBS_ID_COL: pa.array(result.obs_ids, type=pa.string()),
            DRAFT_ID_COL: pa.array(result.draft_ids, type=pa.string()),
            "partition": pa.array(result.partitions, type=pa.string()),
            "fold": pa.array(result.folds, type=pa.int32()),
        }
    )


def write_split_parquet(result: SplitResult) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(_split_table(result), MODEL_SPLIT_PARQUET, compression="snappy")


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_split_manifest(result: SplitResult) -> None:
    """Pin the split parquet by hash and record the contract that made it.

    This is the manifest the seal (:mod:`deckbench.holdout`) verifies before it
    will return a single holdout row. It pins the split parquet's SHA256, the row
    count per partition, the fold sizes, the rule chosen, the reason, and the
    seed -- the frozen contract that survives in git even though the parquet it
    describes is gitignored.
    """
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    reason = (
        "No persistent player identifier exists in the dataset (see "
        "reports/modeling_data_audit.json player_identifier), so the benchmark's "
        "preferred player-grouped split is not available. The fallback is a "
        "time-based external holdout of approximately the latest "
        f"{int(round(HOLDOUT_FRACTION * 100))} percent of drafts by draft_time. "
        "This is a weaker leakage control than player grouping: the same player "
        "can appear in both partitions under different drafts, and is not treated "
        "as equivalent to a player-grouped split. rank is a skill bucket, not a "
        "player id, and is used nowhere as a grouping key, player id, or "
        "stratifier."
    )
    manifest = {
        "split_parquet": MODEL_SPLIT_PARQUET.relative_to(REPO_ROOT).as_posix(),
        "split_sha256": _sha256(MODEL_SPLIT_PARQUET),
        "rule": result.rule,
        "reason": reason,
        "seed": result.seed,
        "k_folds": result.k_folds,
        "holdout_fraction_target": HOLDOUT_FRACTION,
        "persistent_player_id_exists": result.persistent_player_id_exists,
        "n_obs": result.n_obs,
        "n_drafts": result.n_drafts,
        "rows_per_partition": {DEV: result.n_dev_rows, HOLDOUT: result.n_holdout_rows},
        "drafts_per_partition": {
            DEV: result.n_dev_drafts,
            HOLDOUT: result.n_holdout_drafts,
        },
        "holdout_fraction_drafts": result.holdout_fraction_drafts,
        "holdout_fraction_rows": result.holdout_fraction_rows,
        "fold_sizes": {str(f): n for f, n in result.fold_sizes.items()},
        "dev_time_range": [result.dev_time_min, result.dev_time_max],
        "holdout_time_range": [result.holdout_time_min, result.holdout_time_max],
    }
    SPLIT_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def manifest_members() -> tuple[Path, ...]:
    """Files covered by ``MANIFEST.sha256``, in a fixed order.

    Cards 004 and 005 left four artifacts; this card adds the split parquet as a
    fifth, so ``MANIFEST.sha256`` covers every derived artifact uniformly.
    Resolved lazily so a rebuild -- or a test redirecting paths -- hashes the
    current files.
    """
    return (
        MODEL_TABLE_PARQUET,
        DECK_IDENTITY_PARQUET,
        CARD_MANIFEST_CSV,
        SKILL_FEATURES_PARQUET,
        MODEL_SPLIT_PARQUET,
    )


def write_sha256_manifest() -> None:
    """Rewrite ``MANIFEST.sha256`` with repository-root-relative paths.

    Card 005 rewrote this file with root-relative paths precisely so that
    ``sha256sum -c data/processed/MANIFEST.sha256`` exits zero when run from the
    repository root (the orchestrator runs every check there, ``shell=False``).
    This card keeps that format and adds ``model_split.parquet`` as a fifth
    member. All members must exist, or the run fails naming the missing one.
    """
    members = manifest_members()
    missing = [m for m in members if not m.exists()]
    if missing:
        raise ManifestMemberMissing(
            "cannot write the manifest; these members are absent: "
            + ", ".join(m.relative_to(REPO_ROOT).as_posix() for m in missing)
        )
    header = [
        "# Hash manifest for the card-004, card-005 and card-006 modeling artifacts.",
        "#",
        "# The parquet/csv blobs are gitignored and regenerable from data/raw via",
        "#   python -m deckbench.table && python -m deckbench.identity && \\",
        "#   python -m deckbench.skill && python -m deckbench.split",
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


def write_report(result: SplitResult) -> None:
    """Write the human-readable report for the split and the seal."""
    fold_rows = "\n".join(
        f"| {f} | {n} |" for f, n in result.fold_sizes.items()
    )
    lines = [
        "# Split and seal -- the frozen benchmark partition",
        "",
        "Card 006. `deckbench.split` freezes the one train/test split every model "
        "in the benchmark will share, and `deckbench.holdout` makes the external "
        "holdout mechanically hard to read by accident. No feature is built, no "
        "model is fit, and no metric is computed here (benchmark sections 7, 17).",
        "",
        f"Source table: `{MODEL_TABLE_PARQUET.relative_to(REPO_ROOT).as_posix()}`",
        f"Split output: `{MODEL_SPLIT_PARQUET.relative_to(REPO_ROOT).as_posix()}`",
        f"Split manifest: `{SPLIT_MANIFEST.relative_to(REPO_ROOT).as_posix()}`",
        "",
        "## The grouping rule and why",
        "",
        "The benchmark (section 7) prefers a player-grouped split so the same "
        "player cannot appear on both sides. The audit "
        "(`reports/modeling_data_audit.json`) records that **no persistent player "
        f"identifier exists** in this dataset "
        f"(`persistent_player_id_exists = {str(result.persistent_player_id_exists).lower()}`), "
        "so that preferred control is unavailable. The chosen rule is therefore "
        f"**`{result.rule}`**: drafts are ordered by `draft_time` and the latest "
        f"~{int(round(HOLDOUT_FRACTION * 100))} percent become the external "
        "holdout.",
        "",
        "> **This is a weaker leakage control than player grouping.** With no "
        "player id, the same player can appear in both the development set and the "
        "holdout under different drafts. A time-based holdout is not treated as "
        "equivalent to a player-grouped split; it is the strongest available "
        "control given the data, and its weakness is recorded here and in the "
        "split manifest.",
        "",
        "`rank` is a six-level skill bucket, not a player id (audit "
        "`player_identifier`). It is used **nowhere** in this card as a grouping "
        "key, a player identifier, or a stratifier; the split module reads only "
        f"`{', '.join(columns_read())}`.",
        "",
        "## Split by draft, never by game row",
        "",
        "Every partition and every fold is assigned at the `draft_id` level, so "
        "no draft's games straddle a partition or fold boundary (benchmark "
        "section 7). Both properties are asserted by test: the intersection of "
        "draft ids across partitions is empty, and no `draft_id` spans two folds.",
        "",
        "## Partition sizes",
        "",
        f"- Observations: **{result.n_obs}** across **{result.n_drafts}** drafts.",
        f"- Development: **{result.n_dev_rows}** rows / **{result.n_dev_drafts}** "
        f"drafts (draft_time {result.dev_time_min} .. {result.dev_time_max}).",
        f"- Holdout: **{result.n_holdout_rows}** rows / "
        f"**{result.n_holdout_drafts}** drafts (draft_time "
        f"{result.holdout_time_min} .. {result.holdout_time_max}).",
        f"- Holdout fraction: **{result.holdout_fraction_drafts:.4f}** of drafts, "
        f"**{result.holdout_fraction_rows:.4f}** of games.",
        "",
        "Every observation is assigned exactly one partition; no row is "
        "unassigned and no row is in both.",
        "",
        "## Cross-fitting folds",
        "",
        f"Every development observation carries one of **{result.k_folds}** "
        "cross-fitting folds (benchmark section 3's T2 procedure). Fold "
        "membership is a deterministic hash of `(seed, draft_id)`, so every game "
        "of a draft shares a fold and no draft spans two folds. Holdout rows "
        f"carry fold `{HOLDOUT_FOLD}` -- cross-fitting happens inside development "
        "only.",
        "",
        "| fold | dev rows |",
        "| --- | --- |",
        fold_rows,
        "",
        "## Determinism and the seed",
        "",
        f"The only randomness is the fold assignment, drawn from the declared "
        f"seed **{result.seed}** via a hash -- there is no RNG state to carry. "
        "Row order is the model table's own order. Two consecutive runs therefore "
        "produce a byte-identical `model_split.parquet`; `python -m "
        "deckbench.split --verify` rebuilds it in memory and checks it against "
        "the file on disk.",
        "",
        "## Pinned twice, on purpose",
        "",
        "The split parquet is pinned in two places that answer different "
        "questions. `data/splits/split_manifest.json` pins its SHA256 and is what "
        "the seal verifies before returning any holdout row -- if the split was "
        "regenerated after models were fit against it, the hash moves and the "
        "seal fails closed. `data/processed/MANIFEST.sha256` pins it alongside "
        "the four card-004/005 artifacts so every derived artifact is covered "
        "uniformly and a full rebuild is checked byte-for-byte.",
        "",
        "## The seal",
        "",
        "The external holdout is opened only through "
        "`deckbench.holdout.load_holdout`, which refuses to answer without a card "
        "id and a reason, verifies the split's hash against the manifest (failing "
        "closed on any mismatch), and appends one line to the append-only ledger "
        "`cycle/holdout_ledger.jsonl` every time it does answer -- before "
        "returning the rows, so an interrupted read is still recorded. A refused "
        "read appends nothing. A second read by the same card id is refused "
        "unless an explicit repeat flag is passed, and the ledger records the "
        "repeat. Ordinary development uses `deckbench.holdout.load_dev`, which "
        "returns development rows without a card id and without touching the "
        "ledger, so the ledger's signal stays high. Afterwards, how many times "
        "the holdout was opened is a countable fact rather than a recollection "
        "(benchmark sections 9, 12).",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def build() -> SplitResult:
    """Build the split, write the parquet, pin it twice, and write the report."""
    result = build_split()
    write_split_parquet(result)
    write_split_manifest(result)
    write_sha256_manifest()
    write_report(result)
    return result


def verify() -> None:
    """Rebuild the split in memory and check the on-disk artifacts match.

    Fails if the parquet is not byte-reproducible, if the split manifest's pinned
    hash is stale, or if ``MANIFEST.sha256`` does not describe the current
    parquet. This is the check that makes "frozen" mean something.
    """
    if not MODEL_SPLIT_PARQUET.exists():
        raise SplitVerificationError(
            f"{MODEL_SPLIT_PARQUET} is absent; run `python -m deckbench.split` first."
        )
    result = build_split()
    with tempfile.TemporaryDirectory() as tmp:
        rebuilt = Path(tmp) / "model_split.parquet"
        pq.write_table(_split_table(result), rebuilt, compression="snappy")
        if rebuilt.read_bytes() != MODEL_SPLIT_PARQUET.read_bytes():
            raise SplitVerificationError(
                "rebuilt split is not byte-identical to the on-disk parquet"
            )
    on_disk_sha = _sha256(MODEL_SPLIT_PARQUET)

    if not SPLIT_MANIFEST.exists():
        raise SplitVerificationError(f"{SPLIT_MANIFEST} is absent")
    manifest = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("split_sha256") != on_disk_sha:
        raise SplitVerificationError(
            "split_manifest.json split_sha256 does not match the parquet on disk"
        )

    if not SHA256_MANIFEST.exists():
        raise SplitVerificationError(f"{SHA256_MANIFEST} is absent")
    rel = MODEL_SPLIT_PARQUET.relative_to(REPO_ROOT).as_posix()
    listed = {}
    for line in SHA256_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(" *", 1)
        listed[name] = digest
    if listed.get(rel) != on_disk_sha:
        raise SplitVerificationError(
            f"MANIFEST.sha256 does not pin the current {rel}"
        )
    print(
        f"Split verified: {result.n_dev_rows} dev / {result.n_holdout_rows} "
        f"holdout rows, byte-identical rebuild, both pins current."
    )


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if "--verify" in args:
        verify()
        return
    result = build()
    print(
        f"Split built: {result.n_dev_rows} dev / {result.n_holdout_rows} holdout "
        f"rows ({result.n_dev_drafts} / {result.n_holdout_drafts} drafts, "
        f"holdout {result.holdout_fraction_drafts:.4f} of drafts, "
        f"{result.holdout_fraction_rows:.4f} of games), {result.k_folds} folds, "
        f"seed {result.seed}. Wrote "
        f"{MODEL_SPLIT_PARQUET.relative_to(REPO_ROOT).as_posix()}, "
        f"{SPLIT_MANIFEST.relative_to(REPO_ROOT).as_posix()} and refreshed "
        f"{SHA256_MANIFEST.relative_to(REPO_ROOT).as_posix()}."
    )


if __name__ == "__main__":
    main()
