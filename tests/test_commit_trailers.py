"""Every handshake commit since the epoch must be readable by git's own parser.

A trailer block that git cannot see is worse than no block at all: the discipline
looks followed, the lab notebook records it as followed, and every machine reader
disagrees. Measured on 2026-09-02, 36 of the 80 commits before ``EPOCH`` carried a
complete, correct block and *none* were readable -- each shadowed by a
``Co-Authored-By`` paragraph placed after it. Git reads the last paragraph and
nothing else.

History before ``EPOCH`` is not rewritten. Two committed artifacts in the
adaptive_orchestrator repository pin HOB SHAs -- ``tests/fixtures/MANIFEST.json``
(``source_commit``) and ``src/ratchet/replay.py`` (``HOB_BASE_SHA``, plus an
ancestry assertion on every recorded ``reviewed_commit``) -- and a rewrite would
invalidate the keystone replay that is the orchestrator's only end-to-end proof.

See INSTRUCTIONS.md section 8.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# The last pre-convention commit. Commits after this one are in scope.
EPOCH = "0315399b8a28defb7d3c7a9117a7a339a38a03b5"

REPO_ROOT = Path(__file__).resolve().parents[1]

# A line that looks like the start of a handshake block. Matched on the whole
# message, not just the last paragraph -- that difference is the defect.
ROLE_LINE = re.compile(r"^Role:[ \t]*\S", re.MULTILINE)

_UNIT = "\x1f"
_RECORD = "\x1e"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


def _epoch_exists() -> bool:
    try:
        _git("cat-file", "-e", f"{EPOCH}^{{commit}}")
    except subprocess.CalledProcessError:
        return False
    return True


def _commits_since_epoch() -> list[tuple[str, str, str]]:
    """(sha, full message, Role trailer as git sees it) for each commit after EPOCH."""
    raw = _git(
        "log",
        f"{EPOCH}..HEAD",
        f"--format=%H{_UNIT}%(trailers:key=Role,valueonly,separator=;){_UNIT}%B{_RECORD}",
    )
    commits: list[tuple[str, str, str]] = []
    for record in raw.split(_RECORD):
        record = record.lstrip("\n")
        if not record:
            continue
        parts = record.split(_UNIT, 2)
        if len(parts) != 3:
            continue
        sha, role, message = parts
        commits.append((sha.strip(), message, role.strip()))
    return commits


@pytest.mark.skipif(not _epoch_exists(), reason="epoch commit not present in this clone")
def test_no_handshake_block_is_shadowed() -> None:
    """A message carrying a Role: line must expose it to git's trailer parser.

    This is the exact defect INSTRUCTIONS.md section 8 exists to prevent: the block
    is present and correct, but a paragraph placed after it makes git report
    nothing. Fix with ``git commit --amend``, moving ``Co-Authored-By`` into the
    block.
    """
    shadowed = [
        sha
        for sha, message, role in _commits_since_epoch()
        if ROLE_LINE.search(message) and not role
    ]
    assert not shadowed, (
        "these commits carry a Role: line that git's trailer parser cannot see; "
        "the block is almost certainly shadowed by a trailing paragraph "
        f"(see INSTRUCTIONS.md section 8): {shadowed}"
    )


@pytest.mark.skipif(not _epoch_exists(), reason="epoch commit not present in this clone")
def test_handshake_commits_carry_a_qualified_phase() -> None:
    """A readable Role implies a readable, namespace-qualified Phase.

    A bare ``Phase 4`` is ambiguous: the build spec and the effect-semantics repair
    both have one. ``ratchet.ledger`` refuses a handshake commit with no Phase
    trailer outright, so an unqualified or missing Phase is a defect either way.
    """
    offenders: list[tuple[str, str]] = []
    for sha, _message, role in _commits_since_epoch():
        if not role:
            continue
        phase = _git(
            "log", "-1", "--format=%(trailers:key=Phase,valueonly,separator=;)", sha
        ).strip()
        if not phase or re.fullmatch(r"(?i)phase\s*\d+", phase):
            offenders.append((sha[:8], phase or "(none)"))
    assert not offenders, (
        "handshake commits need a namespace-qualified Phase such as 'effect-4f' or "
        f"'buildspec-6', never a bare 'Phase N' (INSTRUCTIONS.md section 8): {offenders}"
    )
