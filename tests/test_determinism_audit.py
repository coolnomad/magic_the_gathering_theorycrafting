"""Tests for the card-013 determinism audit harness (`tools/determinism_audit.py`).

These exercise the harness against the real repository but keep the subprocess count
low so the file runs well under the orchestrator's 60 s Output-Validation budget:

  * the confirmed-unstable review files are now byte-stable across fresh processes;
  * the fix changed only ordering — the multiset of records equals the committed version;
  * `card_pair_projection_audit_repair.jsonl` is covered and stable;
  * the characterization logic distinguishes pure reordering from an internal record diff;
  * the harness exits non-zero exactly when a covered artifact is unstable;
  * a run leaves the working tree byte-identical.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
REVIEW_FILES = ("llm_accepted.jsonl", "llm_queued.jsonl")


def _load_harness() -> ModuleType:
    path = REPO / "tools" / "determinism_audit.py"
    spec = importlib.util.spec_from_file_location("determinism_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # dataclass introspection needs it registered
    spec.loader.exec_module(module)
    return module


da = _load_harness()


@pytest.fixture(scope="module")
def interp() -> str:
    return da.find_interpreter()


@pytest.fixture(scope="module")
def review_and_audit_report(interp: str):
    # One shared run of the two card-critical jobs, two fresh processes each.
    return da.run_audit(jobs=["phase3_review", "audit_repair"], runs=2, interp=interp)


def _find(report, artifact: str):
    return next((r for r in report.artifacts if r.artifact == artifact), None)


def _canon(obj):
    if isinstance(obj, dict):
        return {k: _canon(v) for k, v in obj.items()}
    if isinstance(obj, list):
        items = [_canon(x) for x in obj]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    return obj


def _canonical_multiset(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            out.append(json.dumps(_canon(json.loads(line)), sort_keys=True, ensure_ascii=False))
    return sorted(out)


# --------------------------------------------------------------------------- #
#  The confirmed case: review files are now deterministic                       #
# --------------------------------------------------------------------------- #

def test_review_files_reported_stable(review_and_audit_report) -> None:
    report = review_and_audit_report
    for name in ("llm_accepted.jsonl", "llm_queued.jsonl", "llm_face_status.jsonl"):
        res = _find(report, f"data/review/{name}")
        assert res is not None, f"{name} not covered by the harness"
        assert res.verdict == "stable", (name, res.characterization)


def test_reconcile_output_is_byte_identical_across_hash_seeds(interp: str) -> None:
    # Directly exercise the fix through the harness primitives, in two fresh processes
    # under different hash seeds. Pre-fix this differed; it must now agree byte-for-byte.
    code = "from hobkg import phase3; phase3.reconcile(); phase3.finalize_faces()"
    snap = da.snapshot()
    captured: list[dict[str, bytes]] = []
    try:
        for seed in (0, 91237):
            da.restore(snap)
            ok, err = da.run_child(interp, code, seed)
            assert ok, err
            captured.append({n: (REPO / "data/review" / n).read_bytes() for n in REVIEW_FILES})
    finally:
        da.restore(snap)
    for name in REVIEW_FILES:
        assert captured[0][name] == captured[1][name], f"{name} differs between hash seeds"


def test_fix_preserves_record_multiset_of_committed_review_files(interp: str) -> None:
    # The committed files are the working copy (clean tree); a fresh regeneration must
    # contain the same records — only their intra-record ordering may change.
    code = "from hobkg import phase3; phase3.reconcile(); phase3.finalize_faces()"
    committed = {n: _canonical_multiset((REPO / "data/review" / n).read_text(encoding="utf-8"))
                 for n in REVIEW_FILES}
    snap = da.snapshot()
    try:
        da.restore(snap)
        ok, err = da.run_child(interp, code, 4242)
        assert ok, err
        regen = {n: _canonical_multiset((REPO / "data/review" / n).read_text(encoding="utf-8"))
                 for n in REVIEW_FILES}
    finally:
        da.restore(snap)
    for name in REVIEW_FILES:
        assert regen[name] == committed[name], f"{name} record multiset changed"


# --------------------------------------------------------------------------- #
#  audit_repair projection is covered and stable                                #
# --------------------------------------------------------------------------- #

def test_audit_repair_projection_covered_and_stable(review_and_audit_report) -> None:
    res = _find(review_and_audit_report,
                "data/graph_global/card_pair_projection_audit_repair.jsonl")
    assert res is not None, "audit_repair projection not covered"
    assert res.verdict == "stable"


# --------------------------------------------------------------------------- #
#  Characterization: pure reordering vs an internal record diff                 #
# --------------------------------------------------------------------------- #

def test_characterize_pure_reordering() -> None:
    a = b'{"id":1}\n{"id":2}\n'
    b = b'{"id":2}\n{"id":1}\n'
    char = da.characterize([a, b], jsonl=True)
    assert char["multiset_of_records_identical"] is True
    assert char["pure_reordering"] is True
    assert char["a_record_differs_internally"] is False
    assert char["record_count"] == [2, 2]
    assert char["first_differing_byte_offset"] >= 0


def test_characterize_internal_record_diff() -> None:
    # An element reordered *inside* a record — the confirmed llm_queued.jsonl signature.
    a = b'{"e":["x","y"]}\n'
    b = b'{"e":["y","x"]}\n'
    char = da.characterize([a, b], jsonl=True)
    assert char["multiset_of_records_identical"] is False
    assert char["pure_reordering"] is False
    assert char["a_record_differs_internally"] is True
    assert char["record_count"] == [1, 1]
    assert char["byte_length"] == [len(a), len(b)]


# --------------------------------------------------------------------------- #
#  Exit-code contract and tree hygiene                                          #
# --------------------------------------------------------------------------- #

def test_main_exit_nonzero_when_an_artifact_is_unstable(monkeypatch) -> None:
    unstable = da.AuditReport(seeds=[0, 1])
    unstable.artifacts.append(da.ArtifactResult(
        "x.jsonl", "job", "unstable", 2,
        characterization=da.characterize([b"a\n", b"b\n"], jsonl=True)))
    monkeypatch.setattr(da, "run_audit", lambda **kwargs: unstable)
    monkeypatch.setattr(da, "render_report", lambda report: "")
    assert da.main([]) == 1

    stable = da.AuditReport(seeds=[0, 1])
    stable.artifacts.append(da.ArtifactResult("y.jsonl", "job", "stable", 2))
    monkeypatch.setattr(da, "run_audit", lambda **kwargs: stable)
    assert da.main([]) == 0


def test_report_flags_unstable_artifacts_as_failure() -> None:
    report = da.AuditReport(seeds=[0, 1])
    report.artifacts.append(da.ArtifactResult(
        "data/review/x.jsonl", "phase3_review", "unstable", 2,
        characterization=da.characterize([b'{"e":["x","y"]}\n', b'{"e":["y","x"]}\n'], jsonl=True)))
    text = da.render_report(report)
    assert "UNSTABLE" in text
    assert "first_diff_byte" in text


def test_frozen_base_verified_byte_identical(review_and_audit_report) -> None:
    frozen = {r.artifact: r for r in review_and_audit_report.frozen}
    for name in ("nodes.jsonl", "edges.jsonl", "conditions.jsonl"):
        res = frozen.get(f"data/graph_global/{name}")
        assert res is not None and res.verdict == "stable", name


def test_audit_run_leaves_tree_byte_identical(interp: str) -> None:
    sample = [REPO / "data/review/llm_accepted.jsonl",
              REPO / "data/graph_global/card_pair_projection_audit_repair.jsonl",
              REPO / "data/graph_global/edges.jsonl"]
    before = {p: p.read_bytes() for p in sample}
    da.run_audit(jobs=["phase3_review", "audit_repair"], runs=2, interp=interp)
    for path, data in before.items():
        assert path.read_bytes() == data, f"{path} not restored to its original bytes"
