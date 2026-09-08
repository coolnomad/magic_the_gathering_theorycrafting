"""Verify that a file has only been appended to since its last commit.

`LABNOTEBOOK.md` and `CONVERSATION_LOG.md` are append-only by repository rule
(`INSTRUCTIONS.md` section 3), and until now nothing could check it. The obvious
check -- compare `git show HEAD:file` against the working file -- is wrong in a
way that looks right: `* text=auto` in `.gitattributes` stores LF in the blob
while the working copy on Windows is CRLF, so a clean append reports a violation
on every line. Verified 2026-09-07: a 3712-byte pure append failed the naive
byte comparison and passed once compared at the blob level.

This tool therefore compares *git blobs*, not working copies. The committed blob
(LF, as stored) is compared against the working tree normalized through git's own
`hash-object` machinery (which applies the same `text=auto` normalization git
would apply on commit). The append-only property holds when the committed blob is
a byte-level prefix of that normalized working blob. Both operands are blobs
retrieved from git, so line-ending differences never produce a false violation.

Usage:
    python tools/check_append_only.py <path>

Exit code 0 when the committed blob is a byte-level prefix of the working tree
(a pure append, or no change). Exit code 1 otherwise, naming the first byte
offset at which the working tree diverges from its committed blob.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    """Outcome of an append-only check on a single file."""

    ok: bool
    message: str
    offset: int | None = None
    committed_len: int | None = None
    working_len: int | None = None


def _git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
    )


def _repo_root(path: Path) -> Path:
    start = path.parent if path.parent != Path("") else Path.cwd()
    proc = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"not inside a git repository: {path} ({proc.stderr.decode(errors='replace').strip()})"
        )
    return Path(proc.stdout.decode().strip())


def _first_divergence(committed: bytes, working: bytes) -> int | None:
    """First byte offset where `committed` is not a prefix of `working`.

    Returns None when `committed` is a (possibly improper) byte-level prefix of
    `working` -- i.e. the file was only appended to, or not changed at all.
    """
    overlap = min(len(committed), len(working))
    for i in range(overlap):
        if committed[i] != working[i]:
            return i
    if len(working) < len(committed):
        # the working tree is a truncation of the committed blob
        return len(working)
    return None


def check_append_only(path: str | Path) -> CheckResult:
    """Check that `path`'s committed blob is a byte-level prefix of its working tree.

    Both the committed content and the working-tree content are obtained as git
    blobs, so `text=auto` line-ending normalization is applied identically to
    each side and cannot manufacture a false violation.
    """
    p = Path(path).resolve()
    root = _repo_root(p)
    rel = p.relative_to(root).as_posix()

    committed_proc = _git(root, ["cat-file", "blob", f"HEAD:{rel}"])
    if committed_proc.returncode != 0:
        # No committed blob at HEAD (new / untracked file): nothing to violate.
        return CheckResult(
            ok=True,
            message=f"OK: {rel} has no committed blob at HEAD; nothing to check.",
        )
    committed = committed_proc.stdout

    # Normalize the working tree through git's own object machinery. `hash-object`
    # consults .gitattributes for `rel`, so CRLF is folded to LF exactly as on commit.
    hashed = _git(root, ["hash-object", "-w", "--", str(p)])
    if hashed.returncode != 0:
        raise RuntimeError(
            f"git hash-object failed for {rel}: {hashed.stderr.decode(errors='replace').strip()}"
        )
    work_sha = hashed.stdout.decode().strip()
    work_proc = _git(root, ["cat-file", "blob", work_sha])
    if work_proc.returncode != 0:
        err = work_proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git cat-file failed for {work_sha}: {err}")
    working = work_proc.stdout

    offset = _first_divergence(committed, working)
    if offset is None:
        return CheckResult(
            ok=True,
            message=(
                f"OK: committed blob of {rel} is a byte-level prefix of the working tree "
                f"(committed {len(committed)} bytes, working {len(working)} bytes)."
            ),
            committed_len=len(committed),
            working_len=len(working),
        )
    return CheckResult(
        ok=False,
        message=(
            f"APPEND-ONLY VIOLATION: {rel} diverges from its committed blob at byte offset "
            f"{offset} (committed {len(committed)} bytes, working {len(working)} bytes). "
            f"The committed content must be a byte-level prefix of the working tree; existing "
            f"content may only be appended to, never edited or deleted."
        ),
        offset=offset,
        committed_len=len(committed),
        working_len=len(working),
    )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python tools/check_append_only.py <path>", file=sys.stderr)
        return 2
    result = check_append_only(argv[0])
    stream = sys.stdout if result.ok else sys.stderr
    print(result.message, file=stream)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
