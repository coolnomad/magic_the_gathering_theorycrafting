# Effect-semantics — structured effects (Phase 3 object families + Phase 4a/4b participant families)

Additive `effect_semantics` layer over the frozen reference. **ABILITY-scoped** extraction (one clause per (ability, mode); targets never leak across abilities; real `clause_id`), with **same-object variable binding**, **per-operation duration/condition**, explicit self-effects, object-vs-participant separation, comma-OR subtype lists, and empty-object-selector rejection. Object families: destruction, damage (incl. source-power & any-target), counters, power/toughness (mod + set/switch), ability grant/removal, tap/untap, fight, type-change, control-change, and damage-prevention. **Phase-4a participant families:** DRAW and LIFE (gain/lose) — player-directed records that bind to a PARTICIPANT (same-participant binding, e.g. Reverent Howl's draw+lose-life) and are **stochastic/participant-level, so they never fan out to card pairs**; `Pay N life` is a cost, not an effect. **Phase-4b participant families:** DISCARD (hand→graveyard) and MILL (library→graveyard) — likewise participant-level/stochastic with no card-pair fan-out, each carrying `source_zone`/`dest_zone`/`event`; discard distinguishes an activation-cost discard ('Discard a card: …') and a condition ('If you discard …') from a real discard effect. **Phase-4c:** SACRIFICE (battlefield→graveyard) integrates the portable `sac_schema` extractor — reusing its selector/cost parsing — classifying each outlet as a `cost` (activated / additional-cast / kicker) or an `effect` (optional `may`, edict, or conditional self-sacrifice), with the eligibility `card_selector` (self / fodder type / subtype / OR) and no card-pair fan-out; Saga 'Sacrifice after N' self-timers, quoted token abilities, and 'Whenever you sacrifice …' triggers are dispositioned, not extracted. Each effect is a validated record; projection aggregates all supporting effects/modes per pair (`supports`). Frozen core untouched. **Proposed schema extensions (documented, not casually invented):** `CAN_FIGHT`, `CHANGES_TYPE_OF`, `SETS_BASE_PT`, `SWITCHES_PT`, `REMOVES_ABILITY_FROM`, `EXCHANGES_CONTROL_OF`/`GAINS_CONTROL_OF`, `PREVENTS_DAMAGE_FROM`, `DRAWS_CARDS`, `GAINS_LIFE`/`LOSES_LIFE`, `DISCARDS_CARDS`, `MILLS_CARDS`, `SACRIFICES`. Every census clause in scope is reconciled (`reports/effect_reconciliation.md`, 0 unresolved).

- effects: **211** on 132 faces  · pairs: **7950**

| relation | pairs |  | op | effects |
|---|---:|---|---|---:|
| `ADDS_COUNTER_TO` | 1794 |  | `DRAW` | 34 |
| `MODIFIES_POWER_TOUGHNESS` | 1619 |  | `ADD_COUNTER` | 32 |
| `GRANTS_ABILITY_TO` | 1415 |  | `MODIFY_PT` | 31 |
| `CAN_DEAL_DAMAGE_TO` | 1120 |  | `SACRIFICE` | 22 |
| `CAN_DESTROY` | 603 |  | `GRANT_ABILITY` | 20 |
| `CAN_UNTAP` | 461 |  | `DISCARD` | 11 |
| `CHANGES_TYPE_OF` | 225 |  | `GAIN_LIFE` | 10 |
| `CAN_TAP` | 224 |  | `DESTROY` | 10 |
| `EXCHANGES_CONTROL_OF` | 150 |  | `DEAL_DAMAGE` | 10 |
| `SETS_BASE_PT` | 115 |  | `LOSE_LIFE` | 8 |
| `CAN_FIGHT` | 112 |  | `MILL` | 6 |
| `PREVENTS_DAMAGE_FROM` | 112 |  | `UNTAP` | 5 |
|  |  |  | `SET_BASE_PT` | 4 |
|  |  |  | `CHANGE_TYPE` | 3 |
|  |  |  | `TAP` | 2 |
|  |  |  | `FIGHT` | 1 |
|  |  |  | `CONTROL_CHANGE` | 1 |
|  |  |  | `PREVENT_DAMAGE` | 1 |
