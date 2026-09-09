#!/usr/bin/env python3
"""Determinism audit harness (card 013).

`registry.md` carries the success criterion *"Frozen artifacts stay byte-identical,
and two serial builds agree."* This harness makes that criterion checkable rather
than aspirational: it regenerates every derived artifact several times, EACH in a
fresh Python process, and compares the bytes the code actually writes.

Why a fresh process per run: the one confirmed instability in this repository is
per-record element order that falls out of Python `set` iteration, whose order is
randomized per process via ``PYTHONHASHSEED``. Comparing two regenerations inside a
single process would fix the seed and hide it; comparing against git's stored blob
would invent a phantom difference, because ``* text=auto`` stores LF while the
working copy is CRLF, so a CRLF working copy differs from an LF blob by exactly one
byte per line and says nothing about determinism. This harness therefore

  * spawns N fresh subprocesses per regeneration job, one per distinct hash seed;
  * reads each artifact back in **binary**, i.e. exactly the bytes the code wrote;
  * compares those byte strings to each other, never to git.

For every artifact reported unstable it records how it differs: the record count in
each run, whether the multiset of records is identical (pure reordering) or a record
differs internally, and the offset of the first differing byte.

The frozen base (``nodes.jsonl``, ``edges.jsonl``, ``conditions.jsonl`` and
``frozen_manifest.json``) is never regenerated; the harness only verifies it stays
byte-identical to the hashes pinned in ``frozen_manifest.json``. The modeling arm's
``data/processed`` artifacts are likewise not rebuilt here (their own cards assert a
byte-identical rebuild); the harness verifies them against ``MANIFEST.sha256``.

The working tree is snapshotted before any regeneration and restored afterwards, so a
run leaves it byte-identical to how it started.

Usage::

    python tools/determinism_audit.py            # audit, exit non-zero if unstable
    python tools/determinism_audit.py --report    # also (re)write reports/determinism_audit.md
    python tools/determinism_audit.py --runs 5     # regenerate 5x instead of the default 3
    python tools/determinism_audit.py --jobs phase3_review,audit_repair   # subset (used by tests)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

# Directories holding derived artifacts we snapshot, restore and enumerate.
DERIVED_DIRS = ("data/review", "data/llm", "data/graph_global", "schema", "reports")

# The report this harness writes — excluded from snapshot/restore (it must persist) and
# from enumeration (it is not a build artifact, it is the audit's own output).
REPORT_PATH = "reports/determinism_audit.md"

# The frozen base: never regenerated, only verified byte-identical against the manifest.
FROZEN_MANIFEST = "data/graph_global/frozen_manifest.json"
FROZEN_FILES = (
    "data/graph_global/nodes.jsonl",
    "data/graph_global/edges.jsonl",
    "data/graph_global/conditions.jsonl",
    "data/graph/nodes.jsonl",
    "data/graph/edges.jsonl",
    "data/graph/conditions.jsonl",
    "data/graph/gates.jsonl",
    FROZEN_MANIFEST,
)

# Modeling-arm artifacts: not rebuilt here, verified against their own hash manifest.
DECKBENCH_MANIFEST = "data/processed/MANIFEST.sha256"

# Per-face directories collapse to a single grouped artifact so the report stays legible.
GROUP_DIRS = (
    "data/llm/tasks",
    "data/llm/critiques",
    "data/llm/batches",
    "data/llm/rebatches",
    "data/llm/audit",
    "data/llm/extractions",
)

# Regeneration jobs: a name and the Python executed in a fresh subprocess. Each job reads
# the committed inputs (the harness restores them before every run) and writes only
# additive/derived outputs — NONE of them touch the frozen base. Jobs earlier in the list
# own any artifact they share with a later job (e.g. phase3_review owns llm_accepted.jsonl,
# not phase3_apply_dispositions, which rewrites it with disposition edges).
JOBS: tuple[tuple[str, str], ...] = (
    ("phase3_build_tasks", "from hobkg import phase3; phase3.build_tasks()"),
    ("phase3_review", "from hobkg import phase3; phase3.reconcile(); phase3.finalize_faces()"),
    ("phase3_ingest", "from hobkg import phase3; phase3.ingest()"),
    ("phase3_apply_dispositions", "from hobkg import phase3; phase3.apply_dispositions()"),
    ("project", "from hobkg import project; project.project()"),
    ("graph_repair", "from hobkg import graph_repair as g; g.repair(); g.reproject()"),
    ("complete_mechanisms",
     "from hobkg import complete_mechanisms as m; m.materialize(); m.reproject()"),
    ("equip", "from hobkg import equip as e; e.materialize(); e.reproject()"),
    ("completeness", "from hobkg import completeness as c; c.materialize(); c.reproject()"),
    ("lifecycle", "from hobkg import lifecycle as x; x.materialize(); x.reproject()"),
    ("audit", "from hobkg import audit as a; a.build_candidates(); a.build_batches(); a.ingest()"),
    ("modules", "from hobkg import modules; modules.build_modules()"),
    ("coverage",
     "from hobkg import coverage as c; "
     "c.coverage(); c.structural_validation_set(); c.pair_index()"),
    ("audit_repair", "from hobkg import audit_repair; audit_repair.materialize()"),
    ("schemas", "from hobkg import pipeline; pipeline.export_schemas()"),
    # `ports --all` regenerates the 210-face artifact; the bare `ports` derives the 11-face
    # pilot and DESTROYS card_ports.jsonl (HANDOFF hazard), so the flag is mandatory here.
    ("ports", "from hobkg import ports; ports.main(['--all'])"),
)

PROBE = "import hobkg, jsonschema, pydantic; from hobkg import phase3, audit_repair"


# --------------------------------------------------------------------------- #
#  Data model                                                                   #
# --------------------------------------------------------------------------- #

@dataclass
class ArtifactResult:
    artifact: str                       # repo-relative path (or "dir/ (N files)")
    job: str
    verdict: str                        # stable | unstable | not_regenerable | verified_manifest
    runs: int
    note: str = ""
    characterization: dict[str, object] | None = None


@dataclass
class AuditReport:
    artifacts: list[ArtifactResult] = field(default_factory=list)
    frozen: list[ArtifactResult] = field(default_factory=list)
    deckbench: list[ArtifactResult] = field(default_factory=list)
    job_errors: dict[str, str] = field(default_factory=dict)
    seeds: list[int] = field(default_factory=list)

    def any_unstable(self) -> bool:
        pools = (self.artifacts, self.frozen, self.deckbench)
        return any(r.verdict == "unstable" for pool in pools for r in pool)


# --------------------------------------------------------------------------- #
#  Interpreter discovery & child execution                                      #
# --------------------------------------------------------------------------- #

def find_interpreter() -> str:
    """Return a Python that can import hobkg and its deps.

    The default check runs under the orchestrator venv, which lacks hobkg and its
    dependencies; so we probe candidates rather than assume ``sys.executable``.
    """
    candidates: list[str] = []
    override = os.environ.get("HOBKG_PYTHON")
    if override:
        candidates.append(override)
    candidates.append(sys.executable)
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates.append(r"C:\Python314\python.exe")

    env = _child_env(seed=0)
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        try:
            proc = subprocess.run([cand, "-c", PROBE], env=env,
                                  capture_output=True, text=True, timeout=90)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return cand
    raise SystemExit(
        "determinism_audit: no Python interpreter found that can import hobkg + deps "
        "(pydantic, jsonschema). Set HOBKG_PYTHON to the project interpreter.")


def _child_env(seed: int) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = str(seed)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run_child(interp: str, code: str, seed: int) -> tuple[bool, str]:
    try:
        proc = subprocess.run([interp, "-c", code], env=_child_env(seed),
                              capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - environment
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return False, tail[-1] if tail else f"exit {proc.returncode}"
    return True, ""


# --------------------------------------------------------------------------- #
#  Snapshot / restore of the working tree                                       #
# --------------------------------------------------------------------------- #

def _derived_files() -> list[Path]:
    out: list[Path] = []
    excluded = (REPO / REPORT_PATH).resolve()
    for rel in DERIVED_DIRS:
        base = REPO / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.resolve() != excluded:
                out.append(path)
    return out


def snapshot() -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in _derived_files()}


def restore(snap: dict[Path, bytes]) -> None:
    """Restore every snapshotted file and delete anything created since. Rewrites only
    files whose bytes drifted, so untouched files keep their original mtime."""
    for path in _derived_files():
        if path not in snap:
            path.unlink()
    for path, data in snap.items():
        if not path.exists() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def _mtimes(paths: list[Path]) -> dict[Path, float]:
    out: dict[Path, float] = {}
    for path in paths:
        if path.exists():
            out[path] = path.stat().st_mtime_ns
    return out


def _written_since(before: dict[Path, float]) -> list[Path]:
    """Files whose mtime changed (or that appeared) since ``before`` — i.e. the outputs a
    job wrote. mtime updates on every write even when the bytes are identical, so a stable
    output is still detected."""
    return [p for p in _derived_files() if before.get(p) != p.stat().st_mtime_ns]


# --------------------------------------------------------------------------- #
#  Grouping & comparison                                                        #
# --------------------------------------------------------------------------- #

def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _artifact_id(path: Path) -> str:
    rel = _rel(path)
    for group in GROUP_DIRS:
        if rel.startswith(group + "/"):
            return group
    return rel


def _combine(members: dict[str, bytes]) -> bytes:
    """Deterministic byte view of a grouped directory: each member as
    ``<rel>\\n<bytes>\\n`` in sorted-path order. Any per-file difference surfaces."""
    parts: list[bytes] = []
    for rel in sorted(members):
        parts.append(rel.encode("utf-8") + b"\n" + members[rel] + b"\n")
    return b"".join(parts)


def _first_diff(a: bytes, b: bytes) -> int:
    limit = min(len(a), len(b))
    for i in range(limit):
        if a[i] != b[i]:
            return i
    return limit if len(a) != len(b) else -1


def characterize(runs: list[bytes], jsonl: bool) -> dict[str, object]:
    """Compare run 0 against the first run that differs from it and describe the diff."""
    base = runs[0]
    other = next((r for r in runs[1:] if r != base), base)

    def records(data: bytes) -> list[bytes]:
        if jsonl:
            return [line for line in data.split(b"\n") if line]
        return [data]

    ra, rb = records(base), records(other)
    multiset_identical = sorted(ra) == sorted(rb)
    return {
        "record_count": [len(ra), len(rb)],
        "byte_length": [len(base), len(other)],
        "multiset_of_records_identical": multiset_identical,
        "pure_reordering": multiset_identical and base != other,
        "a_record_differs_internally": not multiset_identical,
        "first_differing_byte_offset": _first_diff(base, other),
    }


# --------------------------------------------------------------------------- #
#  The audit                                                                    #
# --------------------------------------------------------------------------- #

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_frozen(seeds: list[int]) -> list[ArtifactResult]:
    manifest_path = REPO / FROZEN_MANIFEST
    pinned: dict[str, str] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pinned = {rel: entry["sha256"] for rel, entry in manifest.items()}
    out: list[ArtifactResult] = []
    for rel in FROZEN_FILES:
        path = REPO / rel
        if not path.exists():
            out.append(ArtifactResult(rel, "(frozen)", "not_regenerable", 0,
                                      "frozen base file absent"))
            continue
        actual = _sha256(path.read_bytes())
        if rel == FROZEN_MANIFEST:
            out.append(ArtifactResult(rel, "(frozen)", "stable", 0,
                                      "frozen manifest; not regenerated"))
        elif rel in pinned and pinned[rel] == actual:
            out.append(ArtifactResult(rel, "(frozen)", "stable", 0,
                                      "byte-identical to frozen_manifest.json"))
        elif rel in pinned:
            out.append(ArtifactResult(rel, "(frozen)", "unstable", 0,
                                      f"sha256 {actual[:12]} != pinned {pinned[rel][:12]}"))
        else:
            out.append(ArtifactResult(rel, "(frozen)", "stable", 0,
                                      "frozen base; not pinned in this manifest, not regenerated"))
    return out


def _verify_deckbench() -> list[ArtifactResult]:
    manifest_path = REPO / DECKBENCH_MANIFEST
    out: list[ArtifactResult] = []
    if not manifest_path.exists():
        return out
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition(" ")
        rel = name.lstrip("*").strip()
        path = REPO / rel
        if not path.exists():
            out.append(ArtifactResult(rel, "(deckbench)", "not_regenerable", 0,
                                      "gitignored blob absent; rebuild via deckbench cards"))
            continue
        actual = _sha256(path.read_bytes())
        verdict = "verified_manifest" if actual == digest else "unstable"
        note = ("matches MANIFEST.sha256 (verified, not regenerated here)"
                if verdict == "verified_manifest"
                else f"sha256 {actual[:12]} != manifest {digest[:12]}")
        out.append(ArtifactResult(rel, "(deckbench)", verdict, 0, note))
    return out


def run_audit(jobs: list[str] | None = None, runs: int = 3,
              interp: str | None = None) -> AuditReport:
    seeds = list(range(runs))
    interp = interp or find_interpreter()
    selected = [(n, c) for n, c in JOBS if jobs is None or n in jobs]

    report = AuditReport(seeds=seeds)
    assigned: set[str] = set()
    snap = snapshot()
    try:
        for job_name, code in selected:
            # captures[artifact_id] -> list (per seed) of bytes; grouped dirs accumulate members
            captures: dict[str, list[bytes]] = {}
            group_members: dict[str, list[dict[str, bytes]]] = {}
            frozen_before = {REPO / f: (REPO / f).stat().st_mtime_ns
                             for f in FROZEN_FILES if (REPO / f).exists()}
            failed = False
            frozen_touched = False
            for seed in seeds:
                restore(snap)
                before = _mtimes(_derived_files())
                ok, err = run_child(interp, code, seed)
                if not ok:
                    report.job_errors[job_name] = err
                    failed = True
                    break
                for fpath, mtime in frozen_before.items():
                    if fpath.exists() and fpath.stat().st_mtime_ns != mtime:
                        frozen_touched = True
                for path in _written_since(before):
                    aid = _artifact_id(path)
                    if aid in GROUP_DIRS:
                        group_members.setdefault(aid, [{} for _ in seeds])
                        group_members[aid][seeds.index(seed)][_rel(path)] = path.read_bytes()
                    else:
                        captures.setdefault(aid, [])
                        captures[aid].append(path.read_bytes())
            restore(snap)
            if failed:
                continue
            for aid, members_per_seed in group_members.items():
                captures[aid] = [_combine(m) for m in members_per_seed]
            if frozen_touched:
                report.job_errors[job_name] = (report.job_errors.get(job_name, "")
                                               + " [job wrote a frozen-base file]").strip()
            _record_job(report, job_name, captures, assigned, seeds)
    finally:
        restore(snap)

    report.frozen = _verify_frozen(seeds)
    report.deckbench = _verify_deckbench()
    return report


def _record_job(report: AuditReport, job_name: str, captures: dict[str, list[bytes]],
                assigned: set[str], seeds: list[int]) -> None:
    for aid in sorted(captures):
        if aid in assigned:
            continue                      # owned by an earlier job
        assigned.add(aid)
        runs_bytes = captures[aid]
        jsonl = aid.endswith(".jsonl") or aid in GROUP_DIRS
        if len(runs_bytes) < len(seeds) or any(b != runs_bytes[0] for b in runs_bytes):
            report.artifacts.append(ArtifactResult(
                aid, job_name, "unstable", len(runs_bytes),
                characterization=characterize(runs_bytes, jsonl)))
        else:
            report.artifacts.append(ArtifactResult(aid, job_name, "stable", len(runs_bytes)))


def _uncovered_note(rel: str) -> str:
    if rel.endswith("assembly_review.jsonl"):
        return ("written by `assemble` with the frozen base; not regenerated here "
                "(would touch the frozen base)")
    if "effect" in rel:
        return ("effect-semantics overlay (Phase 4f); regenerable via the effect-* "
                "commands, not wired into this harness")
    if rel.endswith(("card_communities.jsonl", "set_network.html", "card_002_dashboard.html")):
        return ("network/community projection; regenerable via the network layer, "
                "not wired into this harness")
    if rel.endswith(("human_audit_items.jsonl", "human_audit_verdicts.jsonl",
                     "llm_dispositions.jsonl", "unresolved.jsonl")):
        return "hand-authored or agent-produced input; no deterministic producer"
    if rel.startswith("schema/"):
        return "JSON Schema exported by an unrecipe'd pipeline stage; not wired into this harness"
    if rel.startswith("reports/"):
        return "narrative / one-off report, not a rebuildable data artifact"
    return "no regeneration recipe registered in this harness"


def _enumerate_uncovered(report: AuditReport) -> list[ArtifactResult]:
    """Every derived file with no producing recipe in this harness — reported honestly as
    'not regenerable' with the reason, so 'covered' means every artifact is accounted for."""
    covered = {r.artifact for r in report.artifacts}
    covered |= set(GROUP_DIRS)
    frozen = set(FROZEN_FILES)
    out: list[ArtifactResult] = []
    seen_groups: set[str] = set()
    for path in _derived_files():
        rel = _rel(path)
        if rel in frozen:
            continue
        aid = _artifact_id(path)
        if aid in covered or aid in seen_groups:
            if aid in GROUP_DIRS:
                seen_groups.add(aid)
            continue
        if aid in GROUP_DIRS:
            seen_groups.add(aid)
        out.append(ArtifactResult(aid, "(none)", "not_regenerable", 0, _uncovered_note(aid)))
    return out


# --------------------------------------------------------------------------- #
#  Report                                                                       #
# --------------------------------------------------------------------------- #

NARRATIVE = """# Determinism audit

