# HOB Phase 4 — Global Assembly

- **nodes**: 1646
- **edges**: 2135
- **dangling edges**: 0
- **signature violations**: 7
- **edges with Unknown endpoint type**: 0
- **nodes with Unknown type**: 0
- **face-to-rule amass edges (must be 0)**: 0

## Node types

- Ability: 533
- Operation: 447
- CardFace: 210
- Card: 193
- ObjectClass: 88
- Event: 72
- State: 43
- Resource: 14
- TokenSpec: 12
- Rule: 10
- Cost: 9
- Zone: 6
- CounterType: 5
- Gate: 3
- Effect: 1

## Edge predicates

- HAS_ABILITY: 653
- CAUSES: 305
- HAS_FACE: 210
- MOVES_TO: 100
- REFERENCES_RULE: 86
- MOVES_FROM: 84
- TRIGGERS: 81
- MODIFIES: 80
- HAS_KEYWORD: 80
- QUALIFIES_FOR: 77
- PRODUCES: 65
- ENABLES: 59
- ADDS_COUNTER: 36
- CREATES_OBJECT: 35
- SCALES_WITH: 35
- INSTANTIATES: 26
- CAN_LEAD_TO: 22
- CONSUMES: 22
- REQUIRES: 13
- ATTACHED_TO: 12
- HAS_COST: 12
- HAS_COUNTER_TYPE: 11
- PREVENTS: 9
- HAS_STATE: 8
- REPLACES: 7
- COUNTS: 3
- PERSISTS_AS: 2
- HAS_TYPE: 1
- REMOVES_COUNTER: 1

## Signature violations (sample)

- obj:objectclass-food-artifact(ObjectClass) -PRODUCES-> op:gain-life(Operation)
- op:gollum-ab-recur(Operation) -MOVES_FROM-> face:8d88facd-cf7e-498e-ab6b-6bd021316162:0(CardFace)
- op:face:a97d6c5c-1cff-442d-b535-fc8389160b0b:0:a97d6c5c-ch34(Operation) -PRODUCES-> op:add-mana(Operation)
- op:face:c9634afc-4a5b-4cf6-b63d-0ff9909dd5a7:0:c9634afc-a2(Operation) -PRODUCES-> op:add-mana(Operation)
- ability:face:f75bb13b-41fc-4614-b35e-f456069ce9c6:0:a1(Ability) -ATTACHED_TO-> obj:target-dwarf-you-control(ObjectClass)
- ability:face:f8961618-ae68-4d13-84eb-8b5464ce4971:0:f8961618-a1(Ability) -ATTACHED_TO-> obj:target-creature-you-control(ObjectClass)
- op:face:fa602f8f-1d80-4f6d-8b8f-d1a1f36037bd:0:eff1(Operation) -CONSUMES-> event:sacrifice(Event)
