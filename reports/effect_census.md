# HOB effect-family census (Phase 1.2 — complete clause ledger)

Deterministic scan of **all Oracle text on all faces** (permanents included), grouped into semantic **clauses** (one row per (ability, mode) clause, carrying `clause_span` + full `clause_text`, per-family `match_span`s, ability/mode/sentence indices, and every family detected). **EVERY segmented clause is emitted, even with zero detected families** (`families: []`, `disposition: pending_classification`) so no material effect can be dropped for lack of a detector. Detectors are broad CANDIDATE catchers; reminder-text hits are flagged, not removed. Heuristic reference counts are from the instructions and are NOT acceptance values.

- faces scanned: **210**  · faces with a clause: **209**  · total clauses: **408**  · zero-family (pending_classification): **82**

| family | faces w/ candidate | reminder-only | clauses | heuristic ref | prior-layer coverage |
|---|---:|---:|---:|---:|---|
| `draw` | 37 | 10 | 48 | 53 | mechanism (second-draw gate) |
| `discard` | 13 | 12 | 25 | 25 | — |
| `sacrifice` | 23 | 11 | 36 | 34 | sac_schema + completeness/lifecycle |
| `exile` | 17 | 16 | 33 | 33 | — |
| `mill` | 6 | 0 | 6 | 6 | — |
| `return_move` | 13 | 0 | 13 | 13 | — |
| `tutor_search` | 11 | 0 | 13 | 10 | audit_repair (tutor) |
| `token_create` | 23 | 23 | 46 | 46 | audit_repair (token-enter) |
| `amass` | 13 | 1 | 14 | — | — |
| `life` | 22 | 0 | 22 | 22 | — |
| `counterspell` | 3 | 0 | 3 | 3 | — |
| `play_cast_permission` | 12 | 15 | 27 | 23 | — |
| `deal_damage` | 19 | 1 | 20 | — | effect_semantics (Phase 3 planned) |
| `destroy` | 10 | 0 | 11 | — | effect_semantics (CAN_DESTROY) |
| `tap_untap` | 8 | 1 | 11 | — | — |
| `add_counter` | 45 | 1 | 47 | — | audit_repair (targeted-counter) |
| `remove_counter` | 1 | 0 | 1 | — | — |
| `modify_pt` | 40 | 1 | 42 | — | audit_repair (anthem/pump) + equip |
| `set_switch_pt` | 4 | 0 | 4 | — | — |
| `grant_ability` | 28 | 0 | 29 | — | equip (granted-when-attached) |
| `remove_ability` | 1 | 0 | 1 | — | — |
| `fight` | 1 | 0 | 1 | — | — |
| `prevent` | 1 | 0 | 1 | — | — |
| `control_change` | 1 | 0 | 1 | — | — |
| `type_change` | 4 | 1 | 5 | — | — |
| `scry_look_reveal` | 16 | 3 | 19 | — | — |
| `copy` | 1 | 0 | 1 | — | — |
| `cost_modification` | 10 | 1 | 11 | — | infrastructure_casting |
| `additional_land` | 2 | 0 | 2 | — | — |
| `restriction` | 13 | 5 | 18 | — | — |
| `delayed` | 7 | 3 | 10 | — | lifecycle (delayed sac) |
| `replacement` | 7 | 8 | 16 | — | legend_rule (SBA) |
| `attachment` | 20 | 0 | 25 | — | equip layer |
| `mana_production` | 12 | 11 | 23 | — | infrastructure/mechanism (mana) |

All dispositions are `pending_structuring`; see `docs/hob_effect_semantics_repair_instructions.md` for the required dispositions and the per-family structuring plan. A clause may list several families (e.g. Warg Tactics mode-1 carries `add_counter` + `grant_ability`) so it is adjudicated once, consistently.

