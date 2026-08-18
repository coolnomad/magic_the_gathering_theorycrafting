I would not accept Phase 3 yet. The named tests pass, but the generalized extractor produces several materially incorrect records.

The central problem is architectural: `_object_effects()` parses an entire card face as one clause unless it is modal. Targets from one ability can therefore be attached to effects in another ability.

## 1. Targets leak across separate abilities

The generated records contain clear false bindings.

### Dwarven Mattock

Oracle text:

> When this Equipment enters, attach it to target Dwarf you control.
> Equipped creature gets +2/+2 and has ward {1}.

The graph emits a targeted `MODIFY_PT` effect on a Dwarf. That is wrong. The +2/+2 applies to the equipped creature through the attachment relationship, not to the earlier target Dwarf indefinitely.

The extractor finds the earlier `target Dwarf`, then binds the later “gets +2/+2” to it because both abilities are processed together.

Crude Bent Blade has the same class of problem: its Equipment modification is being reinterpreted as a normal targeted modification.

### Master’s Councillors

Oracle text:

> This creature gets +2/+0 for each graveyard with seven or more cards in it.
> Whenever you draw your second card each turn, target player mills three cards.

The self-modification is incorrectly bound to the later target player. It produces an object effect with an empty object selector.

### Sting, Bilbo’s Sword

Oracle text:

> Put a hone counter on Sting for each creature target opponent controls.

The emitted record says the counter is placed on `obj0`, representing the target opponent. The counter actually goes on Sting itself; the target opponent is only used to determine the number of counters.

This is a direct semantic error.

### Required correction

Phase 3 must consume actual clause/ability boundaries from the Phase 1 ledger. It should not use:

```python
_mФodes(entire_face_text)
```

as its parsing unit.

Every emitted effect should carry a real census `clause_id`, not:

```text
#a?
```

Targets must be scoped to their own ability or modal branch.

## 2. Durations are attached to the entire clause instead of individual effects

Warg Tactics currently gives its `ADD_COUNTER` record:

```json
"duration": "until_end_of_turn"
```

That is wrong. The +1/+1 counter is permanent; only trample and hexproof expire at end of turn.

The same problem affects other counter-plus-temporary-ability cards, including Bard the Bowman and Thranduil’s Company.

Pinecone Strike’s damage record receives:

```json
"duration": "this_turn"
```

The damage is immediate. The associated death-to-exile replacement lasts for the turn.

Duration must attach to the operation or nested replacement it actually modifies:

* Warg counter: `duration: null`
* Warg granted abilities: `until_end_of_turn`
* Pinecone damage: `duration: null`
* Pinecone replacement: `duration: this_turn`

Add explicit tests for these distinctions.

## 3. Participant targets are being emitted as object selectors

Examples:

* The Great Goblin deals 2 damage to target opponent.
* Master’s Councillors targets a player who mills cards.
* Sting references a target opponent to count creatures.

These generate selectors with no card type, subtype, supertype, or generic-permanent constraint. They then either project nowhere or bind the wrong operation to the player.

Object-directed effects should reject empty object selectors. Player effects should be emitted as participant-bound effects or deferred explicitly to Phase 4.

Strengthen `validate_effect()` so an object relation cannot validate with an empty object selector unless it has an explicit self/antecedent binding.

## 4. Multi-subtype selectors are truncated

Mirkwood says:

> target Bear, Spider, or Wolf you control

The emitted selector contains only:

```json
"subtypes": ["bear"],
"controller": "any"
```

It loses Spider, Wolf, and the controller restriction because `_TDELIM` stops at the first comma.

Selector parsing must understand comma-separated OR lists. Add tests for:

* Bear, Spider, or Wolf you control;
* Goblin or Orc you control;
* artifact or creature you control;
* one or two target creatures;
* up to one target creature.

## 5. Several required Phase 3 semantics remain missing

### Moment of Glory

Only its targeted counter is represented. This effect is missing:

> If this spell was cast from a graveyard, put a +1/+1 counter on each other creature you control.

That requires a nontargeted `each other creature you control` selector and the cast-from-graveyard condition.

### Gnashing of Teeth

Its target-player mode should affect every creature controlled by that player. Instead it emits a `MODIFY_PT` record with an empty object selector.

This requires:

* participant variable for the target player;
* object selector for each creature controlled by that participant;
* nontargeted/mass status.

### The Black Arrow damage

Its “1 damage to any target” effect is absent. “Any target” must preserve the creature/planeswalker/battle/player alternatives rather than disappearing because it lacks a normal card-type phrase.

### Missing Phase 3 families

The agreed Phase 3 scope also included:

* prevention;
* ability removal;
* base P/T setting or switching;
* control changes.

The census shows candidates for these families, but this commit does not implement or disposition them. Either complete them in Phase 3 or rename this as a partial Phase 3a and state what remains.

## Recommended corrective instructions

> Treat `2e266b4` as a Phase 3 prototype, not an accepted phase.
>
> 1. Refactor object extraction to operate on Phase 1 census clauses/abilities with real `clause_id` values.
> 2. Never share target pools across separate abilities.
> 3. Attach duration to individual operations or nested replacements, not the entire clause.
> 4. Represent self-effects explicitly; do not bind them to an unrelated target elsewhere in the text.
> 5. Separate participant targets from object targets.
> 6. Reject object effects with empty object selectors unless an explicit self or antecedent binding supplies the object.
> 7. Parse comma-separated subtype lists and retain controller restrictions.
> 8. Correct Dwarven Mattock, Crude Bent Blade, Master’s Councillors, Sting, Mirkwood, Warg Tactics, Pinecone Strike, Gnashing of Teeth, Moment of Glory, and The Black Arrow.
> 9. Complete or explicitly defer prevention, ability removal, P/T setting/switching, and control changes.
> 10. Reconcile every Phase 3 census clause with an extracted effect or documented disposition.
>
> Preserve the correct records already demonstrated for Reverent Howl, Magnificent End, Stone by Sunlight, Troll Negotiations, Quarrel, Concerted Care, and Gaze in Wonder.

The existing tests are too centered on successful examples. The generated data shows that the generalized behavior is not yet safe.
