# Running HOB under Ratchet — v1.1 Scope

*Drafted 2026-09-02 against HOB at `0315399` and ratchet at v1. Every factual
claim below was measured, and the command that measured it is given.*

---

## 1. What we are building

Ratchet v1 is finished and proven: it replays the recorded HOB Phase 4a-4e loop
exactly — sixteen reviews, verdict sequence, repair profile 3/2/2/2/2, two
recurrences, byte-identical ledger. But it proved that against a **synthesized**
git history, because HOB's own commits could not be read.

v1.1 makes HOB itself drivable. Four pieces of work, in dependency order:

1. Repair the commit trailer defect (§2) — the single blocking issue.
2. Declare the epoch and bring HOB under Compact (§4).
3. Write the phase contract and the verification config (§5, §6).
4. Seed the regression ratchet from the arc that already happened (§7).

Nothing here changes ratchet. If a ratchet change turns out to be needed, that
is a finding to report, not a thing to do quietly — the whole point of the
instrument is that the specification and the implementation disagree out loud.

---

## 2. The finding that makes this possible

**HOB's commits carry correct handshake trailers. No machine can read them.**

Measured over the last 80 commits:

```
commits examined                    : 80
message CONTAINS a Role: line       : 36
ratchet parse_trailers sees a Role  : 0
SHADOWED (block present, unreadable): 36
```

The cause is one blank line. `0315399` ends like this:

