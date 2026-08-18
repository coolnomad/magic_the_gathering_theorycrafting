The revised Phase 3a is substantially better, but I still would not accept Phase 3. Ability scoping and the named duration fixes landed; the generated records expose a second layer of selector and projection errors.

## What was fixed correctly

* Targets no longer leak between separate abilities.
* Dwarven Mattock and Crude Bent Blade no longer emit false targeted buffs.
* Sting’s hone counters correctly bind to Sting itself.
* Master’s Councillors’ static pump correctly binds to itself.
* Warg Tactics separates permanent counter duration from temporary ability duration.
* Pinecone Strike separates immediate damage from the turn-long replacement.
* Moment of Glory now has distinct targeted and conditional mass-counter effects.
* Gnashing of Teeth now distinguishes its target-player mode.
* Mirkwood retains Bear, Spider and Wolf.
* The Black Arrow’s damage effect is present.
* Real census clause IDs replace `#a?`.
* The remaining Phase 3 families have at least prototype representations.
* Frozen artifacts remain unchanged.

## Blocking problem 1: ordinary syntax words are becoming subtypes

The subtype extractor still treats capitalized words as creature/card subtypes. Generated selectors contain bogus subtypes including:

* `target`
* `creatures`
* `each`
* `other`
* `until`
* `whenever`
* `landfall`
* `saga`

Because `matches_card()` requires the subtype constraint, these bogus values can eliminate all valid projections.

Examples:

* Reverent Howl: creature plus subtype `target`
* Smaug’s Fury: creature plus subtype `target`
* Concerted Care: artifact/creature plus subtype `target`
* Stone by Sunlight: creature plus subtype `until`
* Great Ugly-Looking Goblin: creature plus subtype `each`
* The Arkenstone: creature plus subtype `creatures`

This means several headline effects are structurally present but do not project to their eligible cards.

The subtype parser needs a controlled vocabulary or grammar. At minimum:

* remove targeting, quantifier, trigger and duration syntax before subtype extraction;
* normalize plurals;
* validate candidates against known MTG subtypes;
* distinguish card types and supertypes from subtypes.

Add a global test that every emitted selector subtype belongs to the accepted subtype vocabulary.

## Blocking problem 2: Mirkwood Meditator is still bound to the wrong object

Its text says:

> you may have this creature’s base power and toughness become 4/2 until end of turn.

The emitted record targets a land:

```json
"object_var": "obj0",
"card_types": ["land"],
"subtypes": ["landfall", "whenever"]
```

The parser selects the land from the Landfall trigger instead of `this creature`.

This happens because the “first subject-producing verb” is `have`, and the prefix contains “a land you control.” The grammatical subject of the P/T operation must be determined locally around “base power and toughness become,” not from the first prior object phrase.

Expected:

```json
"object_var": "self",
"selector": {"self": true},
"duration": "until_end_of_turn",
"value": "4/2"
```

The current test checks only the value and misses the wrong affected object.

## Blocking problem 3: Old Fat Spider’s prevention effect is malformed

Correct text:

> Prevent all damage that would be dealt by up to one target creature for as long as this Saga remains on the battlefield.

The emitted selector includes subtype `saga`, because the parser absorbs the duration phrase into the object selector. It also records no duration.

Expected:

* target creature selector;
* no Saga subtype;
* quantity `up_to_1`;
* duration tied to the source Saga remaining on the battlefield.

The existing test checks only the relation name.

## Blocking problem 4: Burglar’s Plot loses essential constraints

Correct text:

> Exchange control of two target nonland permanents that share a card type.

The representation currently reduces this to one generic target permanent. It loses:

* quantity two;
* nontoken/nonland predicate;
* two distinct object variables;
* the shared-card-type constraint;
* the exchange relationship between those two objects.

It consequently projects to lands even though they are explicitly ineligible.

This needs a two-object operation, not a single selector with `EXCHANGES_CONTROL_OF`.

## Blocking problem 5: self-effects do not project to self-pairs

Self records now exist, but `_self_selector()` has no type/subtype constraint, and `matches_card()` does not treat `self: true` specially. Consequently effects such as these do not generate source→source projections:

* Sting adding counters to itself;
* Master’s Councillors modifying itself;
* Mirkwood Pathmaker setting its own P/T;
* Nori granting itself first strike;
* other reflexive P/T and ability effects.

This is exactly the reflexive-self relationship previously encountered in the human audit.

In projection:

```python
if selector["self"]:
    project only source_card -> source_card
```

Do not fan a self selector to other cards.

## Mass effects need proper quantifiers

Several plural subjects are represented as ordinary single-object selectors:

* “Creatures you control get…”
* “Other Bears you control get…”
* “Artifacts and creatures you control have…”
* “Elves you control…”

These should be nontargeted mass selectors:

```json
"targeted": false,
"affects_each": true,
"quantifier": "all"
```

Also, “artifacts and creatures you control” means every object in either class—not only objects that are simultaneously artifacts and creatures. The current AND type logic is wrong for that construction.

## The Black Arrow has inconsistent variable IDs

Its damage record has:

```json
"object_var": "obj0"
```

but:

```json
"selector": {"var": "tmp"}
```

The selector and effect must share the same variable. `validate_effect()` should assert that `object_var == selector.var` unless an explicit binding says otherwise.

## Reconciliation is too permissive

A clause is marked `extracted` if any effect was extracted from it. That does not show that every detected family within the clause was handled.

Reconciliation should operate on:

```text
(clause_id, family)
```

not only `clause_id`.

Also, these dispositions:

* divided damage — deferred;
* granted nonkeyword ability — deferred;
* remove counter — deferred;

should be counted as `unresolved_nonexecutable` or `deferred`, not hidden inside a headline of “0 unresolved.” They are acceptable explicit deferrals, but the report should state them honestly.

## Required correction

> Treat this as Phase 3b:
>
> 1. Replace capitalization-based subtype inference with grammar/vocabulary-validated subtype extraction.
> 2. Add a global selector-vocabulary test.
> 3. Correct Mirkwood Meditator to a self-bound P/T-setting effect.
> 4. Correct Old Fat Spider’s selector and source-presence duration.
> 5. Model Burglar’s Plot with two distinct nonland-permanent variables and a shared-type constraint.
> 6. Project explicit self selectors only to source→source.
> 7. Represent plural class subjects as nontargeted mass selectors.
> 8. Treat “artifacts and creatures” as class-level OR.
> 9. Require `object_var == selector.var` or an explicit binding.
> 10. Reconcile each `(clause_id, family)` and report deferred/nonexecutable items separately.
> 11. Add projection-level assertions for Reverent Howl, Concerted Care, Stone by Sunlight, the Arkenstone, Great Ugly-Looking Goblin, Mirkwood Meditator, Old Fat Spider, Burglar’s Plot, and at least one self-effect.

The refactor solved the first-order cross-ability problem, but Phase 3 is not yet semantically reliable at the pair-projection level.
