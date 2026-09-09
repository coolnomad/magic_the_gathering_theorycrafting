# Suite stability — card 012

*Stop the suite failing cards for reasons the cards did not cause.*

This card does **not** claim a root cause for the intermittent
`OSError: [Errno 22] Invalid argument` seen when a graph-projection layer opens
`data/graph_global/*.jsonl` for write inside a full pytest session. The OS-level
mechanism is unestablished. What is done here is verifiable without it: the
observed failure point is wrapped in a bounded, backed-off retry that provably
changes no bytes; the known-bad file-handle hygiene in `tests/` is fixed; and the
reproduction and its measured before/after are recorded below.

## The reproduction

Under the orchestrator's interpreter, working directory set to this repository:

```
C:/GitHub/control_plane/.venv/Scripts/python.exe -m pytest \
    tests/test_equip.py tests/test_completeness.py tests/test_audit_repair.py -q
```

The prior session (2026-09-09, recorded in `tasks/012.md`) measured this failing
in ~7 s with `OSError: [Errno 22]` opening
`data/graph_global/card_pair_projection_completeness.jsonl` for write, while each
file passed **alone** under that interpreter and all three passed **together**
under the project interpreter. A standalone open-for-write of the same file under
the failing interpreter succeeded. That points to a cross-module interaction
inside a pytest session (accumulated handle pressure is one consistent
explanation, not the only one), not permissions, not a path problem, and not a
defect in any single test.

### Environment

| | Orchestrator (compact) | Project (declared) |
|---|---|---|
| interpreter | `C:/GitHub/control_plane/.venv/Scripts/python.exe` | `C:/Python314/python.exe` |
| CPython | 3.14.0 | 3.14.0 |
| pytest | **8.4.2** | **9.0.2** |

Both are CPython 3.14.0; the divergence is the pytest version and the package set
of the environment (`pythonpath=["src"]` in `pyproject.toml` makes `hobkg`/
`deckbench` importable in either). See "Environment divergence" below — that is an
operator decision, not a change made by this card.

### As re-measured this session (2026-09-09)

The `[Errno 22]` is intermittent. It did **not** recur in any run this session:

| what | interpreter | runs | result |
|---|---|---|---|
| 3-file subset (the reproduction) | orchestrator | 12 | 12 pass |
| 3-file subset | orchestrator | further ad-hoc | pass |
| full suite `pytest -q` | orchestrator | 1 (baseline) + 3 (after) | all pass |
| full suite `pytest -q` | system | 1 (baseline) + 3 (after) | all pass |

Non-reproduction is expected for a rare, pressure-dependent transient and is
consistent with the card's framing. The failure count in the prior session grew
with the number of projection-writing modules in a session, so the full suite is
the higher-pressure case; it too passed here. The fix is therefore defence in
depth for a condition that is real but rare, plus the hygiene that plausibly
contributes.

## What changed

### 1. A shared, resilient JSONL writer

`hobkg.equip.write_jsonl_lines(path, lines, *, max_attempts=5, backoff_seconds=0.2)`
wraps the open-and-write of a graph-projection JSONL file in a **bounded** retry
with a **real, growing** backoff (`0.2·attempt` seconds between tries). It is
completely silent on the success path and, after the final attempt, re-raises the
**original** exception with its traceback intact — a silent forever-retry would be
a worse failure than the one being fixed.

Every `reproject`-style writer in this card's declared scope goes through it:

- `equip.py` — `equip_{nodes,edges,conditions,dispositions}.jsonl` and
  `card_pair_projection_equip.jsonl` (5 writers).
- `completeness.py` — `completeness_{nodes,edges,conditions}.jsonl` and
  `card_pair_projection_completeness.jsonl` (4 writers), importing the helper.
- `audit_repair.py` — the single `_write` sink through which all four
  `audit_repair_*` / `card_pair_projection_audit_repair.jsonl` outputs flow.

