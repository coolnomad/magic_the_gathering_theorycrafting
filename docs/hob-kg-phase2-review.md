The bundle is broadly on target for the end of Phase 2, and Gandalf is represented at the expected level. But I found one important architectural defect repeated across several templates: **concept/type nodes are sometimes being used as if they were particular game-object states or event instances**. That must be fixed before pair projection.

## What is correct

The bundle passes the basic structural checks:

* 193 cards
* 210 faces
* 17 Adventure faces and 17 instantiated Adventure templates
* 8 Sagas
* 10 Recruit operations
* All JSONL files parse
* No duplicate node or edge IDs
* No dangling edge endpoints
* Gandalf has two faces, an Adventure pathway, and a Storied contribution
* Gandalf’s custom Oracle semantics are absent, correctly reserved for Phase 3

For Gandalf, [nodes.jsonl](sandbox:/workspace/scratch/e3646a5cdd6d/upload/nodes.jsonl) and [edges.jsonl](sandbox:/workspace/scratch/e3646a5cdd6d/upload/edges.jsonl) contain:

```text
Flameshape
    HAS_ABILITY → cast Adventure
    cast → resolve
    resolve → exile

Gandalf face
    can be cast from hand
    can be cast from Adventure exile
    CONTRIBUTES_TO → Storied
```

That is the correct intended scope for Phase 2.

## Critical problem: lost object identity

Consider this Adventure edge:

```text
zone:exile
    ENABLES
cast Gandalf from exile
```

This literally says that the existence of the exile zone enables Gandalf’s cast operation. It does not say that **this particular physical Gandalf/Flameshape object was exiled after its Adventure resolved**.

The desired structure is:

```text
Flameshape resolution
    → source card enters Adventure-exiled state

Adventure-exiled state of this source object
    → enables casting this object's Gandalf face
```

For example:

```text
state:card-f48f2a9b:adventure-exiled
```

rather than the global node:

```text
zone:exile
```

Otherwise, constrained path traversal could conclude that any route into exile enables Gandalf to be cast from exile.

### Adventure also assumes resolution

The current edge is:

```text
cast Adventure → CAUSES → Adventure resolves
```

Casting does not guarantee resolution; the spell can be countered. More precisely:

```text
cast Adventure
    → puts spell on stack

spell resolves
    → Adventure replacement moves source object to exile
```

The source object goes to Adventure exile only if the Adventure spell resolves and would otherwise go to its owner’s graveyard as it resolves.

A suitable simplified model would be:

```text
cast Adventure
    → CAN_LEAD_TO → resolution

resolution
    → source object enters Adventure-exiled state

Adventure-exiled(source object)
    → enables permanent-face casting
```

## The same identity problem appears in Recruit

All ten Recruit-discard operations point to one shared gate:

```text
gate:recruit-nonland-discard
```

That gate then has ten parallel `CREATES_OBJECT` edges to the Human Soldier token—one contributed by each Recruit card.

As a multigraph, this can be interpreted as:

```text
one successful nonland-discard gate
    → creates ten Human Soldiers
```

The ten edges differ only in provenance. They do not represent ten distinct outcomes.

There are two valid designs.

### Per-invocation gates

```text
Patient Instructor Recruit discard
    → Patient Instructor nonland gate
    → create one Soldier

Lake-town Lookout Recruit discard
    → Lake-town Lookout nonland gate
    → create one Soldier
```

All gates can reference the same generic condition definition:

```text
cond:recruit-nonland-discard
```

### Generic rule template plus instances

```text
rule:recruit
    → generic nonland branch
    → generic create-one-Soldier effect

Patient Instructor recruit
    → INSTANTIATES rule:recruit
```

This is probably cleaner. The generic rule has one output edge. Each card-specific Recruit operation invokes the template without duplicating the generic effect.

## The same issue appears in Sagas

The graph currently uses one global counter-type node:

```text
counter:lore
```

All Sagas add counters to that node, and that node enables all chapter abilities:

```text
Mountain-king's Return adds → counter:lore
counter:lore enables → every Saga chapter
```

That loses which Saga has which counters. Mechanically, this could imply that adding a lore counter to one Saga enables the chapter of another Saga.

You need to distinguish the counter **type** from an object’s counter-count **state**:

```text
counter-type:lore

state:Mountain-kings-Return:lore-count
state:Misty-Mountains-Cold:lore-count
```

Then:

```text
Mountain-king's Return lore operation
    → modifies its own lore-count state

Mountain-king's Return lore-count = 2
    → triggers its own chapter II
```

The generic `counter:lore` node remains useful as an ontology node:

```text
Mountain-king's Return lore-count
    HAS_COUNTER_TYPE → lore
```

