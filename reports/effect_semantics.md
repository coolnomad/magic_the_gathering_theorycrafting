# Effect-semantics — structured effects (Phase 3b: targeted-object families)

Additive `effect_semantics` layer over the frozen reference. **ABILITY-scoped** extraction (one clause per (ability, mode); targets never leak across abilities; real `clause_id`), with **same-object variable binding**, **per-operation duration/condition**, explicit self-effects, object-vs-participant separation, comma-OR subtype lists, and empty-object-selector rejection. Families: destruction, damage (incl. source-power & any-target), counters, power/toughness (mod + set/switch), ability grant/removal, tap/untap, fight, type-change, control-change, and damage-prevention. Each effect is a validated record; projection aggregates all supporting effects/modes per pair (`supports`). Frozen core untouched. **Proposed schema extensions (documented, not casually invented):** `CAN_FIGHT`, `CHANGES_TYPE_OF`, `SETS_BASE_PT`, `SWITCHES_PT`, `REMOVES_ABILITY_FROM`, `EXCHANGES_CONTROL_OF`/`GAINS_CONTROL_OF`, `PREVENTS_DAMAGE_FROM`. Every Phase-3 census clause is reconciled (`reports/effect_reconciliation.md`, 0 unresolved).

- effects: **120** on 90 faces  · pairs: **7950**

| relation | pairs |  | op | effects |
|---|---:|---|---|---:|
| `ADDS_COUNTER_TO` | 1794 |  | `ADD_COUNTER` | 32 |
| `MODIFIES_POWER_TOUGHNESS` | 1619 |  | `MODIFY_PT` | 31 |
| `GRANTS_ABILITY_TO` | 1415 |  | `GRANT_ABILITY` | 20 |
| `CAN_DEAL_DAMAGE_TO` | 1120 |  | `DESTROY` | 10 |
| `CAN_DESTROY` | 603 |  | `DEAL_DAMAGE` | 10 |
| `CAN_UNTAP` | 461 |  | `UNTAP` | 5 |
| `CHANGES_TYPE_OF` | 225 |  | `SET_BASE_PT` | 4 |
| `CAN_TAP` | 224 |  | `CHANGE_TYPE` | 3 |
| `EXCHANGES_CONTROL_OF` | 150 |  | `TAP` | 2 |
| `SETS_BASE_PT` | 115 |  | `FIGHT` | 1 |
| `CAN_FIGHT` | 112 |  | `CONTROL_CHANGE` | 1 |
| `PREVENTS_DAMAGE_FROM` | 112 |  | `PREVENT_DAMAGE` | 1 |