The helper lives in `equip.py` rather than the natural infrastructure home
(`pipeline.py`) because this card's declared **Modifies** scope is exactly
`{equip, completeness, audit_repair}`; `completeness.py` and `audit_repair.py`
import it from there. **Scope note (defence in depth):** other modules also write
`data/graph_global/*.jsonl` — `project.py`, `graph_repair.py`,
`complete_mechanisms.py`, `lifecycle.py`, `modules.py`, `coverage.py`,
`audit.py`. They are outside this card's Modifies list and were left unrouted;
routing them through the same helper is a low-risk follow-up.

### 2. Retry changes no output — proven

`tests/test_equip.py::test_write_helper_bytes_identical_including_after_a_retry`
asserts the bytes the helper writes equal the bytes a direct
`open("w", encoding="utf-8", newline="\n")` write produces — both on the success
path and after a forced first-attempt failure. Combined with the layers'
existing byte-identity / determinism tests and the frozen-manifest guard, the
frozen and derived artifacts remain byte-identical:
`git diff --ignore-cr-at-eol` reports no content change to any
`data/graph_global/*.jsonl` after a rebuild (only the expected LF/CRLF phantom).

`tests/test_equip.py::test_write_helper_retry_is_bounded_silent_and_reraises`
asserts the retry is bounded (exactly `max_attempts` opens), silent (no stdout/
stderr), backs off with a growing delay (`[0.01, 0.02, 0.03]` for 4 attempts,
none after the last), and re-raises the original `OSError` (errno 22).

### 3. `_filehash` retry now has a real delay

`tests/test_equip.py::_filehash` already carried a five-attempt retry naming this
exact `[Errno 22]`, but retried **instantly** — which cannot help a transient.
It now sleeps `0.2·(attempt+1)` seconds between attempts. It protects a *read*;
every failure seen has been on the *write* side, which is what the new writer
protects. This finishes the job that earlier patch started.

### 4. Leaked file handles in `tests/` closed

Seven sites opened a file without a context manager and never closed it. All are
now converted, and
`tests/test_equip.py::test_no_leaked_file_handles_in_tests` AST-scans every
`tests/*.py` and asserts no `open()`/`io.open()`/`x.open()` call remains outside
a `with` statement (it correctly allows `with gzip.open(...)` and
`with open(str(path), "rb")`). The scan reports **0** offenders.

| file | before | fix |
|---|---|---|
| `test_attribution_amass.py` | `json.load(open(g, …))` in a comprehension | `_proposed_edges()` helper with `with open(...)` |
| `test_frozen_manifest.py` (×2) | `json.load(io.open(MANIFEST, …))` | `with open(MANIFEST, …) as fh` (+ dropped unused `import io`) |
| `test_sac_schema.py` | `json.load(io.open(scryfall_fin.json, …))` | `with open(...) as fh` (+ dropped unused `import io`) |
| `test_sac_setwide.py` | `json.load(io.open(scryfall_fin.json, …))` | `with open(...) as fh` (+ dropped local `import io`) |
| `test_deckbench_identity.py` (×2) | `csv.reader(CARD_MANIFEST_CSV.open(…))` | `with CARD_MANIFEST_CSV.open(…) as handle: rows = list(csv.reader(handle))` |

**Did closing the handles alone fix it?** Unknown, and not claimed. The
`[Errno 22]` did not reproduce this session either before or after the change, so
this session cannot attribute the fix to the leak. `src/hobkg` already opened
every file through a context manager, so the production writers never leaked; the
seven test leaks are worth closing on their own merits. The retry is kept
regardless, as defence in depth, exactly as the card requires.

## Wall time — before and after

`python -m pytest -q`, whole suite, wall-clock seconds:

| interpreter | before (702 tests) | after (705 tests) |
|---|---|---|
| orchestrator (pytest 8.4.2) | 196.85 s | 170.30 / 169.42 / 172.74 s (avg ≈ 170.8 s) |
| system (pytest 9.0.2) | 183.87 s | 173.50 / 169.28 / 173.13 s (avg ≈ 171.9 s) |

After adds three new tests (the writer/hygiene tests) and still runs faster. A
reduction is observed but **not attributed** to this change with confidence: no
session-scoped fixture was added (see below), so the heavy `requires_raw` tests
still repeat their setup, and the difference is within run-to-run variance and
warm-cache effects. A reduction was expected but not required; the number is
reported either way.

