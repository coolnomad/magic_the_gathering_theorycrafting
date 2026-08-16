I reviewed `197e314` directly. All 166 tests pass, but three issues remain before freezing Phase 6.

1. Unified coverage is now incomplete again. The new legend layer adds 55 nodes and 55 edges, but `coverage()` still reports only:

   * 2,728 frozen edges
   * 9 repair edges
   * 2,737 total

   It omits `legend_nodes.jsonl` and `legend_edges.jsonl`. The completed union is now 2,792 edges, assuming no duplicate IDs. Coverage, provenance counts, predicate counts, and origin counts should include the legend layer separately and in the union.

2. Invariant #2 remains explicitly unmodeled. The implementation correctly demonstrates:

   * Councillors listens to `event:draw_second_card_each_turn`.
   * No producer currently reaches that event.
   * No Recruit/Councillors pair relation is asserted.

   That is honest and preferable to inventing an edge, but it is an unresolved representational gap—not a completed invariant. Eventually it needs a turn-scoped draw-count state or gate:

   `draw event → increment cards-drawn-this-turn → count reaches 2 → second-draw event → Councillors`

   Recruit would then contribute one draw without being sufficient by itself.

3. The legend rule is only approximated. `max_controlled=1` says the second permanent cannot coexist, whereas Magic permits it to enter and then applies a state-based action: its controller chooses one and puts the others into their owners’ graveyards. The state also needs explicit controller scope. The current layer identifies the correct conflict class—same-name legendary permanents—but not the actual transition.

The prior problems were genuinely fixed:

* The “gold set” is honestly renamed and described as structural validation.
* Saga checks are no longer tautological.
* Multi-edge sampling now contains two genuinely distinct relation combinations.
* All 31 self-pair records are checked individually for resolved participation and absence of `another/other` paths.
* The new legend module is deterministic and covers all 55 legendary faces.
* The Dáin’s Company and Bothersome Noisemaker gaps remain clearly deferred.

Verdict: v3.1 is a meaningful correction. Have the agent add the legend layer to unified coverage, label #2 as deferred/unmodeled, and either refine the legend-rule transition or explicitly describe the present representation as a coarse conflict constraint. Then Phase 6 can be frozen with the two targeted projection repairs still tracked separately.
