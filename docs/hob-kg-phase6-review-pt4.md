The new commit `db8b389` adds the missing engineering streams, but it is not ready for “full-spec completion.” All 180 tests pass, yet the second-draw implementation has two substantive defects. Equip remains entirely unaddressed.

## Commit review

Successfully added:

* Query CLI for cards, pairs, and mechanism modules.
* Recruit/draw-source → second-draw payoff projections.
* Dwarf/Equipment eligibility for Dáin’s Company and Kíli.
* Noncreature spells → Bothersome Noisemaker and related triggers.
* A fourth projection layer integrated into the 37,249-pair index.
* Unified mechanism-layer coverage and provenance.
* No reverse Councillors → Recruit relationship.

Blocking defects:

1. `cond:draw-is-second-this-turn` does not exist in `conditions.jsonl`.

   It is referenced by the mechanism edge and 39 projected relationships, but it has no condition record. This violates the explicit spec requirement that every condition ID resolve.

2. The second-draw gate uses `count >= 2`.

   That describes a persistent state after the second draw. It could produce the “second card drawn” event on the third, fourth, and subsequent draws. The event must occur on the transition:

   ```text
   previous count = 1
   + current draw
   → new count = 2
   → emit second-draw event once
   ```

   Model it as an equality/transition gate, not a persistent `>= 2` gate. The count should reset at the beginning of each controller’s turn.

3. Human semantic validation remains outstanding, as the commit itself acknowledges.

4. Equip handling has not changed. `mechanism_edges.jsonl` contains only second-draw, finder, and noncreature-cast repairs.

## Instructions for Equipment → creature handling

Give the agent the following implementation brief.

### Objective

Represent the objective, directed capacity:

> Equipment E can legally be attached to creature C, and while E is attached to C, E’s “equipped creature” effects apply to C.

Do not call this synergy. Distinguish:

* the capacity to activate Equip;
* the attachment action;
* the resulting attachment state;
* effects conditional on that state;
* special automatic attachment effects;
* Equipment entering the battlefield, which is a separate mechanism.

### 1. Amend the specification first

Add an authoritative reusable Equip template and these invariants:

* Equip targets a creature controlled by the activating player.
* Equip is normally activated only at sorcery timing.
* The printed Equip cost is preserved.
* Resolution attaches that Equipment to the selected creature.
* “Equipped creature” resolves to the creature bound in that attachment.
* An Equipment can have alternative Equip costs or attachment operations.
* Automatic attachment effects are not Equip activations.
* Equipment entering and Equipment becoming attached are different events.
* Equipment→creature relations are directed and conditional.
* Every emitted condition ID must resolve.

### 2. Introduce explicit attachment semantics

Prefer a deliberate schema extension rather than overloading the current ambiguous `ATTACHED_TO` edge.

Suggested primitives:

```text
CAN_ATTACH_TO
ATTACHES_TO
HAS_ATTACHMENT_STATE
```

Or use an explicit operation/state construction:

```text
face:E
  HAS_ABILITY → ability:equip:E
  HAS_COST → cost:equip:E
  REFERENCES_RULE → rule:equip

ability:equip:E
  CAUSES → op:equip:E

op:equip:E
  REQUIRES → obj:creature-controlled-by-activator
  CAUSES → state:attachment:E-C

state:attachment:E-C
  data:
    equipment: E
    attached_object: C
    controller_constraint: target creature you control
```

The target `C` is a bound variable, not one global “equipped creature” object shared by every Equipment.

### 3. Represent continuous effects through the bound attachment

For an Equipment giving `+1/+2`:

```text
ability:equipped-bonus:E
  CAUSES → op:modify-equipped-creature:E

op:modify-equipped-creature:E
  REQUIRES → state:attachment:E-C
  MODIFIES → obj:bound-creature-C
  modification:
    power: +1
    toughness: +2
```

For granted abilities or keywords:

```text
op:grant:E
  REQUIRES → state:attachment:E-C
  MODIFIES → ability/keyword of obj:bound-creature-C
```

This is essential: the attachment operation and the bonus must resolve to the same bound creature.

### 4. Normalize every Equip ability

For each of the 12 HOB Equipment cards:

* Find every printed Equip ability.
* Parse its mana and nonmana costs.
* Preserve timing.
* Preserve target restrictions.
* Instantiate `rule:equip`.
* Preserve alternative Equip modes as alternative paths.
* Connect every “equipped creature” effect to the attachment state.
* Record exact Oracle spans and rule provenance.

Do not infer attachment solely from Scryfall’s `Equip` keyword catalogue.

### 5. Keep special attachment mechanisms separate

Examples include:

* Equipment entering already attached;
* creating a token and attaching the Equipment to it;
* attaching any number of Equipment through another permanent’s ETB;
* Hone effects that attach after placing a counter.

These should use their printed operation rather than the Equip activation path:

```text
printed ability → attachment operation → attachment state
```

They may have different timing, costs, targets, and conditions.

### 6. Derive Equipment→creature pair relations

For every Equipment card `E` and creature card `C`, evaluate target-class compatibility.

Emit one or more directed relations:

```text
E → C : CAN_ATTACH_TO
E → C : MODIFIES_WHEN_ATTACHED
E → C : GRANTS_ABILITY_WHEN_ATTACHED
```

Each relation must contain:

* Equip cost;
* sorcery-timing restriction;
* controller restriction;
* target restrictions;
* attachment-state condition;
* exact modification or granted ability;
* complete primitive path;
* provenance;
* source layer.

Do not emit `C → E` unless the creature itself modifies, finds, discounts, or attaches Equipment.

The pair index remains exactly 37,249 records; these become additional relations within existing records.

### 7. Avoid combinatorial primitive expansion

Keep the primitive graph parameterized around `E`, `C`, and `Attached(E,C)`. Resolve it against the finite creature-card population during pair projection.

With 12 Equipment and 112 creature cards, at most 1,344 Equipment→creature pair evaluations are needed. This is trivial at projection time and does not require 1,344 primitive attachment-state nodes.

### 8. Add conditions

At minimum:

```text
cond:equip-target-controlled-by-activator
cond:equip-sorcery-timing
cond:equipment-E-attached-to-creature-C
```

Card-specific restrictions receive stable additional conditions. Every condition must be written to `conditions.jsonl` or an explicitly unioned additive condition layer.

### 9. Regression tests

Require tests demonstrating:

* All 12 Equipment cards instantiate or reference the Equip template correctly.
* Every Equip cost is preserved.
* Every emitted attachment target is a creature.
* Controller and timing restrictions are present.
* Every “equipped creature” effect is attachment-conditioned.
* Equipment and affected creature use the same binding `C`.
* Dwarven Shortsword’s automatic attachment is distinct from its Equip ability.
* Wizard’s Staff preserves its alternative attachment/equip restrictions.
* Equipment ETB triggers are not confused with attachment events.
* A representative Equipment→creature query shows cost, conditions, attachment state, modification, and provenance.
* No unsupported reverse creature→Equipment relation is emitted.
* All new condition IDs resolve.
* Rebuilding is deterministic.
* All primitive paths and endpoint signatures validate.

The immediate order should be: repair the second-draw condition and transition semantics, then implement this Equip template and projection layer, then perform the human review.
