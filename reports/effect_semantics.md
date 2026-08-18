# Effect-semantics — structured effects (Phase 3a: targeted-object families)

Additive `effect_semantics` layer over the frozen reference. **ABILITY-scoped** extraction (one clause per (ability, mode); targets never leak across abilities; real `clause_id`), with **same-object variable binding**, **per-operation duration/condition**, explicit self-effects, object-vs-participant separation, comma-OR subtype lists, and empty-object-selector rejection. Families: destruction, damage (incl. source-power & any-target), counters, power/toughness (mod + set/switch), ability grant/removal, tap/untap, fight, type-change, control-change, and damage-prevention. Each effect is a validated record; projection aggregates all supporting effects/modes per pair (`supports`). Frozen core untouched. **Proposed schema extensions (documented, not casually invented):** `CAN_FIGHT`, `CHANGES_TYPE_OF`, `SETS_BASE_PT`, `SWITCHES_PT`, `REMOVES_ABILITY_FROM`, `EXCHANGES_CONTROL_OF`/`GAINS_CONTROL_OF`, `PREVENTS_DAMAGE_FROM`. Every Phase-3 census clause is reconciled (`reports/effect_reconciliation.md`, 0 unresolved).

- effects: **117** on 90 faces  · pairs: **5364**

| relation | pairs |  | op | effects |
|---|---:|---|---|---:|
| `ADDS_COUNTER_TO` | 1785 |  | `ADD_COUNTER` | 32 |
| `CAN_DEAL_DAMAGE_TO` | 1120 |  | `MODIFY_PT` | 30 |
| `CAN_DESTROY` | 603 |  | `GRANT_ABILITY` | 20 |
| `CAN_UNTAP` | 461 |  | `DESTROY` | 10 |
| `GRANTS_ABILITY_TO` | 448 |  | `DEAL_DAMAGE` | 10 |
| `MODIFIES_POWER_TOUGHNESS` | 336 |  | `UNTAP` | 5 |
| `CAN_TAP` | 224 |  | `SET_BASE_PT` | 4 |
| `EXCHANGES_CONTROL_OF` | 163 |  | `TAP` | 2 |
| `CAN_FIGHT` | 112 |  | `FIGHT` | 1 |
| `SETS_BASE_PT` | 112 |  | `CHANGE_TYPE` | 1 |
|  |  |  | `CONTROL_CHANGE` | 1 |
|  |  |  | `PREVENT_DAMAGE` | 1 |