*Card 013 — establish which derived artifacts are actually deterministic.*

`registry.md` requires that *frozen artifacts stay byte-identical and two serial builds
agree*. This report is produced by `tools/determinism_audit.py`, which regenerates every
derived artifact several times — each in a **fresh process** with a distinct
`PYTHONHASHSEED` — and compares the bytes the code writes, never git's stored blob (under
`* text=auto` a CRLF working copy differs from an LF blob by one byte per line, which is
not a determinism signal). Run it with `python tools/determinism_audit.py --report`; it
exits non-zero if any regenerated artifact is unstable.

## What was measured before any fix (2026-09-09)

**Confirmed unstable — the only genuine case: `data/review/llm_accepted.jsonl` and
`data/review/llm_queued.jsonl`.** Two fresh regenerations (`phase3.reconcile();
phase3.finalize_faces()`, the path the test suite exercises) under different hash seeds
produced files of *identical length* but *different bytes*: for `llm_queued.jsonl`,
37 records both runs, first differing byte at offset 178; for `llm_accepted.jsonl`,
211 records both runs, first differing byte at offset 1247. In both files the multiset of
records (lines) differed, which — at equal total length — is a record differing
internally, not records reordered. The cause is in `phase3.reconcile`: `agreed_edges`,
`disputed_edges`, `agreed_abilities` and `disputed_abilities` were built by iterating
Python `set` differences/intersections, whose order is randomized per process. The order
of elements *inside* each record's list therefore varied run to run.

