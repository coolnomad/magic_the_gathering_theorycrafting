Phase 6 v1 is a sound start, but it is not ready to freeze.

What works:

* 148 tests pass.
* It deterministically creates 22 formal modules.
* Recruit, Storied, Amass, Ferocious, Landfall, Saga, Hone/Equipment, graveyard reuse, second-draw, gates, and token production are represented.
* Storied persistence is detected as a feedback cycle.
* The tested invariants for Recruit, Storied counting, persistence, Adventure faces, and “other/another” object classes pass.

Three important gaps remain.

1. **The repair layer is completely excluded.**

`_Graph` loads only `edges.jsonl` and `nodes.jsonl`. None of the 9 validated repair edges or the repair operation node appears in any Phase 6 module.

Consequently Phase 6 misses:

* Thranduil modifying Elf objects;
* Head of the Hunt supplying Wolves to Chief Warg’s Company;
* Clap! Snap! enabling Great Goblin;
* the repaired life-loss and activated-ability trigger structures.

Phase 6 should assemble over:

```text
frozen nodes + repair nodes
frozen edges + repair edges
```

while retaining each edge’s origin.

2. **Token-production coverage is incomplete.**

The graph creates 11 token types, but Phase 6 emits only 10 token modules. `token:human-soldier` is omitted because Recruit creates it through a gate whose ID contains no card UUID. Token modules should begin from every `CREATES_OBJECT → token:*` target, then traverse upstream through gates/rules to recover participating cards.

3. **It does not yet perform the general discovery promised by the spec.**

It iterates generically over gates, but most other modules are hard-coded. There is no comparable discovery over shared:

* resources,
* events,
* persistent states,
* object classes,
* state transitions.

That is why structures such as noncreature-spell cast → Noisemaker and Dwarf/Equipment → Dáin’s Company still do not appear. Those need either generalized anchor discovery or the already-noted fresh audit/repair pass.

The commit also explicitly defers most remaining semantic invariants, the coverage report, and the manual gold set. That is honest, but those are completion requirements rather than optional enhancements.

Recommended Phase 6 v2:

1. Union frozen and repair layers.
2. Emit a module for every created token, including gate-mediated production.
3. Discover modules around shared resource/event/state/object anchors using structural rules, then label recognized patterns.
4. Add the remaining semantic-invariant tests.
5. Produce the required coverage report and stratified gold-set review.

So: good module framework, correct first vertical slice, but not complete Phase 6 yet. It also does not yet implement the separate capability projection needed to derive “removal count” and connect such features to deck outcomes.
