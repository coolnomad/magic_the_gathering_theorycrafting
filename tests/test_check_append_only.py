"""Tests for tools/check_append_only.py.

Covers the three cases the card names: a genuine append (passes), a mid-file edit
(fails, naming the offset), and a file whose line endings differ between the
committed blob and the working tree (passes -- the false-violation the tool
exists to prevent). Each case builds a throwaway git repository so the check runs
against real committed blobs, not a mock.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Make tools/ importable without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_append_only import check_append_only, main  # noqa: E402


def _run(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _init_repo(repo: Path) -> None:
    _run(repo, "init", "-q")
    _run(repo, "config", "user.email", "test@example.com")
    _run(repo, "config", "user.name", "Test")
    # Reproduce the repository's own rule: text files are normalized to LF in the blob.
    (repo / ".gitattributes").write_bytes(b"* text=auto\n")
    _run(repo, "add", ".gitattributes")
    _run(repo, "commit", "-q", "-m", "attrs")


def _commit_file(repo: Path, name: str, content: bytes) -> Path:
    f = repo / name
    f.write_bytes(content)
    _run(repo, "add", name)
    _run(repo, "commit", "-q", "-m", f"add {name}")
    return f


def test_genuine_append_passes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    f = _commit_file(tmp_path, "log.md", b"line one\nline two\n")
    # Append only; existing bytes untouched.
    f.write_bytes(b"line one\nline two\nline three\n")

    result = check_append_only(f)
    assert result.ok
    assert result.offset is None
    assert result.committed_len == len(b"line one\nline two\n")
    assert result.working_len == len(b"line one\nline two\nline three\n")


def test_mid_file_edit_fails_with_offset(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    f = _commit_file(tmp_path, "log.md", b"line one\nline two\nline three\n")
    # Edit a byte in the middle: "two" -> "TWO". Then append, to prove growth
    # does not excuse the edit.
    f.write_bytes(b"line one\nline TWO\nline three\nappended\n")

    result = check_append_only(f)
    assert not result.ok
    # First divergence is the 't' of "two" flipping to 'T'.
    assert result.offset == len(b"line one\nline ")
    assert "byte offset" in result.message


def test_line_ending_difference_passes(tmp_path: Path) -> None:
    # The headline false-violation: blob stored LF (text=auto), working tree CRLF.
    _init_repo(tmp_path)
    f = _commit_file(tmp_path, "log.md", b"alpha\nbeta\ngamma\n")
    # Same logical content, CRLF line endings (as a Windows checkout would carry).
    f.write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")

    result = check_append_only(f)
    assert result.ok, result.message
    assert result.offset is None


def test_line_ending_difference_with_append_passes(tmp_path: Path) -> None:
    # CRLF working tree AND a genuine append -- still an append after normalization.
    _init_repo(tmp_path)
    f = _commit_file(tmp_path, "log.md", b"alpha\nbeta\n")
    f.write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")

    result = check_append_only(f)
    assert result.ok, result.message
    assert result.offset is None


def test_main_exit_codes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    f = _commit_file(tmp_path, "log.md", b"one\ntwo\n")

    f.write_bytes(b"one\ntwo\nthree\n")
    assert main([str(f)]) == 0

    f.write_bytes(b"one\nTWO\n")
    assert main([str(f)]) == 1

    assert main([]) == 2
