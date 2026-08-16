# HOB Coverage Report (Phase 6)

*Coverage is not correctness; edge count is not maximized.*

- cards / faces parsed: **193 / 210**
- abilities by kind: {'?': 29, 'triggered': 142, 'static': 134, 'spell_effect': 67, 'replacement': 16, 'activated': 59}
- primitive edges (per layer + union): frozen **2728** + repair **9** + legend **113** = union **2850** (+1 repair nodes, +58 legend nodes); by origin {'phase4': 2728, 'graph_repair': 9, 'legend_rule': 113}; provenance gaps: 0
- pair relations (per layer + union): mechanical **5278** + audited **3** + repaired **8** = union **5289**
- conditions: 145 (81 raw-unresolved); unresolved Oracle records: 16
- LLM: 210 faces accepted; audit 5 accepted / 114 no-relation / 10 graph-repair
- pair relations: **5278** {'CONTRIBUTES_TO_GATE': 666, 'INFRASTRUCTURE_CASTING': 4593, 'ENABLES_TRIGGER': 4, 'SUPPLIES_RESOURCE': 15}
- pairs with multiple relation types: 80
- gate-mediated relations: 666; infrastructure-only pairs: 4513
- cards with NO non-infrastructure outgoing relation: **112**
- cards with NO non-infrastructure incoming relation: **176**

## Edges by predicate

- HAS_TYPE: 538
- HAS_ABILITY: 494
- CAUSES: 348
- HAS_FACE: 210
- HAS_COST: 209
- ENABLES: 115
- REFERENCES_RULE: 89
- MOVES_TO: 89
- MOVES_FROM: 84
- TRIGGERS: 82
- MODIFIES: 81
- HAS_KEYWORD: 80
- QUALIFIES_FOR: 78
- PRODUCES: 65
- HAS_STATE: 63
- SCALES_WITH: 35
- ADDS_COUNTER: 34
- CREATES_OBJECT: 27
- INSTANTIATES: 26
- CONSUMES: 23
- CAN_LEAD_TO: 21
- REQUIRES: 14
- ATTACHED_TO: 12
- HAS_COUNTER_TYPE: 11
- PREVENTS: 9
- REPLACES: 7
- COUNTS: 3
- PERSISTS_AS: 2
- REMOVES_COUNTER: 1

## Deferred / unmodeled semantic invariants

*Recorded as honest representational gaps — the graph asserts no edge rather than inventing an unsupported one.*

- **#2 Recruit -> Master's Councillors second-draw ordering** — _deferred_unmodeled_: Councillors triggers only on 'the second card drawn each turn' — a per-turn ORDERING condition. Modeling it needs a turn-scoped cards-drawn-this-turn count state/gate (draw -> increment count -> count reaches 2 -> second-draw event -> Councillors), where Recruit contributes one draw without being sufficient alone. Until that turn-scoped counter exists, the graph correctly asserts NO Recruit<->Councillors edge in either direction across all three projection layers.

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
