Phase 6 v2 is substantially better, but still not ready to freeze. All 157 tests pass.

Successfully fixed:

* Frozen and repair graph layers are unioned for module construction.
* Repair-derived life-loss, counter-placement, activated-ability, Wolf, and Elf structures now participate.
* All 11 created token types receive modules, including Recruit’s gate-mediated Human Soldier.
* General discovery adds 14 shared-anchor modules across events, resources, counters, and object classes.
* A coverage report and gold-set candidate list are generated.

Remaining blockers:

1. **Coverage reports only the frozen layers.**

It reports:

* 2,728 Phase 4 edges, omitting 9 repair edges and 1 repair node.
* 5,278 mechanical relations, omitting 3 audit relations and 8 repaired relations.
* `edges_by_origin = {"phase4": 2728}`, which is not the completed graph.

Coverage should report each layer separately and their deduplicated union.

2. **The ordered-pair completion criterion is still unmet.**

There are only 5,278 relation records, not 37,249 ordered-pair records. Empty pairs are absent. The current test merely asserts `pair_relations_total > 0`.

Add a pair index with exactly:

[
193^2=37{,}249
]

records, each containing zero or more mechanical, audited, and repaired relations.

3. **The “gold set” is a review queue, not a reviewed gold set.**

The report explicitly says “Review each stratum by hand.” It contains no expected verdicts, reviewer dispositions, corrections, or pass/fail results. Therefore the spec’s “hand-review before full acceptance” gate remains open.

Also, its samples are weakly diversified:

* all 20 null pairs use Old Thrush as the source;
* most multi-edge pairs are repetitive Storied/infrastructure combinations.

4. **Some semantic invariants remain untested.**

Still missing substantive regression tests for:

* Recruit → Master’s Councillors only through second draw and never reverse;
* legend-rule conflicts as state constraints;
* self-pair object identity versus separate-copy effects.

The mana-color invariant is covered elsewhere.

5. **Module subgraphs remain anchor-local.**

Eight of nine repair edges appear in modules; the missing edge is Thranduil Ability → anthem Operation. The Elf module contains the `MODIFIES` edge but not the causal edge connecting the printed ability to that operation. For a genuinely expandable formal subgraph, include the provenance path from card/ability through operation to anchor.

6. **The known sealed-deck gaps remain.**

No discovered module captures:

* Dwarf/Equipment support for Dáin’s Company;
* noncreature-spell casts enabling Bothersome Noisemaker.

Those require the planned targeted audit/repair pass because the necessary primitive connections are still missing.

Verdict: the higher-order module system now works and the major Phase 6 v1 defects are fixed. What remains is mostly completion discipline—unified coverage, the 37,249-pair index, real gold-set adjudication, three semantic invariants, and the targeted projection-gap repair.
