# HOB effect-family census (Phase 1 — deterministic candidate detection)

Deterministic scan of **all Oracle text on all faces** (permanents included). Each family's detector is a broad CANDIDATE catcher; reminder-text hits are flagged (`reminder_only`), not removed. Every candidate's disposition is `pending_structuring` — later phases replace it with structured / not-projected / ignored / unresolved. Heuristic reference counts are from the instructions and are NOT acceptance values.

- faces scanned: **210**  · faces with ≥1 candidate: **179**

| family | faces w/ candidate | reminder-only | clauses | heuristic ref | prior-layer coverage |
|---|---:|---:|---:|---:|---|
| `draw` | 37 | 10 | 50 | 53 | mechanism layer (second-draw gate) |
| `discard` | 13 | 12 | 26 | 25 | — |
| `sacrifice` | 23 | 11 | 37 | 34 | sac_schema + completeness/lifecycle |
| `exile` | 17 | 16 | 46 | 33 | — |
| `mill` | 6 | 0 | 6 | 6 | — |
| `return_move` | 13 | 0 | 13 | 13 | — |
| `tutor_search` | 11 | 0 | 14 | 10 | audit_repair (Seek the Heart tutor) |
| `token_create` | 23 | 23 | 47 | 46 | audit_repair (token-enter) |
| `amass` | 13 | 1 | 17 | — | — |
| `life` | 22 | 0 | 24 | 22 | — |
| `counterspell` | 3 | 0 | 3 | 3 | — |
| `play_cast_permission` | 10 | 15 | 26 | 23 | — |
| `deal_damage` | 19 | 1 | 20 | — | — |
| `destroy` | 10 | 0 | 12 | — | — |
| `tap_untap` | 8 | 1 | 13 | — | — |
| `add_counter` | 33 | 11 | 46 | — | audit_repair (targeted-counter) |
| `modify_pt` | 40 | 1 | 42 | — | audit_repair (anthem/pump) + equip |
| `grant_ability` | 27 | 0 | 27 | — | equip (granted-when-attached) |
| `fight` | 1 | 0 | 1 | — | — |
| `prevent` | 1 | 0 | 1 | — | — |
| `control_change` | 0 | 0 | 0 | — | — |
| `type_change` | 3 | 0 | 3 | — | — |

All dispositions are `pending_structuring` at Phase 1; see `docs/hob_effect_semantics_repair_instructions.md` for the required dispositions and the per-family structuring plan.

