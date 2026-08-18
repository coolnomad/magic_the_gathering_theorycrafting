# Effect-semantics — structured effects (Phase 3 object families + Phase 4a/4b participant families)

Additive `effect_semantics` layer over the frozen reference. **ABILITY-scoped** extraction (one clause per (ability, mode); targets never leak across abilities; real `clause_id`), with **same-object variable binding**, **per-operation duration/condition**, explicit self-effects, object-vs-participant separation, comma-OR subtype lists, and empty-object-selector rejection. Object families: destruction, damage (incl. source-power & any-target), counters, power/toughness (mod + set/switch), ability grant/removal, tap/untap, fight, type-change, control-change, and damage-prevention. **Phase-4a participant families:** DRAW and LIFE (gain/lose) — player-directed records that bind to a PARTICIPANT (same-participant binding, e.g. Reverent Howl's draw+lose-life) and are **stochastic/participant-level, so they never fan out to card pairs**; `Pay N life` is a cost, not an effect. **Phase-4b participant families:** DISCARD (hand→graveyard) and MILL (library→graveyard) — likewise participant-level/stochastic with no card-pair fan-out, each carrying `source_zone`/`dest_zone`/`event`; discard distinguishes an activation-cost discard ('Discard a card: …') and a condition ('If you discard …') from a real discard effect. Each effect is a validated record; projection aggregates all supporting effects/modes per pair (`supports`). Frozen core untouched. **Proposed schema extensions (documented, not casually invented):** `CAN_FIGHT`, `CHANGES_TYPE_OF`, `SETS_BASE_PT`, `SWITCHES_PT`, `REMOVES_ABILITY_FROM`, `EXCHANGES_CONTROL_OF`/`GAINS_CONTROL_OF`, `PREVENTS_DAMAGE_FROM`, `DRAWS_CARDS`, `GAINS_LIFE`/`LOSES_LIFE`, `DISCARDS_CARDS`, `MILLS_CARDS`. Every census clause in scope is reconciled (`reports/effect_reconciliation.md`, 0 unresolved).

- effects: **189** on 126 faces  · pairs: **7950**

| relation | pairs |  | op | effects |
|---|---:|---|---|---:|
| `ADDS_COUNTER_TO` | 1794 |  | `DRAW` | 34 |
| `MODIFIES_POWER_TOUGHNESS` | 1619 |  | `ADD_COUNTER` | 32 |
| `GRANTS_ABILITY_TO` | 1415 |  | `MODIFY_PT` | 31 |
| `CAN_DEAL_DAMAGE_TO` | 1120 |  | `GRANT_ABILITY` | 20 |
| `CAN_DESTROY` | 603 |  | `DISCARD` | 11 |
| `CAN_UNTAP` | 461 |  | `GAIN_LIFE` | 10 |
| `CHANGES_TYPE_OF` | 225 |  | `DESTROY` | 10 |
| `CAN_TAP` | 224 |  | `DEAL_DAMAGE` | 10 |
| `EXCHANGES_CONTROL_OF` | 150 |  | `LOSE_LIFE` | 8 |
| `SETS_BASE_PT` | 115 |  | `MILL` | 6 |
| `CAN_FIGHT` | 112 |  | `UNTAP` | 5 |
| `PREVENTS_DAMAGE_FROM` | 112 |  | `SET_BASE_PT` | 4 |
|  |  |  | `CHANGE_TYPE` | 3 |
|  |  |  | `TAP` | 2 |
|  |  |  | `FIGHT` | 1 |
|  |  |  | `CONTROL_CHANGE` | 1 |
|  |  |  | `PREVENT_DAMAGE` | 1 |
