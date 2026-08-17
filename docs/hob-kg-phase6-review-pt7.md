I read through the four new commits through `a51b832`. This is a substantial improvement and it directly addresses the Crude Bent Blade case.

What now works:

* Crude Bent Blade → Stir Up Trouble:

  * `SATISFIES_SACRIFICE_COST`
  * artifact typing is used
  * controlled and battlefield constraints are carried
  * Stir’s alternative `{4}` payment is recorded
  * `terminates_attachment: true`

* Crude Bent Blade → Snowslope Hunter:

  * `SATISFIES_SACRIFICE_COST`
  * controlled and battlefield constraints are carried
  * the important `another` constraint is present
  * attachment termination is recorded

The resulting path is grounded and directed:

```text
Crude card
 → Crude face
 → Artifact type
 ← CONSUMES — sacrifice operation
 ← Hunter/Stir ability
 ← consumer face
 ← consumer card
```

The broader completeness pass also addresses the three previously identified families:

* all genuine card-draw operations now feed the second-draw state;
* token creators can enable token-entry triggers;
* creature-sacrifice operations can enable dies triggers;
* artifacts and creatures project into compatible sacrifice outlets.

All 218 tests pass locally.

## Remaining issues

The main remaining problem is that this is a correct analytical projection but not yet a complete state-transition representation.

`terminates_attachment: true` is metadata on the pair relationship. There is no actual primitive transition such as:

```text
sacrifice Crude
  MOVES_FROM → battlefield
  MOVES_TO → graveyard
  TERMINATES → Crude attachment state
```

The graph knows that the relationship ends, but a simulator or intervention engine cannot yet execute that change. I would add a general invariant:

```text
If permanent P leaves the battlefield:
  terminate every attachment state hosted by P
  terminate every continuous effect requiring that state
```

Likewise, Stir’s `or_pay: "{4}"` is stored in gate data rather than modeled as an explicit OR gate:

```text
additional casting cost
  OR
  ├── sacrifice artifact or creature
  └── pay {4}
```

That is adequate for deck-feature extraction, but not yet adequate for autonomous execution.

## One semantic naming problem

The new `SAC_OUTLETS` catalogue mixes:

* actual costs: Stir, Snowslope Hunter;
* optional effects: Rhovanion Rampager, Bolg, Sackville-Bagginses.

All resulting pairs are called `SATISFIES_SACRIFICE_COST`. That is inaccurate for optional sacrifice effects. I would separate them:

* `SATISFIES_SACRIFICE_COST`
* `IS_ELIGIBLE_SACRIFICE_TARGET`

Otherwise a deck analysis could mistakenly count Bolg as requiring sacrifice fodder when sacrifice is an optional resolution choice rather than a cost.

## Portability concern

The sacrifice catalogue is currently a hand-authored dictionary of nine Hobbit face IDs, with `oracle_span: null`. That is fine as a frozen repair, but not yet the reusable workflow you want. The harness should mechanically detect sacrifice clauses, parse:

* accepted types;
* cost versus effect;
* `another`;
* optionality;
* OR-payment;
* activation/casting timing;
* exact Oracle span;

then send only ambiguous cases to the LLM.

The Equipment disposition problem was handled correctly: complex effects such as Glamdring and Orcrist have been reclassified as unresolved/schema-extension requirements instead of being called deliberately ignored.

My verdict: **the requested Crude Bent Blade relationship is now represented correctly for deck-space analysis.** Before calling the mechanism fully executable or portable, I would require explicit lifecycle transitions, cost/effect separation, explicit OR gates, and automatic sacrifice-clause extraction.
