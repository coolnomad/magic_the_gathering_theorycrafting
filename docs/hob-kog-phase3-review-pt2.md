Most of the v2 refreeze checks out, but the Adventure/Amass exception is not harmless—the agent’s own output confirms one remaining attribution defect.

## What now passes

* All 84 accepted `TRIGGERS` edges are Event → Ability.
* No trigger-signature violations remain.
* Amass’s generic template is object-bound through `obj:army-A`.
* The same Army variable is used for creation, selection, counter state, and modification.
* Typecycling now includes cost, discard destination, searched-type requirement, library-to-hand movement, reveal, and shuffle.
* Phase 2 has no dangling endpoints.
* Counts reproduce: 210 faces, 418 abilities, 1,013 accepted edges, one unresolved edge.

## Remaining defect: Clap! Snap! is attributed to the wrong face

The normalized faces are correct:

```text
face ...:0 = Great Ugly-Looking Goblin
Oracle: creatures with +1/+1 counters have menace

face ...:1 = Clap! Snap!
Oracle: Amass Goblins 2
```

But `mechanics.jsonl` assigns the card-level Scryfall `Amass` keyword to face `:0`.

That produces an incorrect Phase 2 instantiation:

```text
op:face:...:0:amass
army_subtype = Goblin
n = N
span = null
```

Meanwhile, the correct Adventure face `:1` still contains inline:

```text
CREATES_OBJECT → token:goblin-army
ADDS_COUNTER → counter:+1/+1
REFERENCES_RULE → keyword:amass
```

Consequently:

* Phase 2 reports 14 Amass instantiations, but one is attached to the wrong face.
* The accepted LLM layer has only 13 `INSTANTIATES` Amass edges.
* Clap! Snap! remains the exact mixed inline/template case that was supposed to be eliminated.
* Great Ugly-Looking Goblin falsely appears to have an Amass capability.
* The erroneous instantiation has no Oracle span and loses the actual value (N=2).

The claim that “the keyword was attributed to the permanent face by Scryfall, not a missing representation” identifies the source of the bug, but does not make the representation correct. Card-level Scryfall keywords cannot determine face ownership on multiface cards.

## Required targeted correction

Do not reopen the whole Phase 3 run. Make one deterministic normalization/rule-expansion fix:

1. For multiface cards, assign named mechanics using the face’s Oracle text and type/role.
2. Treat top-level Scryfall keywords as card-level hints only.
3. Remove the Amass mechanic and Phase 2 instantiation from face `:0`.
4. Assign Amass to Clap! Snap!, face `:1`.
5. Instantiate:

```text
op:face:...:1:amass
    INSTANTIATES op:amass
    army_subtype = Goblins
    n = 2
```

6. Remove the inline `CREATES_OBJECT` and `ADDS_COUNTER` Amass expansion from face `:1`, retaining its spell ability and its template instantiation.
7. Rerun reconciliation/finalization and the graph build.

Add regression tests:

```python
assert not has_amass(great_ugly_face)
assert has_amass(clap_snap_face)
assert amass_params(clap_snap_face) == {
    "army_subtype": "Goblins",
    "n": "2",
}
assert count_amass_instantiations() == 14
assert count_inline_amass_expansions() == 0
assert all_amass_instantiations_have_oracle_spans()
```

Also add a general invariant:

> On multiface cards, a card-level keyword may nominate candidate faces but may not be assigned to a face unless supported by that face’s Oracle text, type line, or an explicit face-specific rule.

After that correction, I would accept Phase 3 v2 and proceed to Phase 4. The documented CardFace-as-actor convention can be handled there, provided Phase 4 converts it into explicit Operation nodes and then enforces strict domain/range validation with no unresolved endpoint types.
