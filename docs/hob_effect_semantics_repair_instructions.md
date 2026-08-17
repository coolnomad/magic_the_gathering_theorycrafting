# HOB Effect-Semantics Repair: Agent Instructions

## Objective

Correct the remaining HOB graph omissions for spells and abilities that draw, discard, sacrifice, exile, move, damage, destroy, modify, or grant abilities.

Implement this as a systematic additive semantic layer over the frozen HOB analytical reference. Do not solve the examples by inserting isolated card-pair edges. The result must represent the underlying effect, its eligible objects or participants, its conditions and modes, and—where deterministic—project that effect to every eligible HOB card.

The frozen Phase 4/Phase 5 artifacts and all previously frozen layers must remain byte-identical.

## Read First

Before editing code:

1. Read `INSTRUCTIONS.md` and the current specifications, architecture notes, audit records, portability plan, and layer-composition code.
2. Inspect the latest `audit_repair` implementation and its tests.
3. Record the hashes of every frozen artifact that must not change.
4. Add a specification/ledger entry for this work before implementation, following repository discipline.
5. Treat `LABNOTEBOOK.md` and `CONVERSATION_LOG.md` as append-only.

## Architectural Requirements

### 1. Additive overlay

Create a new additive layer, such as `effect_semantics` or `effect_repair`. It may add structured facts, projections, and explicit suppressions/retypings at union time, but it must not rewrite frozen source artifacts.

When replacing an incorrect relation, retain its provenance and mark it `superseded` or inactive through the ordered overlay. Do not silently delete history.

### 2. General representation, not named-card patches

Run the extractor/materializer across all 210 HOB card faces, including abilities on permanents—not merely instants and sorceries.

Reusable engine code must not branch on card names or UUIDs. Set-local exceptions, if genuinely unavoidable, must be declarative, provenance-bearing, and documented. An audited pair is a regression test, not the scope of the implementation.

### 3. Structured selectors and bindings

Represent an affected object with a structured selector containing, where applicable:

- zone;
- card type, subtype, and supertype;
- controller, owner, or participant relationship;
- target, each/all, nontargeted, or chosen status;
- quantity: fixed, variable, all, or up to N;
- predicates such as tapped, attacking, flying, token/non-token, or power threshold;
- exclusions such as `another`, `other`, and `self`;
- a stable object-variable ID.

Represent participants explicitly: `you`, `target_player`, `target_opponent`, `each_player`, `each_opponent`, controller, or owner.

Use stable variable bindings so “it,” “that creature,” “those cards,” and “this way” resolve to the correct prior object or participant. Multiple consequences applied to one target must bind to the same variable.

Do not blanket-remove self-pairs. “Another” excludes the source permanent itself, not another physical copy with the same card name. Likewise, a spell such as Meager Meal may target a creature card with the same name as another copy of its source card where the rules permit it.

### 4. Effect vocabulary

Support or reuse canonical structured operations for at least:

- deal damage;
- destroy or attempt to destroy;
- exile;
- return/move between zones;
- tap and untap;
- add/remove counters;
- modify power/toughness;
- grant/remove keywords or abilities;
- change type or control;
- prevent damage;
- fight;
- draw, discard, mill, and search;
- create tokens;
- gain, lose, or pay life;
- counter a spell or ability;
- grant permission to play or cast.

Each operation must preserve its amount or formula, source, affected binding, optionality, condition, duration, and zone transition where applicable.

### 5. Modes and conditions

Preserve:

- `choose one` as mutually exclusive branches;
- `choose one or both` as independently selectable branches;
- kicker, gift, cast-from-graveyard, trigger, timing, and intervening conditions;
- `until end of turn`, delayed-return, and other durations;
- shared bindings among effects within the same mode.

Do not flatten modal effects into an unconditional bundle.

## Projection Rules

Project structured selectors deterministically to all eligible card faces or token specifications. A larger pair index is acceptable when it is the faithful consequence of a generic relation.

Use precise relations such as:

- `CAN_DEAL_DAMAGE_TO`;
- `CAN_DESTROY`;
- `CAN_EXILE`;
- `CAN_RETURN` / `CAN_BOUNCE` / `CAN_BLINK`;
- `ADDS_COUNTER_TO`;
- `MODIFIES_POWER_TOUGHNESS`;
- `GRANTS_ABILITY_TO`;
- `CAN_TAP` / `CAN_UNTAP`;
- `CAN_REANIMATE` / `CAN_RECUR`.

Use existing canonical predicate names where equivalents already exist; do not create synonyms casually. If the schema cannot express a necessary distinction, stop and document the proposed schema extension before inventing a predicate.

Additional rules:

- Mass effects must remain distinguishable from targeted effects, for example with `AFFECTS_EACH` or equivalent metadata.
- Player effects remain participant-level facts. Derive card-to-card relations only when a real downstream trigger, permission, selection, or resource dependency justifies one.
- Ordinary draws, mills, and top-library exile are stochastic and must not fan out deterministically to every card in the set.
- Tutors/searches may fan out to every eligible card because their selector determines the possible choices.
- Artifact-token destruction should point directly to eligible token specifications. A secondary relation to cards that can create those objects may be useful, but it must not claim that the removal spell destroys the creator.
- Keep generic object-class facts available even when pair projection is also generated.

