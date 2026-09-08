"""The seal on the external holdout (card 006).

A frozen split that anything can read is not a control. The failure this guards
against is evaluating on the holdout repeatedly and reporting the run that looked
best -- and that failure leaves no trace in a diff. So holdout access goes
through one function that refuses to answer without a card id and a reason,
verifies the split's hash against the frozen manifest before returning a single
row, and appends a line to an append-only ledger every time it does answer.
Afterwards, how many times the holdout was opened is a countable fact rather than
a recollection (benchmark sections 9, 12).

Two paths, deliberately unequal in ceremony:

* :func:`load_holdout` -- the sealed path. Fails closed on any hash mismatch or
  missing/malformed argument, writes the ledger line **before** returning rows so
  an interrupted read is still recorded, and refuses a second read by the same
  card id unless an explicit ``repeat`` flag is passed.
* :func:`load_dev` -- the unsealed path. Returns development rows without a card
  id and without touching the ledger, so ordinary work does not route through the
  seal and fill the ledger with noise until nobody reads it.

Nothing here catches a bare ``Exception`` around the hash verification: a masked
verification failure is the one bug that would make this whole module
decorative.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

# src/deckbench/holdout.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SPLIT_PARQUET = PROCESSED_DIR / "model_split.parquet"
SPLIT_MANIFEST = REPO_ROOT / "data" / "splits" / "split_manifest.json"
LEDGER_PATH = REPO_ROOT / "cycle" / "holdout_ledger.jsonl"

# Partition labels, matched to :mod:`deckbench.split`.
DEV = "dev"
HOLDOUT = "holdout"

# A card id names the task card opening the holdout, e.g. "007". Task cards in
# this repository are three-digit ids; anything else is treated as malformed so a
# read cannot be attributed to a card that does not exist.
CARD_ID_PATTERN = re.compile(r"^\d{3}$")


class HoldoutSealError(Exception):
    """Raised when a holdout read is refused or the seal cannot be verified.

    This is the single typed error the seal raises: a hash mismatch, a missing or
    malformed card id, a missing reason, or an unpermitted repeat. It always
    means no holdout row was returned.
    """


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verify_seal(split_parquet: Path, split_manifest: Path) -> str:
    """Verify the split parquet against its pinned hash; return that hash.

    Fails closed: a missing manifest, a missing parquet, an unparseable manifest,
    a manifest with no pinned hash, or a hash mismatch each raise
    :class:`HoldoutSealError` rather than falling back to returning rows. The
    ``json.JSONDecodeError`` catch is specific on purpose -- there is no bare
    ``except`` around this verification, because a masked failure here removes the
    only guarantee this module provides.
    """
    if not split_manifest.exists():
        raise HoldoutSealError(
            f"split manifest not found: {split_manifest}. The seal cannot verify "
            "the holdout and will not return rows."
        )
    if not split_parquet.exists():
        raise HoldoutSealError(
            f"split parquet not found: {split_parquet}. Run "
            "`python -m deckbench.split` first."
        )
    try:
        manifest = json.loads(split_manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HoldoutSealError(
            f"split manifest {split_manifest} is not valid JSON: {exc}"
        ) from exc
    pinned = manifest.get("split_sha256")
    if not isinstance(pinned, str) or not pinned:
        raise HoldoutSealError(
            f"split manifest {split_manifest} does not pin a split_sha256"
        )
    actual = _sha256(split_parquet)
    if actual != pinned:
        raise HoldoutSealError(
            "split parquet SHA256 does not match the manifest: the split was "
            "changed after it was frozen. Refusing to return holdout rows "
            f"(expected {pinned}, got {actual})."
        )
    return actual


def _validate_card_id(card_id: object) -> str:
    """Return a well-formed card id, or raise before anything is written."""
    if not isinstance(card_id, str) or not card_id.strip():
        raise HoldoutSealError(
            "a holdout read requires a card id; it is missing or empty."
        )
    if not CARD_ID_PATTERN.match(card_id):
        raise HoldoutSealError(
            f"card id {card_id!r} is malformed; expected a three-digit task-card "
            "id such as '007'."
        )
    return card_id


def _validate_reason(reason: object) -> str:
    """Return a non-empty reason, or raise before anything is written."""
    if not isinstance(reason, str) or not reason.strip():
        raise HoldoutSealError(
            "a holdout read requires a non-empty reason; it is missing or empty."
        )
    return reason


def _git_commit_sha() -> str:
    """Best-effort current commit SHA for the ledger line.

    The ledger line records which commit opened the holdout. If git is
    unavailable the read is still recorded (with ``"unknown"``) rather than
    refused -- the seal fails closed on the *hash verification*, not on an
    inability to name the commit.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _prior_read_exists(card_id: str, ledger_path: Path) -> bool:
    """Whether the ledger already records a permitted read by this card id."""
    if not ledger_path.exists():
        return False
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("card_id") == card_id:
            return True
    return False


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _partition_rows(split_parquet: Path, partition: str) -> pa.Table:
    table = pq.read_table(split_parquet)
    mask = pc.equal(table.column("partition"), partition)
    return table.filter(mask)


