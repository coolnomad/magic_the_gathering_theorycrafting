# HOB Coverage Report (Phase 6)

*Coverage is not correctness; edge count is not maximized.*

- cards / faces parsed: **193 / 210**
- abilities by kind: {'?': 43, 'triggered': 142, 'static': 134, 'spell_effect': 67, 'replacement': 16, 'activated': 59, 'state_based_action': 1, 'automatic': 4, 'static_pt_bonus': 9, 'static_grant': 6, 'sacrifice_outlet': 9}
- primitive edges (per layer + union): frozen **2728** + repair **9** + legend **113** + mechanism **111** + equip **173** + completeness **101** = union **3235** (+1 repair, +58 legend, +3 mechanism, +107 equip, +28 completeness nodes); by origin {'phase4': 2728, 'graph_repair': 9, 'legend_rule': 113, 'mechanism_repair': 111, 'equip': 173, 'completeness': 101}; provenance gaps: 0
- pair relations (per layer + union): mechanical **5278** + audited **3** + repaired **8** + mechanism **392** + equip **3250** + completeness **1036** = union **9967**
- conditions all resolve: **True** (unresolved: none)
- conditions: 166 (81 raw-unresolved); unresolved Oracle records: 16
- LLM: 210 faces accepted; audit 5 accepted / 114 no-relation / 10 graph-repair
- pair relations: **5278** {'CONTRIBUTES_TO_GATE': 666, 'INFRASTRUCTURE_CASTING': 4593, 'ENABLES_TRIGGER': 4, 'SUPPLIES_RESOURCE': 15}
- pairs with multiple relation types: 80
- gate-mediated relations: 666; infrastructure-only pairs: 4513
- cards with NO non-infrastructure outgoing relation: **112**
- cards with NO non-infrastructure incoming relation: **176**

## Edges by predicate

- HAS_ABILITY: 621
- HAS_TYPE: 552
- CAUSES: 432
- HAS_COST: 223
- HAS_FACE: 210
- ENABLES: 115
- PRODUCES: 109
- REFERENCES_RULE: 102
- MOVES_TO: 98
- MODIFIES: 96
- MOVES_FROM: 84
- TRIGGERS: 83
- HAS_KEYWORD: 80
- QUALIFIES_FOR: 78
- REQUIRES: 64
- HAS_STATE: 63
- CONSUMES: 36
- SCALES_WITH: 35
- ADDS_COUNTER: 34
- CREATES_OBJECT: 27
- INSTANTIATES: 26
- CAN_LEAD_TO: 21
- ATTACHED_TO: 12
- HAS_COUNTER_TYPE: 11
- PREVENTS: 9
- REPLACES: 7
- COUNTS: 3
- PERSISTS_AS: 2
- REMOVES_COUNTER: 1
- SATISFIES: 1

## Deferred / unmodeled semantic invariants

*Recorded as honest representational gaps — the graph asserts no edge rather than inventing an unsupported one.*

- _none_ — every spec semantic invariant is now modeled (invariant #2, the Recruit → Master's Councillors second-draw ordering, is resolved in the mechanism-repair layer via `state:cards-drawn-this-turn` + `gate:second-draw`).

## Cards with no non-infrastructure outgoing relation (sample)

- Rhovanion Rampager
- Bejeweled Warg
- Lake-town Toymaker
- Silvan Reveler
- Uneasy Partings
- The Eagles Are Coming!
- Hobbit Hole
- Gnashing of Teeth
- Great Ugly-Looking Goblin // Clap! Snap!
- Woodland Weavemaster
- Settle the Wreckage
- Thranduil's Company
- The Lonely Mountain
- Chief Warg's Company
- Great Fierce Bee
- An Unexpected Party // At the Door
- Mirkwood Meditator
- Thorin's Last Stand
- Dreaded Bat-Cloud
- Moment of Glory
- Attercop
- Bilbo's Deadly Slice
- Last Light of Durin's Day
- Little Bear
- Swamp
- Tidings of War
- Dancing from Dark to Dawn
- Smaug's Fury
- Bard's Company
- Gundabad Opportunist
