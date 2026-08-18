Phase 3b fixes the previous selector/projection failures, but I found several remaining semantic omissions. I would not freeze Phase 3 yet.

## Correctly fixed

* Bogus syntax subtypes no longer poison the headline projections.
* Reverent Howl, Concerted Care, Stone by Sunlight and the Arkenstone now project correctly.
* Mirkwood Meditator is correctly self-bound.
* Self-effects project only source→source.
* Old Fat Spider’s prevention selector and duration are correct.
* Burglar’s Plot now records:

  * two variables;
  * nonland permanents;
  * quantity two;
  * shared-card-type constraint.
* Mass selectors and artifact-or-creature class unions are corrected.
* The Black Arrow’s variable IDs agree.
* Reconciliation now operates per `(clause_id, family)` and reports four deferrals separately.

## Blocking issue 1: effect conditions and qualifiers are still missing

Several emitted effects are represented as unconditional despite explicit restrictions.

Examples:

* Great Ugly-Looking Goblin grants menace only to creatures with a +1/+1 counter. Its selector has no counter predicate.
* Most Decrepit Old Bird’s +1/+1 requires threshold.
* Ori and Óin require an enduring story.
* Thorin Oakenshield and Fíli require an enduring story.
* Dáin’s Company requires control of another Dwarf.
* Bolg’s Company requires control of another Goblin.

These records currently have `condition: null`.

The broad pair projection can still include every creature that could potentially satisfy the condition, but the structured selector/effect must retain the condition. For example:

```json
{
  "predicates": {
    "has_counter": "+1/+1"
  }
}
```

or:

```json
{
  "condition": {
    "kind": "gate",
    "gate": "enduring_story"
  }
}
```

Add a systematic test: clauses containing `as long as`, threshold, or `with a ... counter` cannot emit unconditional effects unless explicitly justified.

## Blocking issue 2: Gnashing of Teeth still loses its replacement effect

Its first mode says:

> Target creature gets -5/-5 until end of turn. If that creature would die this turn, exile it instead.

The emitted `MODIFY_PT` record has:

```json
"replacement": null
```

The replacement must bind to the same target variable and last this turn, just as Pinecone Strike’s replacement does:

```json
{
  "kind": "die_would_exile_instead",
  "object_var": "obj0",
  "duration": "this_turn"
}
```

This was one of the mandatory regression cases.

## Blocking issue 3: Old Fat Spider’s hexproof duration is missing

The prevention mode is fixed, but its first chapter says:

> gains hexproof for as long as this Saga remains on the battlefield.

That `GRANT_ABILITY` record still has `duration: null`.

Both chapters require the source-presence duration.

## Blocking issue 4: Thorin, Mountain-king has the wrong damage source

The emitted damage target is reasonable, but its source selector is:

```json
{
  "card_types": ["creature"],
  "subtypes": ["equipment"]
}
```

That is impossible. The source of the damage is the creature to which the Equipment became attached—not an Equipment creature.

The record must bind:

1. the initially chosen creature;
2. the later phrase `that creature`;
3. the damage source variable;

to the same object. The target of the damage remains a distinct variable.

This is another cross-sentence antecedent-binding case within one ability.

## Architectural issue: observed-set subtype vocabulary is too narrow

Validating against actual HOB objects removes syntax noise, but it also deletes valid Oracle selectors when the subtype currently has no instantiated card/token.

The test acknowledges this:

> `Orc` is removed because no HOB permanent has the subtype Orc.

That makes the selector for “target Goblin or Orc” semantically incomplete. Object-class semantics should preserve both Goblin and Orc even if the projection currently finds zero Orc cards.

Use the canonical Magic subtype vocabulary, or retain Oracle-recognized but currently uninstantiated subtypes separately. The graph should distinguish:

* selector contains Orc;
* current HOB projection contains zero Orc objects.

## Reconciliation limitation

The new family-level reconciliation is a real improvement, but “extracted” currently means an operation of that family exists—not that all its conditions, bindings, durations and predicates were preserved. That is why the cases above pass reconciliation.

Add semantic regression checks for required qualifiers rather than relying on reconciliation alone.

## Required Phase 3c correction

* Preserve `as long as`, threshold, enduring-story, controls-another, and has-counter conditions.
* Add the +1/+1-counter predicate to Great Ugly-Looking Goblin.
* Add Gnashing’s bound death-to-exile replacement.
* Add the source-presence duration to Old Fat Spider’s hexproof grant.
* Correct Thorin Mountain-king’s cross-sentence source binding.
* Preserve valid but uninstantiated Oracle subtypes such as Orc.
* Add regression tests that inspect these complete effect records and their projections.

The earlier projection defects are genuinely fixed. This is now a narrower semantic-completeness correction rather than another architectural rebuild.
