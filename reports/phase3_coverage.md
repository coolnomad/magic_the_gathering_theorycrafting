# HOB Phase 3 — LLM Semantic Extraction Coverage

> Extractor + independent critic, both performed by Claude Code agents (no API).
> Accepted = assertions on which extractor and critic AGREE and which pass deterministic
> validation (JSON-Schema + controlled-predicate vocab + provenance + no evaluative language).

- **faces processed**: 209 / 209 Oracle-bearing (of 210 total)
- **candidates (validated extractor outputs)**: 209 (0 rejections)
- **accepted abilities**: 416
- **accepted edges**: 983
- **queued (extractor/critic disagreement)**: 22
- **soft span warnings (end overrun, recorded not repaired)**: 18

## Accepted ability kinds

- triggered: 141
- static: 133
- spell_effect: 67
- activated: 59
- replacement: 16

## Accepted edge predicates

- HAS_ABILITY: 229
- HAS_KEYWORD: 80
- MOVES_TO: 78
- TRIGGERS: 68
- CAUSES: 61
- MODIFIES: 61
- REFERENCES_RULE: 57
- PRODUCES: 49
- ADDS_COUNTER: 48
- CREATES_OBJECT: 48
- SCALES_WITH: 40
- MOVES_FROM: 33
- CONSUMES: 26
- HAS_COUNTER_TYPE: 21
- ENABLES: 17
- REQUIRES: 12
- ATTACHED_TO: 12
- HAS_COST: 11
- PREVENTS: 9
- REPLACES: 7
- CAN_LEAD_TO: 5
- PERSISTS_AS: 4
- HAS_STATE: 3
- COUNTS: 2
- QUALIFIES_FOR: 1
- REMOVES_COUNTER: 1

## Schema-extension requests (surfaced, not yet adopted)

- `AMASSES`: 7 cards
- `HAS_KEYWORD_TYPECYCLING`: 1 cards

Amass is representable with existing predicates (`CREATES_OBJECT token:goblin-army` +
`ADDS_COUNTER`), so it does not block; a dedicated Amass template is a candidate for a
later schema decision. Coverage is not correctness; do not maximize edge count. (spec)
