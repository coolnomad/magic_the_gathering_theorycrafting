# HOB Phase 3 — LLM Semantic Extraction Coverage (FROZEN v3)

> Extractor + independent critic (Claude Code agents). v3 fixes the multiface
> keyword-attribution defect: Amass now on Clap! Snap! (face :1), object-bound
> template, 0 inline duplicates, no primary-face fallback for unsupported multiface keywords.

- **normalized faces dispositioned**: 210 / 210 (209 extracted + 1 reviewed_empty)
- **accepted abilities**: 418
- **accepted edges**: 1011
- **unresolved (excluded)**: 1
- **predicate-signature violations in accepted**: 0
- **Amass: INSTANTIATES rule:amass**: 14 | **inline goblin-army expansions**: 0
- **schema_extension_requests remaining**: 0

## Disposition verdicts

- accepted_critic: 62
- accepted_extractor: 9
- unresolved: 1
- corrected: 1

## Accepted ability kinds

- triggered: 142
- static: 134
- spell_effect: 67
- activated: 59
- replacement: 16

## Accepted edge predicates

- HAS_ABILITY: 268
- TRIGGERS: 84
- HAS_KEYWORD: 80
- MOVES_TO: 78
- CAUSES: 65
- MODIFIES: 63
- REFERENCES_RULE: 57
- PRODUCES: 51
- SCALES_WITH: 36
- ADDS_COUNTER: 35
- MOVES_FROM: 35
- CREATES_OBJECT: 34
- CONSUMES: 24
- INSTANTIATES: 16
- ENABLES: 15
- REQUIRES: 12
- HAS_COST: 12
- ATTACHED_TO: 11
- PREVENTS: 10
- REPLACES: 7
- HAS_STATE: 6
- CAN_LEAD_TO: 5
- HAS_COUNTER_TYPE: 4
- PERSISTS_AS: 1
- QUALIFIES_FOR: 1
- REMOVES_COUNTER: 1

## Unresolved

- `face:4a5f76e7-40be-4b06-9935-4a3b2672e1c2:0` a1 -DERIVED_FROM-> zone:graveyard — No clean primitive for "gains the activated abilities of Elf cards in your graveyard"; DERIVED_FROM is a graph-provenance predicate, not a game-mechanic ability-grant relation.

Phase 4 canonicalization requirements: see docs/phase4-requirements.md. Coverage is not correctness. (spec)