```
Role: worker
Phase: Phase 4
Iteration: 4f-repair2
Addresses-Review: b2697b084f595b76ca315a8b75cc8d514493d9c0
Addresses-Implementation: a8ead2f780fa6f0ef79fd6e6b30f0c333bf3f962
Validation: pytest (434 passed)
Validation: python -m hobkg.cli effect-build (x2, byte-identical)
Validation: python -m hobkg.cli effect-reconcile (0 unresolved)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

Git's trailer parser reads the **last paragraph** and nothing else. That
paragraph holds only `Co-Authored-By`, so `git log --format='%(trailers)'`
returns just that line and the entire handshake block is invisible.
`ratchet.gitstate.trailers.parse_trailers` uses the same last-paragraph rule and
agrees: zero of thirty-six.

Three things follow, and they matter more than the fix.

**The discipline was followed.** This is not a project that ignored the
protocol. Thirty-six commits carry a complete, correct, well-formed block with
role, phase, iteration and both address trailers. The failure is entirely in
paragraph placement.

**The lab notebook records it as working.** The entry for `0315399` states
"Commit trailers: `Role: worker`, `Phase: Phase 4`, `Iteration: 4f-repair2`,
`Addresses-Review`/`Addresses-Implementation` for pt18/a8ead2f." That is true of
the text and false of the machine-readable commit, and nothing anywhere would
have caught the difference. Scope §17.6 of the orchestrator already names this
species — "any generated status artifact in this system needs a machine-checked
freshness assertion or it will do the same" — and here it is again, in the
append-only log that was supposed to be the reliable surface.

**Nothing in `INSTRUCTIONS.md` asks for trailers at all.** Line 92 says "small,
frequent commits with clear messages." The trailer convention lives in
`review_event_protocol.md`, which the commit author was following from memory
while the tool appended `Co-Authored-By` as its own paragraph underneath.

### The fix

`Co-Authored-By` moves into the same paragraph as the other trailers. It is a
trailer; git treats it as one; it belongs in the block. One line of convention,
written down in `INSTRUCTIONS.md` where the commit rule already lives, with a
worked example.

### What NOT to do

**Do not rewrite history to repair the thirty-six.** Two committed artifacts pin
HOB SHAs and would break:

- `tests/fixtures/MANIFEST.json` in the orchestrator pins `source_commit`
  `0315399b8a28defb7d3c7a9117a7a339a38a03b5` for all 39 vendored review files.
- `src/ratchet/replay.py` pins `HOB_BASE_SHA = cec67643efd6ef13a3eabe9302c8001727f9e669`
  and asserts every recorded `reviewed_commit` is an ancestor of it.

A filter-branch would invalidate both and break the keystone replay that is the
project's only end-to-end proof. The past stays as it is.

**Do not loosen ratchet's parser to read a shadowed block.** Reading the
second-to-last paragraph when the last one looks like trailers is exactly the
"tolerate malformed input" move that scope §15 forbids, and it would make
`parse_trailers` disagree with git — two readers, two answers, which is the
condition this system exists to eliminate.

---

## 3. HOB as it actually stands

Verified, not taken from `HANDOFF.md`:

| | |
| --- | --- |
| HEAD | `0315399` — "Effect-semantics Phase 4f repair 2" |
| Working tree | 7 dirty entries, including two untracked watcher scripts |
| Tests | **434** test functions across 38 files |
| Effect layer | 244 effects on 144 faces; 9,032 pairs; `CAN_EXILE` 537 |
| Reconciliation | 240 extracted, 4 deferred, 0 unresolved |
| Determinism | two serial `effect-build` runs byte-identical |
| Compact project? | **No** — no `registry.md`, no `tasks/`, no `audit/` |

**`HANDOFF.md` is stale, again.** It reports the graph "FROZEN at `8201109`,
ALL reviews pt1-pt11 resolved, 227 tests pass." That describes the build-spec
Phase 6 freeze. The effect-semantics arc came afterwards and is now at 434 tests
and Phase 4f. Arc A pt9 found this file stale in 2026-08; it is stale again.

**Two phase numbering schemes are in circulation and they collide.** The build
spec has Phases 0-6, where Phase 4 is graph assembly and Phase 6 is higher-order
mechanism assembly. The effect-semantics repair has its own Phase 1-4 with
sub-phases 4a-4f. The orchestrator's vendored corpus contains both: `arc_a` is
`hob-kg-phase6-*` (build spec Phase 6) and the Phase 4 corpus is
`hob_effect_semantics_..._PHASE4_*` (effect-semantics 4a-4f). A phase contract
that says "Phase 4" without saying which is ambiguous, and the `Phase:` trailer
inherits that ambiguity. **Pick one namespace and qualify it** — `effect-4f`,
`buildspec-6` — before the first card runs.

---

## 4. The epoch

The declared epoch is HOB's HEAD at the moment the trailer convention lands.
Commits before it are pre-protocol and out of scope for the ledger; commits
after it must satisfy the guard.

This is the same move ratchet made on its own history at `da1cc9a`, for the same
reason, and `ledger.rebuild(root, since=...)` from card 023 is the mechanism.
Record the epoch SHA in this document when the convention commit lands.

The guard is not relaxed. A commit inside the epoch with no `Phase` trailer
raises `LedgerError` naming it — `tests/test_ledger_rebuild.py::
test_unbounded_rebuild_raises_naming_the_phaseless_commit` fails if anyone
weakens that.

---

## 5. The phase contract

Card 015 built the artifact type; HOB supplies the content, and it already
exists in prose.

**Invariants** come from `docs/hob-knowledge-graph-build-spec.md` §"Semantic
invariants" — seventeen numbered, card-specific, individually testable claims,
each already phrased as a testable proposition (Recruit always yields draw then
discard; a legendary artifact counts once, not twice, for Storied; equipped-creature
bonuses resolve to the *same* bound creature). This is the exact shape card 015's
template was modelled on, and the mapping to named tests is mostly discoverable:
38 test files whose names track the families.

**Acceptance cases** come from `docs/hob_effect_semantics_repair_instructions.md`
§"Acceptance Gates" — thirteen numbered conditions, several already machine-checkable
(frozen artifact hashes unchanged; two clean rebuilds byte-identical; zero provenance
gaps and zero unresolved condition references).

Card 015 requires each acceptance case to be **individually addressable by id**,
so a deferral can be checked against it. Doing that here retires the prose
word-subset heuristic in `escalation.build_acceptance_case_predicate` — see
`REVIEW_NOTES.md` §A5 and §G1. That is the single highest-value cleanup this
scope enables, and it is a ratchet repair card, not a HOB card.

**Mandatory regressions** come from the same document's §"Mandatory Regression
Cases": Warg Tactics, Reverent Howl, Pinecone Strike, and the removal/damage,
buffs, tapping and search families.

The contract is committed **in its own commit**, separate from implementation.
Scope §17.4 records why: HOB put a spec amendment and a code change in the same
commit (`bf16c01`), which is why "the contract as of the reviewed SHA" is not
recoverable for the Phase 6 arc.

---

## 6. The verification config

`ratchet.verification.VerificationConfig` is JSON, `extra="forbid"`, and each
command is `shlex.split` with `shell=False` — **no shell**, so no `&&`, pipes,
globs or redirects. Hash a produced file by naming it in `artifacts`, not by
piping to `sha256sum`.

HOB's commands are already known from the lab notebook's own validation lines:

| Kind | Command | What it evidences |
| --- | --- | --- |
| `test` | `python -m pytest -q` | 434 tests |
| `determinism` | `python -m hobkg.cli effect-build` | run twice; artifacts must hash identically |
| `report` | `python -m hobkg.cli effect-reconcile` | "240 extracted, 4 deferred, 0 unresolved" |
| `report` | `python -m hobkg.cli coverage` | the coverage report the build spec mandates |
| `hash` | frozen artifacts with `baseline_sha` | "unchanged since acceptance", machine-checked from git |

The determinism artifacts are the three the notebook already hashes:
`effect_records`, the projection pairs, and `pair_index`.

**One known hazard.** The notebook records that `test_suppressions` and
`test_pair_index` exhibit "cross-test generated-artifact interference — green on
a clean ordered run; passes in isolation." A suite that depends on ordering is a
suite whose green is conditional, and the regression ratchet runs guard tests
*individually* (`pytest <node_id>`) to check liveness. Order-dependent tests
should be fixed rather than declared around; if they cannot be, that is a
finding for the contract's approved deferrals with a stated closure consequence.

---

## 7. Seeding the ratchet

Two defect classes demonstrably recurred and are the reason the ratchet exists:

- **path connectivity** — raised at Arc A pt5, repaired, raised again at pt8 in
  the reviewer's own words as "the same class of failure pt5 exposed";
- **coverage-union** — across pt2 and pt3.

Plus the two the keystone replay detects in the effect-semantics arc:
`selector.zone_mismatch` (pt14) and `projection.overbroad_binding` (pt15).

Each gets a `class_id`, a named live guard test, and a registration in
`cycle/regression_ledger.json`. Register them **before** the first cycle, so the
ratchet starts from what the project already learned instead of relearning it.

Note the caveat in `REVIEW_NOTES.md` §A7: occurrence counts are seeded at 1 per
registered class and the live count lives in memory, so a controller restart
resets a class's recurrence count. With four seeded classes that is a real
exposure, and it is a ratchet repair card worth doing before a long HOB run.

---

## 8. Standing constraints

- **The frozen base is frozen.** Do not rewrite it; do not minimize edge count
  at the expense of faithful generic relations; do not patch only the named
  audit pairs (`repair_instructions` §Non-Goals).
- **Coverage is not correctness.** The build spec says so outright. A green
  suite was wrong in 6 of 11 Arc A rounds.
- **No card-name or UUID branches in reusable engine code** (acceptance gate 7).
- **Append-only logs stay append-only.** `LABNOTEBOOK.md` and
  `CONVERSATION_LOG.md` take corrections as new entries, never edits.
- **Do not claim full action simulation.** It is acceptable to preserve a
  semantic fact as structured but nonexecutable, provided that status and the
  missing capability are explicit.

---

## 9. Task plan

Four cards, to be refined by a `compact greenfield hobkg` session against this
document.

1. **The trailer convention.** Move `Co-Authored-By` into the trailer block;
   document the convention in `INSTRUCTIONS.md` with a worked example; add a
   check that a commit's block is visible to `git log --format='%(trailers)'`.
   Declare the epoch SHA. *This card's own commit is the first conformant one.*
2. **Compact adoption.** Land `registry.md` and `tasks/`; express the remaining
   effect-semantics families as numeric cards; settle the phase-namespace
   ambiguity (§3).
3. **The phase contract.** Seventeen invariants mapped to named tests, thirteen
   acceptance gates as addressable cases, mandatory regressions, closure
   criteria. Committed separately from implementation.
4. **Verification config and ratchet seeding.** The JSON command set of §6; the
   four registered defect classes of §7 with live guards.

Then the first real cycle: one bounded slice of the remaining effect-semantics
work, run end to end, producing an implementation commit, a verification block,
a committed review at an exact SHA, a derived verdict, and a ledger line that
rebuilds byte-identically.

That run is the actual milestone. Everything above it is setup.
