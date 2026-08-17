Phase 2 is a useful vertical slice, but I would not accept it as complete yet. The destruction projection is mostly correct, but the structured representation has one concrete bug and several schema gaps.

## Blocking defect: every destruction effect is marked nontargeted

All ten extracted destruction effects currently contain:

```json
"targeted": false
```

That includes:

* Bilbo’s Deadly Slice
* Stir Up Trouble
* Warg Tactics
* Stone by Sunlight
* Pinecone Strike
* Thorin’s Last Stand

The cause is straightforward. `_DESTROY_RE` consumes the word `target` before passing the remaining phrase to `selector()`:

```python
(?:target\s+)?(.+)
```

But `selector()` determines targeting with:

```python
"targeted": "target" in low
```

The word is therefore already gone.

This distinction matters structurally: targeting interacts with hexproof, ward, protection, target-changing effects, and legality checks. These effects cannot be represented as merely affecting a creature.

The regex should capture target status explicitly and pass it into the selector. Add tests asserting:

* Bilbo, Stir, Warg, Stone, Pinecone, Thorin and Burn are targeted.
* The Black Arrow’s conditional `destroy it` is not independently targeted; it acts on the previously damaged object.
* Any future `destroy each/all` effect is nontargeted and mass-affecting.

## The “Phase 2 schema” is incomplete

The commit describes Phase 2 as delivering:

> selectors, participants, modes, durations, effects

But `effect_schema.py` currently implements only a partial object selector and eligibility resolver.

Still absent or incomplete:

* participant schema;
* owner and zone fields;
* explicit target/each/all/chosen quantifiers;
* duration schema;
* condition schema;
* stable cross-effect object bindings;
* mode schema beyond strings and integer indices;
* supertypes, despite being listed in the module documentation;
* effect records as validated schema objects;
* distinction between attempted destruction and successful zone movement;
* binding of a pronoun effect to its antecedent variable.

This is most visible in The Black Arrow. Its `destroy it` selector successfully infers `Dragon`, but there is no binding showing that the destroyed Dragon is the same object that was dealt damage by the preceding effect. It is currently just a generic Dragon selector with `var: "x"`.

I would describe the current work as **Phase 2a: selector prototype plus destruction vertical slice**, not completion of the requested general schema.

## Pair deduplication can discard provenance

Projection deduplicates using:

```python
(src, tgt, "CAN_DESTROY")
```

and simply skips subsequent matches. If one source has two destroy clauses or modes that can affect the same target, the second path, mode and provenance disappear.

The pair should remain unique if that is the pair-index convention, but its supporting mechanisms should be aggregated:

```json
{
  "relation": "CAN_DESTROY",
  "supports": [
    {"effect_id": "...", "mode_index": 0, ...},
    {"effect_id": "...", "mode_index": 1, ...}
  ]
}
```

The union view may collapse relations; the authoritative effect projection must not discard alternate mechanisms.

## Type conjunction is not enforced

The selector records `or_types`, but `matches_card()` always accepts any listed type:

```python
if not any(ct in t["types"] for ct in sel["card_types"]):
```

That is correct for “artifact or enchantment,” but wrong for a selector such as “artifact creature,” which requires both types.

Use:

* `any(...)` when `or_types` is true;
* `all(...)` when multiple types form a conjunction.

The same correction is needed for token matching.

## What Phase 2 gets right

The card-specific destruction results are otherwise strong:

* Bilbo and Stir project to creatures.
* Warg Tactics is restricted to the flying-creature class.
* Stone by Sunlight retains the power threshold.
* Pinecone Strike points to artifact-token specifications and not nontoken artifact cards.
* Thorin’s mode remains modal.
* Giant’s Boulder reaches permanent types.
* Reminder-text destruction on Stone does not generate a false effect.
* Azog retains a card-level self-pair while its selector records `other`, correctly allowing another copy while excluding the source object.
* The new layer is composed separately into `pair_index`.
* The frozen core remains untouched.

## Recommended response to the agent

> Treat the existing work as Phase 2a and correct it before extending additional effect families:
>
> 1. Fix target detection; all explicit `target` destruction effects must have `targeted: true`.
> 2. Add targeted/nontargeted/mass-effect negative tests.
> 3. Complete the general schema promised by Phase 2: participants, zones, ownership, quantifier, modes, conditions, duration, stable object/participant variables, and validated effect records.
> 4. Populate supertypes or remove the unsupported claim from the schema documentation.
> 5. Bind pronouns to an antecedent effect variable; The Black Arrow must destroy the same Dragon damaged this way.
> 6. Aggregate multiple supporting effects/modes instead of discarding later provenance during pair deduplication.
> 7. Enforce OR versus AND type matching in both card and token eligibility.
> 8. Add tests for schema validation, cross-effect binding, multimode provenance aggregation, and type conjunction.
> 9. Correct the stale Phase 1.2 report sentence about all dispositions being `pending_structuring`.
>
> Preserve the existing destruction projections and frozen artifacts.

So: the extraction results are promising, but the targeting bug alone is enough to require a Phase 2 correction before building the other effect families on this schema.
