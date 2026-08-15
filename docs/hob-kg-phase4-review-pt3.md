Phase 4 v2 fixes the seven problems from the previous audit, but it reveals a new blocking issue: the assembled graph is structurally valid but incomplete. I would not begin Phase 5 pair projection yet.

## What now passes

The reported zero metrics are genuine:

* zero dangling edges;
* zero unknown endpoint types;
* zero signature violations;
* zero leaked ability aliases;
* zero unresolved condition references;
* zero missing edge IDs;
* zero detected template duplicates;
* zero face-to-rule Amass edges.

Other previous defects are also fixed:

* exactly 447 Ability nodes: 418 namespaced LLM abilities plus 29 Phase 2 abilities;
* full ability records are retained;
* actor effects are grouped into operations;
* property-distinct parallel edges coexist;
* all 2,016 edges have stable IDs;
* global conditions are self-contained;
* the seven specific malformed edges were corrected.

That part is good.

## Blocking issue 1: normalized card characteristics are absent

All 210 normalized faces have parsed type information, but none of it is carried into the global face nodes.

For example:

```json
{
  "id": "face:...:0",
  "type": "CardFace",
  "label": "Great Ugly-Looking Goblin",
  "data": {}
}
```

The same is true for Clap! Snap!, Island, and every other face.

Across the global graph:

* 210 CardFace nodes;
* **0** with type-line data;
* **0** with mana-cost data;
* **0** with power/toughness data;
* only **1 `HAS_TYPE` edge**;
* only **12 `HAS_COST` edges**.

But the normalized source has:

* 210/210 faces with parsed types;
* 197 faces with mana costs;
* 22 mana-producing faces.

This means the assembled graph cannot systematically answer:

* Which cards are creatures, artifacts, Goblins, Elves, Halflings, or legendary?
* Which cards can Island help cast?
* Which creatures qualify as targets?
* Which cards satisfy tribal conditions?
* What are the curve and colored-pip requirements?
* Which cards naturally produce mana?

Those are foundational pair-projection inputs.

### Required fix

Materialize normalized characteristics during assembly:

```text
CardFace ──HAS_TYPE──> CardType
CardFace ──HAS_TYPE──> Subtype
CardFace ──HAS_TYPE──> Supertype
CardFace ──HAS_COST──> structured mana Cost
mana ability Operation ──PRODUCES──> mana Resource
```

Also retain normalized fields in node data:

```json
{
  "role": "primary|adventure",
  "type_line": {...},
  "mana_cost": {...},
  "power": "...",
  "toughness": "...",
  "produced_mana": [...],
  "oracle_text": "..."
}
```

Card nodes should retain layout, color identity, rarity, and source identifiers.

## Blocking issue 2: token characteristics are mostly discarded

There are 12 TokenSpec nodes, but only `token:human-soldier` retains characteristics. The other 11 have empty data, including:

* Treasure;
* Axe;
* Dwarf;
* Bird Soldier;
* Goblin Army;
* Wolf;
* Dragon;
* Bear;
* Elf;
* Stone Boulder.

The normalized token file already contains these characteristics. Assembly should copy them into the global nodes and produce the relevant type/qualification edges.

This matters immediately for Storied, tribal interactions, Army selection, flying, artifact counting, and creature-body production.

## Blocking issue 3: most conditions remain unstructured prose

The output contains 147 condition records:

* 45 structured;
* **102 encoded as `{"raw": "..."}`**.

Examples include:

```text
if you sacrifice another creature this way
third resolution this turn
combat damage to a player, mode: second option chosen
you have an enduring story
X = number of cards discarded this way
```

They are now self-contained, but they are not machine-evaluable. The original spec requires structured expressions, not prose stored inside an expression wrapper.

At minimum, distinguish:

```text
structured
raw_unresolved
```

Raw conditions must not be treated as executable or automatically composed during pair projection. Prefer converting common families mechanically:

```json
{"op":"event_identity","event":"sacrifice","binding":"this_way"}
{"op":"eq","left":{"state":"ability_resolutions_this_turn"},"right":3}
{"op":"mode_selected","mode":2}
{"op":"state_active","state":"enduring_story"}
{"op":"eq","left":{"variable":"X"},"right":{"count":"cards_discarded_this_way"}}
```

Any condition that cannot be parsed should remain explicitly unresolved.

## Blocking issue 4: Adventure template duplicates remain undetected

The template-duplicate metric reports zero because its detector covers only a narrow set of endpoints.

The assembled graph still contains:

* 17 authoritative Phase 2 Adventure resolution-state paths;
* at least 8 LLM-derived reminder-text operations independently moving the Adventure card to exile.

For example:

```text
Phase 2:
cast → can resolve → produces adventure_exiled(X)

LLM reminder expansion:
adventure-effect operation → MOVES_TO exile
```

These are parallel encodings of the same Adventure rule, and the LLM form lacks the stronger object-bound resolution semantics.

The LLM provenance should be merged into the authoritative template path, not retained as a second mechanism. Apply the same path-level audit to Recruit, Storied, Saga, and hone. Endpoint-based duplicate detection is insufficient.

## Acceptance tests needed

Add tests requiring:

```python
assert cardface_count == 210
assert all_faces_retain_normalized_type_data()
assert every_normalized_type_has_canonical_type_edges()
assert every_mana_cost_face_has_a_structured_casting_cost()
assert every_mana_producer_has_a_mana_operation()
assert all_12_tokens_have_complete_characteristics()

assert raw_executable_conditions == 0
assert every_raw_condition_is_marked_unresolved()

assert adventure_count == 17
assert adventure_resolution_state_paths == 17
assert llm_reminder_adventure_exile_paths == 0
```

Also verify that all normalized entity provenance survives into the global graph.

## Verdict

Phase 4 v2 is a successful **structural assembly**, but it is not yet a complete **mechanistic assembly**. The current all-zero report only covers internal graph integrity; it does not cover normalized-entity completeness or path-level template duplication.

Send the agent:

> Extend Phase 4 assembly to materialize all normalized card, face, mana, type, subtype, supertype, P/T, color, and token characteristics. All 210 faces and 12 token specifications must retain their normalized data and corresponding canonical type/cost/resource edges. Convert common edge conditions into structured expressions and mark any remaining raw conditions explicitly unresolved and non-executable. Replace endpoint-only template deduplication with path-level mechanic deduplication; remove LLM reminder-text Adventure exile operations and merge their provenance into the 17 authoritative object-bound Adventure template paths. Add completeness and path-level duplicate gates before Phase 5.

[Phase 4 v2 commit](https://github.com/coolnomad/magic_the_gathering_theorycrafting/commit/fbbbfe4)
