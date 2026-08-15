# HOB Phase 4 — Global Assembly (v4.1)

- **nodes**: 1769
- **edges**: 2728
- **conditions (self-contained)**: 145 (64 structured, 81 raw-unresolved)
- **adventure faces / resolution paths**: 17 / 17
- **mana paths (controller / opponent-only)**: 21 / 1

## Gate metrics (every one must be 0)

- **signature_violations**: 0  OK
- **unknown_endpoint_edges**: 0  OK
- **unknown_type_nodes**: 0  OK
- **leaked_ability_aliases**: 0  OK
- **unresolved_condition_refs**: 0  OK
- **edges_missing_id**: 0  OK
- **template_duplicate_edges**: 0  OK
- **face_to_rule_amass_edges**: 0  OK
- **dangling_edges**: 0  OK
- **faces_missing_type_data**: 0  OK
- **faces_missing_type_edges**: 0  OK
- **faces_missing_cost_edge**: 0  OK
- **mana_faces_without_mana_path**: 0  OK
- **false_direct_mana_operations**: 0  OK
- **materialized_edges_without_provenance**: 0  OK
- **tokens_missing_characteristics**: 0  OK
- **raw_executable_conditions**: 0  OK
- **raw_conditions_not_marked_unresolved**: 0  OK
- **llm_reminder_adventure_exile_paths**: 0  OK

## Node types

- Ability: 447
- Operation: 402
- CardFace: 210
- Cost: 206
- Card: 193
- ObjectClass: 145
- Event: 72
- State: 43
- Resource: 14
- TokenSpec: 12
- Rule: 10
- Zone: 6
- CounterType: 5
- Gate: 3
- Effect: 1

## Edge predicates

- HAS_TYPE: 538
- HAS_ABILITY: 494
- CAUSES: 340
- HAS_FACE: 210
- HAS_COST: 209
- REFERENCES_RULE: 88
- MOVES_TO: 88
- MOVES_FROM: 84
- TRIGGERS: 82
- MODIFIES: 80
- HAS_KEYWORD: 80
- QUALIFIES_FOR: 78
- PRODUCES: 65
- ENABLES: 60
- SCALES_WITH: 35
- ADDS_COUNTER: 34
- CREATES_OBJECT: 27
- INSTANTIATES: 26
- CONSUMES: 23
- CAN_LEAD_TO: 21
- REQUIRES: 13
- ATTACHED_TO: 12
- HAS_COUNTER_TYPE: 11
- PREVENTS: 9
- HAS_STATE: 8
- REPLACES: 7
- COUNTS: 3
- PERSISTS_AS: 2
- REMOVES_COUNTER: 1