But it should not directly connect all additions to all chapters.

## Hone has the same smaller defect

The graph currently duplicates:

```text
counter:hone → PRODUCES → hone boost
```

once for each card that places hone counters. Those are two copies of the same rule, not two separate effects per counter.

More importantly, a hone counter must be attached to a particular Equipment:

```text
Equipment object E
    has n hone counters

E attached to creature C
    → C gets +n/+0
```

The graph needs:

* Generic hone-counter type
* Counter count attached to an Equipment object
* Attached-creature relation
* Power modification scaling with that Equipment’s counter count

The generic rule-level edges should occur once.

## Storied is close, but rename the card-level relation

The Storied gate itself in [gates.jsonl](sandbox:/workspace/scratch/e3646a5cdd6d/upload/gates.jsonl) is good:

* Battlefield
* Controlled by you
* Legendary OR artifact OR Saga
* Count distinct objects
* Threshold ≥3
* No double-counting
* Persistent output

But this edge:

```text
Gandalf face CONTRIBUTES_TO Storied
```

can sound like Gandalf contributes merely because the card exists in the deck.

At the card-definition level, the more precise predicate is:

```text
Gandalf face QUALIFIES_FOR Storied
```

At runtime:

```text
battlefield instance of Gandalf
    CONTRIBUTES_TO Storied count
```

Likewise:

```text
Treasure token specification QUALIFIES_FOR Storied
```

while:

```text
particular Treasure token on battlefield
    CONTRIBUTES_TO Storied count
```

This separates mechanistic capacity from realized state—the same separation we will eventually need between deck composition and replay execution.

## Tokens need more properties

[tokens.jsonl](sandbox:/workspace/scratch/e3646a5cdd6d/upload/tokens.jsonl) correctly identifies twelve token identities and type lines. But most token specifications lack:

* Color
* Power/toughness
* Keywords
* Rules text
* Mana abilities
* Named-token abilities

For example, the Human Soldier should include:

```json
{
  "colors": ["W"],
  "power": 1,
  "toughness": 1,
  "types": ["Creature"],
  "subtypes": ["Human", "Soldier"]
}
```

Treasure needs its sacrifice-for-mana ability. Axe needs its Equipment effect and equip cost. The Dragon and other creature tokens need P/T and keywords.

Without those properties, later graph construction will miss:

* Recruit creating a white 1/1
* Token power satisfying Ferocious
* Flying-token interactions
* Treasure producing mana
* Equipment-token interactions
* Sacrifice costs
* Creature-count and subtype effects

The related Scryfall token objects should be fetched and normalized rather than using only `all_parts` names/type lines.

## Gandalf’s status specifically

Gandalf is correct for the intended phase boundary:

| Required Phase 2 fact                     | Status                                  |
| ----------------------------------------- | --------------------------------------- |
| Two faces                                 | Correct                                 |
| Separate types and costs                  | Correct                                 |
| Adventure cast operation                  | Present                                 |
| Adventure resolution/exile route          | Present but object binding is incorrect |
| Permanent castable normally               | Present                                 |
| Permanent castable after Adventure        | Present but enabled by generic exile    |
| Legendary permanent qualifies for Storied | Present                                 |
| Wizard subtype available for Phase 3      | Present in `faces`, not yet globalized  |
| Custom trigger parsed                     | Correctly deferred                      |
| Flameshape permission parsed              | Correctly deferred                      |

One additional pipeline check: [mechanical_extractions.jsonl](sandbox:/workspace/scratch/e3646a5cdd6d/upload/mechanical_extractions.jsonl) contains no Gandalf-specific extraction. That is acceptable only if Phase 3 sends **every Oracle-bearing face** to the LLM. If Phase 3 processes only records nominated by `mechanical_extractions.jsonl`, both Gandalf and Flameshape will be skipped.

## Verdict

The phase is approximately right in coverage and separation of responsibilities, but I would amend Phase 2 before treating it as frozen:

1. Separate concepts/types from object-bound states and event instances.
2. Bind Adventure exile permission to the exact physical card.
3. Avoid treating casting as guaranteed resolution.
4. Make Recruit outputs either per-instance or generic-template outputs—not duplicated parallel edges.
5. Bind lore counters and chapters to the same Saga object.
6. Bind hone counters to particular Equipment objects.
7. Change card-level Storied edges from `CONTRIBUTES_TO` to `QUALIFIES_FOR`.
8. Fully normalize token characteristics.
9. Confirm Phase 3 processes all 210 faces, not only mechanical-extraction hits.

The core schema is sound. The issue is not that the graph lacks more edges; it is that several shared nodes currently erase **which object an event, counter, permission, or condition belongs to**. That would create false card-pair paths later, so it is worth repairing now.