def load_holdout(
    card_id: str,
    reason: str,
    *,
    repeat: bool = False,
    split_parquet: Path | None = None,
    split_manifest: Path | None = None,
    ledger_path: Path | None = None,
) -> pa.Table:
    """Return the external holdout rows, through the seal.

    Verifies the split's hash against the frozen manifest (failing closed on any
    mismatch), requires a well-formed ``card_id`` and a non-empty ``reason``,
    refuses a second read by the same card id unless ``repeat=True``, and appends
    exactly one line to the append-only ledger -- **before** returning the rows,
    so an interrupted read is still recorded. A refused read appends nothing.

    Returns a table of the holdout partition's assignment rows (``obs_id``,
    ``draft_id``, ``partition``, ``fold``); downstream code joins features onto
    ``obs_id``.
    """
    split_parquet = split_parquet or SPLIT_PARQUET
    split_manifest = split_manifest or SPLIT_MANIFEST
    ledger_path = ledger_path or LEDGER_PATH

    # 1. Verify the seal first. Anything wrong here raises; no row is returned
    #    and, because this precedes any write, no ledger line is appended.
    split_sha256 = _verify_seal(split_parquet, split_manifest)

    # 2. Validate the arguments. Each raises before any write, so a refused read
    #    leaves the ledger byte-identical.
    card_id = _validate_card_id(card_id)
    reason = _validate_reason(reason)

    # 3. Enforce one-read-per-card unless the caller explicitly repeats.
    is_repeat = _prior_read_exists(card_id, ledger_path)
    if is_repeat and not repeat:
        raise HoldoutSealError(
            f"card id {card_id!r} has already opened the holdout. Pass "
            "repeat=True to read it again; the repeat will be recorded so the "
            "count of comparisons stays visible."
        )

    # 4. Write the ledger line BEFORE returning rows, so an interrupted read is
    #    still recorded. Append-only: one new line, never a rewrite.
    record = {
        "timestamp": _now_iso(),
        "card_id": card_id,
        "reason": reason,
        "git_commit": _git_commit_sha(),
        "split_sha256": split_sha256,
        "is_repeat": is_repeat,
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")

    # 5. Only now return the holdout rows.
    return _partition_rows(split_parquet, HOLDOUT)


def load_dev(split_parquet: Path | None = None) -> pa.Table:
    """Return the development rows -- the unsealed path.

    Requires no card id and touches no ledger, so ordinary development does not
    route through the seal. Never returns a holdout row: it filters to the
    development partition only.
    """
    split_parquet = split_parquet or SPLIT_PARQUET
    if not split_parquet.exists():
        raise FileNotFoundError(
            f"split parquet not found: {split_parquet}. Run "
            "`python -m deckbench.split` first."
        )
    return _partition_rows(split_parquet, DEV)