## Required Effect-Family Audit

Generate a deterministic census from current Oracle text. The following prior heuristic counts are starting points, not acceptance values: draw 53 faces, discard 25, sacrifice 34, exile 33, mill 6, return 13, tutor/search 10, token creation 46, life 22, counterspell 3, and play/cast permission 23. Reminder text and false positives mean the final adjudicated totals may differ.

Every candidate clause must receive one disposition:

1. structured and projected where appropriate;
2. structured but intentionally not pair-projected, with a reason;
3. deliberately ignored, with a reason;
4. unresolved/nonexecutable, with a reason and provenance.

Audit these families:

### Draw and life

Model a draw as an operation affecting participant P, moving N cards from P's library to P's hand, producing the appropriate draw event and counter consequence where supported. Preserve amount, optionality, and condition. Do not map the draw to every possible library card.

Bind combined instructions correctly. In Reverent Howl, the same target player both draws two cards and loses 2 life.

### Discard

Distinguish:

- a cost from an effect;
- mandatory from optional discard;
- the participant performing it;
- fixed/variable quantities and card selectors;
- hand-to-graveyard movement and the discard event.

Where supported, distinguish relations such as eligible discard choice, satisfaction of a discard cost, and enabling a discard trigger. Review all existing `SUPPLIES_RESOURCE` relations so that cost consumption, event triggering, and merely coincident resource production are not conflated. Do not limit this review to the already corrected Kíli and Uncover/Plunder cases.

### Sacrifice

Classify every sacrifice clause rather than treating every occurrence as a sacrifice outlet:

- selectable-fodder cost;
- optional or mandatory sacrifice effect;
- self-sacrifice cost;
- edict imposed on another participant;
- delayed cleanup;
- Saga cleanup;
- Treasure reminder text;
- conditional consequence.

Reuse or integrate the portable sacrifice-clause extractor if it is already available. Preserve eligibility, participant, cost/effect status, resulting zone/event, and artifact-versus-creature consequences.

### Exile and permissions

Distinguish:

- targeted and mass removal;
- blink/exile-and-return;
- Adventure/flashback-style self-exile;
- death replacement;
- countered-spell exile;
- exile-and-play permission;
- stochastic top-library exile.

Preserve object identity, source and destination zones, duration, controlling participant, and any play/cast permission.

`Settle the Wreckage` must bind a target player P, select all attacking creatures controlled by P, exile those creatures, then allow P to search for up to N basic lands where N is the number exiled this way and put them onto the battlefield tapped. Do not reduce it to an unqualified creature-exile relation.

### Movement, search, mill, and recursion

For bounce, blink, reanimation, recursion, and other movement, identify the moved object plus source and destination zones. Preserve whether it returns immediately or later and whether it is the same object.

Tutors should project to eligible choices; mill and random/top-library movement should remain stochastic object-class operations.

### Other families

Include prevention, control exchange, type changes, additional-land permissions, cost modification, scry/look/reveal, copying/additional triggers, attack/block/cast restrictions, variable token creation, delayed token creation, and counterspells including “unless its controller pays” alternatives. Record unsupported execution semantics explicitly rather than omitting the clause.

## Mandatory Regression Cases

Add tests proving the following semantics. Tests should query both the structured layer and the composed graph/pair index where projection is appropriate.

### Warg Tactics

- Mode 1: attempts to destroy a target creature with flying.
- Mode 2: puts a +1/+1 counter on a target creature you control and grants that same creature trample and hexproof until end of turn.
- The modes are mutually exclusive.

### Reverent Howl

- Mode 1: one target player draws two cards and loses 2 life; both effects bind to the same participant.
- Mode 2: one target creature gets +2/+2 and lifelink until end of turn; both effects bind to the same creature.
- The modes are mutually exclusive.

### Pinecone Strike

- It has `choose one or both`, not mutually exclusive modes.
- One mode deals 3 damage to a target creature and attaches the “if it would die this turn, exile it instead” replacement to that same creature.
- The other mode destroys a target artifact token, not every artifact.

### Removal and damage

- Bilbo's Deadly Slice and Stir have the correct target-creature destruction relation.
- Magnificent End deals 5 damage to a target creature and retains the cost-reduction condition involving a tapped target.
- Stone by Sunlight distinguishes destroying a creature with power 4 or greater from its type-change/indestructible mode.
- Quarrel in the Shire distinguishes the source creature you control from the target creature an opponent controls and derives damage from the source's power.
- Troll Negotiations puts counters on one controlled creature, then makes it fight a distinct eligible opponent-controlled creature.

### Buffs and granted abilities