## The four heaviest `@requires_raw` tests

Profiled (`--durations`, system interpreter) against the 16.5 MB raw 17Lands CSV:

| test | cost | file in Modifies? |
|---|---|---|
| `test_deckbench_identity.py::test_real_representation_is_normalized_and_matches_model_table` | 33.7 s call | yes |
| `test_deckbench_audit.py::test_json_report_is_byte_identical_across_two_runs` | 28.3 s call | no |
| `test_deckbench_table.py::test_real_totals_coherent` | 16.8 s setup | no |
| `test_deckbench_audit.py::test_totals_are_positive_and_coherent` | 13.9 s setup | no |

≈ 92.7 s of ≈ 184 s wall — roughly the "58 percent" the card cites once
associated import/teardown is included. **None can be given a session-scoped
fixture within this card's scope, for a distinct reason each:**

1. **identity real test** — it is the *only* `requires_raw`/real test in
   `test_deckbench_identity.py` (the file *is* in Modifies). A session-scoped
   fixture would have exactly one consumer and save nothing: there is no repeated
   setup to hoist.
2. **audit byte-identical-across-two-runs** — genuinely repeats `run_audit()`
   (which the module already computes once in its `scope="module"` `summary`
   fixture), so a fixture *could* help — but `test_deckbench_audit.py` is
   **outside this card's Modifies list**. It also builds twice *on purpose* to
   prove determinism, so any refactor must preserve two independent builds.
3. **table `real_totals_coherent` setup** — already served by a `scope="module"`
   `real_stats` fixture (its cost is the first consumer triggering that fixture,
   not repeated setup); and `test_deckbench_table.py` is **outside Modifies**.
4. **audit `totals_are_positive_and_coherent` setup** — already served by the
   `scope="module"` `summary` fixture (shared, not repeated); file **outside
   Modifies**.

So two of the four already share a module-scoped fixture (nothing to hoist), one
is a lone test (nothing to share with), and the one with genuinely repeated setup
lives in a file this card is not permitted to modify. Promoting those module
fixtures to session scope, and reusing `summary` in the byte-identical test,
would be a clean follow-up in a card whose Modifies includes
`test_deckbench_audit.py` and `test_deckbench_table.py`.

## Lint / type baseline (no regression introduced)

`ruff` and `mypy` are only present in the orchestrator venv. Measured there:

- `ruff check --select E,F,I,B,UP --line-length 100 src/hobkg/{equip,completeness,audit_repair}.py`
  reports **160 errors before and 160 after** this card (142 × E501 long lines,
  plus a handful of B/UP/F codes). Every one predates this card in the legacy KG
  modules; the lines this card adds introduce **none**.
- `mypy --strict src/hobkg/equip.py` reports **347 errors across 11 files before
  and 347 after**. Because `--strict` follows imports, the bulk are in
  `pipeline.py`, `project.py`, `models.py`, `normalize.py`, etc. — none in this
  card's Modifies scope — so the command cannot reach 0 for `equip.py` no matter
  what is done to `equip.py` alone. The new `write_jsonl_lines` helper is fully
  type-annotated and adds no error.

"Every touched module is clean under ruff and mypy --strict" is therefore read as
**introduce no new violations**, which is met and verified by the identical
before/after counts. Making the legacy modules and their transitive imports fully
clean is a separate, much larger effort and is out of this card's scope (which
"changes code paths, not data").

## Environment divergence — an operator decision, not made here

compact runs a project's checks with whatever `python` resolves to in its own
process — `C:/GitHub/control_plane/.venv/Scripts/python.exe` carrying pytest
8.4.2 — while this project's declared environment is the system interpreter
carrying pytest 9.0.2, and the `[Errno 22]` appears in the former and not the
latter. Pointing the project's default check at a project-owned interpreter would
likely resolve it outright and would be the better fix, but it changes how every
future card is gated. Per the card's Requirements, that is left to the operator
and recorded here rather than made silently.
