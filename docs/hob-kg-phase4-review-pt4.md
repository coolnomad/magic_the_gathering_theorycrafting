I checked newest commit [`9bc063a`](https://github.com/coolnomad/magic_the_gathering_theorycrafting/commit/9bc063a4cf9cb7d03599794a24abf9818459c0ce). It is a substantial improvement, and all 88 tests pass. However, I found three semantic defects that should be corrected before Phase 5.

1. Indirect mana production is being turned into a direct ability

The backfill creates operations such as:

```text
Long-Bodied Grey Dog → produce mana → resource:mana
Bejeweled Warg → produce mana → resource:mana
```

These cards do not directly produce mana. Scryfall’s `produced_mana` can reflect indirect production through Treasure tokens. The correct path is:

```text
card ability → creates Treasure
Treasure → has mana ability
Treasure mana ability → produces mana
```

The present representation removes the cost, condition, delay, and token dependency. `_backfill_mana_operations()` should only synthesize a direct operation when Oracle text actually contains a mana ability. Otherwise, the completeness test should require a mechanistic path to mana, not a direct `PRODUCES` operation.

2. The condition parser marks partial or inverted interpretations executable

Concrete failures include:

* `"you do not have an enduring story"` becomes positive `state_active(enduring_story)`.
* `"combat damage to a player, mode: second option chosen"` becomes only `mode_selected(2)`, losing the combat-damage requirement.
* `"X = number of cards discarded this way"` becomes `event_identity(discard)`, because the broad “discarded this way” rule runs before the variable-binding rule.
* `"third resolution this turn"` remains unresolved despite being one of the intended mechanical conversions.

The safe rule should be:

> A condition is executable only when the parser represents the entire condition, including negation and every conjunct.

Otherwise it must remain `raw_unresolved`. Compound conditions need `and`, negation needs `not`, and parser patterns should be ordered from specific to general.

3. Newly synthesized primitive edges have no provenance

For example, the new `HAS_TYPE`, `HAS_COST`, synthetic mana, and token-mana edges commonly contain:

```json
"provenance": []
```

That violates the project’s principle that every asserted primitive edge must have provenance. Deterministic derivations can cite:

```json
{
  "source": "normalized_face",
  "source_id": "...",
  "field": "type_line|mana_cost|produced_mana",
  "derivation": "phase4_materialization"
}
```

For indirect mana, provenance alone is insufficient—the false direct edge should be removed.

My verdict: Phase 4 v3 now passes structural completeness and Adventure deduplication, but it is not yet semantically safe for pair projection. The necessary closure pass is narrow:

* replace the direct-mana gate with mechanistic mana reachability;
* make condition parsing lossless or unresolved;
* attach derivation provenance to every materialized edge;
* add regression tests for the exact failures above.

After that, I would accept Phase 4 and begin Phase 5.
