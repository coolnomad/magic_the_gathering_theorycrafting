I examined the repository at the frozen `ab1a1c8` commit and current `main` (`479d5d2`). The bookkeeping claims are correct, but Phase 3 is not yet semantically safe to freeze.

The good news:

* 210 face dispositions exist.
* Ordinary Bear is correctly `reviewed_empty`.
* Counts reproduce: 417 abilities, 1,001 accepted edges, 2 unresolved.
* No extension requests remain.
* The two manually retained unresolved edges were correctly rejected.
* The repository is clean, and the later commit only adds the orchestration playbook.

However, I found three blocking problems.

## 1. Thirty-one accepted `TRIGGERS` edges violate the predicate schema

The spec defines:

```text
Event ──TRIGGERS──> Ability
```

Of the 74 accepted `TRIGGERS` edges:

* 43 have the correct event → ability form.
* 31 do not.

The accepted graph includes patterns such as:

```text
Ability ──TRIGGERS──> Event
CounterType ──TRIGGERS──> Ability
CardFace ──TRIGGERS──> target object
Ability ──TRIGGERS──> Ability
```

Examples include:

```text
ability → event:etb
ability → event:attack
counter:lore → Saga chapter ability
face → target creature
second-draw ability → second-draw event
```

The agent correctly caught the Great Goblin instance manually, but the same predicate-domain problem survived elsewhere.

The current validator checks:

* allowed predicate name;
* JSON structure;
* provenance presence;
* face ID;
* span bounds;
* evaluative language.

It does **not** validate predicate domain and range. Consequently, extractor–critic agreement can approve the same structural mistake twice.

Required fix:

```python
PREDICATE_SIGNATURES = {
    "TRIGGERS": {
        "source_types": {"Event"},
        "target_types": {"Ability"},
    },
    "HAS_ABILITY": {
        "source_types": {"CardFace", "ObjectClass"},
        "target_types": {"Ability", "Operation"},
    },
    # ...
}
```

Phase 3 validation needs to resolve local IDs to proposed node types and reject edges that violate these signatures.

For trigger corrections:

* ordinary triggered ability: `Event → TRIGGERS → Ability`;
* reflexive sequencing: preceding ability/effect `CAUSES` an event, then event `TRIGGERS` the reflexive ability;
* Saga chapters: lore-state transition condition `ENABLES` the chapter ability;
* “when counters are placed”: create a counter-placement `Event`, then connect it to the ability.

## 2. The Amass template is not object-bound

The current template contains:

```text
op:amass → gate:no-army
gate:no-army → creates token:army
op:amass → op:add-counters
op:add-counters → counter:+1/+1
```

But it never represents the selected Army object receiving the counters. There is also no binding that says the newly created Army is eligible to become that selected Army in the next step.

The value (N) and Army subtype exist only in the card-specific instantiation’s data. They are not propagated into the add-counter operation.

It therefore cannot yet execute:

```text
If no Army exists, create Army A
Choose an Army A controlled by the player
Add N +1/+1 counters to that same A
Add the specified subtype to A
```

The corrected template needs a bound variable:

```text
Army object A
amass instance supplies subtype S and quantity N

if no Army:
    create A

select controlled Army A
modify counter_count(A, +1/+1) by N
ensure A has Army and subtype S
```

This is the same object-identity issue previously fixed for Adventures and hone.

The current tests only verify that an `ADDS_COUNTER` edge reaches the global counter type. They do not test the target Army, subtype application, parameter propagation, or created-object continuity.

## 3. Mixed inline/template Amass is not harmless

Seven LLM records retain inline:

```text
CREATES_OBJECT + ADDS_COUNTER
```

while the Phase 2 graph also instantiates the generic template.

If Phase 4 unions both representations, these create duplicate mechanistic paths and potentially double-count:

* Army creation capacity;
* counter-production capacity;
* pairwise relationships;
* path multiplicity;
* module strength.

All 14 Amass cards should use the same representation. I recommend:

* retain the card-specific ability and trigger from the LLM extraction;
* replace inline Amass expansion with one `INSTANTIATES op:amass` edge carrying (N) and subtype;
* let the generic template provide the internal semantics;
* explicitly suppress redundant inline edges during assembly.

## Typecycling also needs strengthening

The current generic typecycling template captures:

```text
card → graveyard
library → hand
```

but does not yet explicitly encode:

* the mana payment;
* discarding this exact card as a cost;
* the searched type parameter as a requirement;
* revealing the selected card;
* shuffling afterward.

At minimum:

```text
typecycling ability
 ├── HAS_COST → mana cost
 ├── CONSUMES → this card from hand
 ├── REQUIRES → card with subtype Halfling in library
 ├── MOVES_FROM → library
 ├── MOVES_TO → hand
 ├── CAUSES → reveal
 └── CAUSES → shuffle
```

## Verdict

The Phase 3 extraction itself is impressive and useful, but I would reopen the freeze for one structural closure pass before Phase 4.

Send the agent this:

> Reopen Phase 3 for structural validation. Add predicate domain/range signatures and revalidate all 1,001 accepted edges; 31 of 74 accepted `TRIGGERS` edges currently violate Event→Ability direction/type semantics. Correct them using explicit event nodes, `CAUSES`, or condition-mediated `ENABLES` as appropriate. Make Amass object-bound with Army variable A, propagate subtype S and quantity N, and ensure a newly created Army is the same class of object selected for counters. Normalize all 14 Amass cards to `INSTANTIATES` and suppress inline duplicate expansions. Complete the typecycling template with mana/discard costs, searched-type binding, reveal, and shuffle. Add regression tests for predicate signatures, Amass target identity/parameter propagation, and duplicate-path prevention before refreezing Phase 3.

After that, Phase 4 can safely namespace and canonicalize. Right now, simple assembly would convert several known semantic inconsistencies into authoritative global edges. [Repository](https://github.com/coolnomad/magic_the_gathering_theorycrafting/tree/main)
