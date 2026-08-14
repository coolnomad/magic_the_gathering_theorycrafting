# HOB Phase 3 — LLM Semantic Extraction Coverage (FROZEN)

> Extractor + independent critic performed by Claude Code agents (no API). Accepted =
> assertions on which extractor and critic AGREE and which pass deterministic validation;
> queued disagreements adjudicated into dispositions; every normalized face dispositioned.

- **normalized faces dispositioned**: 210 / 210 (209 extracted + 1 reviewed_empty)
- **accepted abilities**: 417
- **accepted edges**: 1001
- **unresolved (preserved out of accepted graph)**: 2
- **span warnings (extractor-candidate audit; 0 overruns in accepted)**: 16
- **schema_extension_requests remaining**: 0 (Amass + typecycling now templates)

## Disposition verdicts (25 queued faces, 40 disputed items)

- accepted_critic: 38
- unresolved: 2

## Accepted ability kinds

- triggered: 141
- static: 133
- spell_effect: 68
- activated: 59
- replacement: 16

## Accepted edge predicates

- HAS_ABILITY: 234
- MOVES_TO: 81
- HAS_KEYWORD: 80
- TRIGGERS: 74
- CAUSES: 62
- MODIFIES: 62
- REFERENCES_RULE: 58
- PRODUCES: 52
- CREATES_OBJECT: 41
- ADDS_COUNTER: 41
- SCALES_WITH: 40
- MOVES_FROM: 34
- CONSUMES: 25
- HAS_COUNTER_TYPE: 21
- ENABLES: 17
- REQUIRES: 14
- ATTACHED_TO: 12
- HAS_COST: 12
- PREVENTS: 10
- INSTANTIATES: 8
- REPLACES: 7
- CAN_LEAD_TO: 5
- PERSISTS_AS: 4
- HAS_STATE: 3
- COUNTS: 2
- QUALIFIES_FOR: 1
- REMOVES_COUNTER: 1

## Unresolved items (genuine ambiguity, excluded from accepted)

- `face:4a5f76e7-40be-4b06-9935-4a3b2672e1c2:0` a1 -DERIVED_FROM-> zone:graveyard — DERIVED_FROM is a graph-provenance predicate, not a game-mechanic "gains the activated abilities of Elf cards in your graveyard" relation; no existing primitive cleanly models this, so preserve out of the accepted graph.
- `face:83dcfac0-6efd-4e37-9402-15f9889e84e1:0` a1 -TRIGGERS-> counter:generic — TRIGGERS is Event->Ability; asserting Ability->CounterType mis-directs it. The counter-placement trigger needs an explicit event node; preserve as unresolved pending a proper event-mediated form.

Coverage is not correctness; do not maximize edge count. (spec)