**The fix** sorts those set-derived keys with a total key before building the lists
(edge keys are `(source, predicate, target)` string triples; ability keys use a None-safe
total order). Records are unchanged — only their internal element order is now fixed.
Verified: two serial regenerations are byte-identical across five hash seeds, and the
canonical (order-insensitive) multiset of records is identical to the committed version
(no record added, dropped or altered). The committed `llm_accepted.jsonl` /
`llm_queued.jsonl` were rewritten once to the now-deterministic ordering so the suite
leaves the tree clean.

**Corrected premise — `card_pair_projection_audit_repair.jsonl` is stable, and not by
luck.** The card recorded this file as sorted by nothing / "stable only by luck". Measured
here, its writer sorts every record by `(source_card, target_card, relation)`, and
`add_pair` de-duplicates on exactly that triple, so the key is *total* — no ties fall back
to insertion order — and its upstream iterations are `sorted(...)`. Three fresh
regenerations are byte-identical. This is the fourth mechanism in this area to be inferred
wrong from something other than a byte comparison; `audit_repair.py` needed no change.

## Live verdicts

The table below is regenerated on every `--report` run.
"""


def _fmt_char(char: dict[str, object] | None) -> str:
    if not char:
        return ""
    rc = char["record_count"]
    return (f"records={rc}; multiset_identical={char['multiset_of_records_identical']}; "
            f"pure_reordering={char['pure_reordering']}; "
            f"record_differs_internally={char['a_record_differs_internally']}; "
            f"first_diff_byte={char['first_differing_byte_offset']}")


def render_report(report: AuditReport) -> str:
    uncovered = _enumerate_uncovered(report)
    lines = [NARRATIVE.rstrip(), ""]
    lines.append(f"Seeds this run: {report.seeds}. "
                 f"Regenerated artifacts: {len(report.artifacts)}; "
                 f"frozen verified: {len(report.frozen)}; "
                 f"deckbench verified: {len(report.deckbench)}; "
                 f"not regenerable: {len(uncovered)}.")
    lines.append("")

    def table(title: str, rows: list[ArtifactResult]) -> None:
        lines.append(f"### {title}")
        lines.append("")
        lines.append("| artifact | job | runs | verdict | detail |")
        lines.append("|---|---|---|---|---|")
        for r in sorted(rows, key=lambda x: (x.verdict != "unstable", x.artifact)):
            detail = r.note or _fmt_char(r.characterization)
            lines.append(f"| `{r.artifact}` | {r.job} | {r.runs} | **{r.verdict}** | {detail} |")
        lines.append("")

    table("Regenerated derived artifacts", report.artifacts)
    table("Frozen base (verified byte-identical, not regenerated)", report.frozen)
    table("Modeling arm — data/processed (verified against MANIFEST.sha256)", report.deckbench)
    if uncovered:
        table("Derived files with no regeneration recipe here", uncovered)

    unstable = [r for r in report.artifacts + report.frozen + report.deckbench
                if r.verdict == "unstable"]
    lines.append("### Summary")
    lines.append("")
    if unstable:
        lines.append(f"**{len(unstable)} artifact(s) UNSTABLE** — harness exits non-zero.")
        for r in unstable:
            lines.append(f"- `{r.artifact}` ({r.job}): {r.note or _fmt_char(r.characterization)}")
    else:
        lines.append("All regenerated artifacts are byte-stable across the seeds tried; the "
                     "frozen base and modeling-arm artifacts match their pinned hashes.")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Determinism audit for derived artifacts.")
    parser.add_argument("--report", action="store_true",
                        help=f"(re)write {REPORT_PATH}")
    parser.add_argument("--runs", type=int, default=3,
                        help="regenerations per artifact (fresh process each; default 3)")
    parser.add_argument("--jobs", type=str, default=None,
                        help="comma-separated subset of job names to run")
    args = parser.parse_args(argv)

    jobs = args.jobs.split(",") if args.jobs else None
    report = run_audit(jobs=jobs, runs=max(2, args.runs))
    text = render_report(report)

    if args.report:
        (REPO / REPORT_PATH).write_text(text, encoding="utf-8", newline="\n")

    unstable = [r for r in report.artifacts + report.frozen + report.deckbench
                if r.verdict == "unstable"]
    for name, err in report.job_errors.items():
        print(f"job error: {name}: {err}", file=sys.stderr)
    print(f"determinism audit: {len(report.artifacts)} regenerated, "
          f"{len(unstable)} unstable, seeds={report.seeds}")
    for r in unstable:
        print(f"  UNSTABLE {r.artifact} ({r.job}): "
              f"{r.note or _fmt_char(r.characterization)}")
    return 1 if unstable else 0


if __name__ == "__main__":
    raise SystemExit(main())