- Meager Meal may put a +1/+1 counter on up to one target creature with no controller restriction, and a target player may gain 2 life; the two targets need not be the same entity.
- Concerted Care grants hexproof and indestructible until end of turn to a target artifact or creature you control.
- Moment of Glory distinguishes its targeted counter from the cast-from-graveyard effect on each other creature you control.
- Thorin's Last Stand distinguishes its mass +2/+1 mode from its targeted artifact/enchantment destruction plus life-gain mode.
- Gnashing in the Dark preserves its modes, its same-object -5/-5/death-exile replacement, and its target-player-controlled-creatures -1/-1 effect.

### Tapping, returning, and exile

- Gaze in Wonder can tap one or two target creatures.
- Eagles of the North preserves owned-creature return selection and the delayed/derived token quantity.
- Gone Fishing and Roll Over the Edge preserve same-object exile-and-return bindings.
- Settle the Wreckage is represented as specified above.

### Search, counters, and permissions

- Seek the Heart and other tutors expose their full typed selector and destination.
- Thranduil's Decree preserves countering, the permanent-spell exile replacement, and the resulting cast permission and duration.
- Snowslope Hunter and Great Goblin preserve top-card exile and play/cast permission semantics, even if full activation timing and executable payoff state remain explicitly deferred.

Also test relevant permanent sources such as Azog, Burn as a Saga, Stone-Giant, Thorin Mountain-king, Black Arrow, Giant Boulder, Bard, Bifur, and the five sacrifice lands. The scanner must not be spell-only.

## False-Positive Guards

Add explicit negative tests showing that:

- Warg Tactics cannot destroy a nonflying creature through its first mode;
- Pinecone Strike's artifact-token mode does not project to nontoken artifacts;
- Settle the Wreckage does not unconditionally exile nonattacking creatures;
- Concerted Care retains its controller restriction;
- Meager Meal is not incorrectly restricted to creatures you control;
- a stochastic draw, mill, or top-card exile does not create deterministic edges to all cards;
- `another` excludes only the source object, not every other copy with the same card identity;
- player life loss/draw does not create arbitrary spell-to-creature edges;
- modal alternatives do not become simultaneous unconditional effects.

## Provenance and Output Requirements

Every new structured fact and projected relation must carry:

- source card/face identity;
- Oracle-text span or equivalent traceable clause provenance;
- extraction/materialization rule;
- mode and condition references;
- layer origin;
- active/superseded status where relevant.

Update the pair index for all card pairs and expose the new layer distinctly. Preserve class-level relations alongside projections. Require zero provenance gaps and zero dangling condition references.

Produce a machine-readable and human-readable coverage report by effect family containing:

- heuristic candidate count;
- adjudicated clause count;
- structured count;
- pair-projected count;
- unresolved/nonexecutable count;
- ignored count and reasons.

Produce a separate `SUPPLIES_RESOURCE` review report with a disposition for every relevant edge.

Do not label agent-generated annotations as human gold data. Preserve the independent human audit as a distinct validation source.

## Acceptance Gates

The work is complete only when all of the following hold:

1. All candidate clauses have a recorded disposition.
2. No material target or participant restriction exists only in unstructured prose.
3. Pronoun and same-object bindings resolve deterministically.
4. Every zone-changing operation records its object, source zone, and destination zone where the rules determine them.
5. Modes, optionality, conditions, costs, triggers, effects, and durations remain distinct.
6. Deterministic selectors project to every eligible object; stochastic selectors do not.
7. There are no card-name/UUID branches in reusable engine code.
8. Frozen artifact hashes are unchanged.
9. All existing tests and the new regression/negative tests pass.
10. Two clean rebuilds are byte-identical.
11. The composed graph has zero provenance gaps and zero unresolved condition references.
12. The coverage and resource-review reports are checked in.
13. Documentation and append-only logs are updated.

Report before proceeding if satisfying an acceptance gate requires changing a frozen artifact or making an unapproved schema decision.

## Suggested Implementation Sequence

1. Specification entry, frozen-hash manifest, and deterministic census/report generator.
2. Selector, participant, variable-binding, mode, duration, and effect schemas.
3. Targeted object effects: damage, destruction, counters, P/T changes, ability grants, tapping, prevention, fight, and type/control changes.
4. Participant/resource effects: draw, discard, sacrifice, life, mill, search, and counterspells.
5. Zone movement, exile variants, delayed return, and play/cast permissions.
6. Deterministic projection and ordered overlay/suppression handling.
7. Regression tests, negative tests, coverage reports, full suite, deterministic rebuild, documentation, and append-only log entries.

Keep commits reviewable along those boundaries. Do not present a clean test run alone as evidence of semantic completeness; include the census dispositions and concrete query results for the mandatory regression cases.

## Non-Goals

- Do not rewrite the frozen HOB base.
- Do not minimize edge count at the expense of faithful generic relations.
- Do not patch only the named audit pairs.
- Do not add subjective synergy or card-quality judgments.
- Do not claim full action simulation, priority/timing enforcement, per-turn activation counters, or full per-card payoff execution unless those capabilities are actually implemented and tested.
- It is acceptable to preserve a semantic fact as structured but nonexecutable, provided that status and the missing execution capability are explicit.
