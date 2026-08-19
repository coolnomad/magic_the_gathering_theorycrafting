# Effect-semantics — structured effects (Phase 3 object families + Phase 4a-4e families)

Additive `effect_semantics` layer over the frozen reference. **ABILITY-scoped** extraction (one clause per (ability, mode); targets never leak across abilities; real `clause_id`), with **same-object variable binding**, **per-operation duration/condition**, explicit self-effects, object-vs-participant separation, comma-OR subtype lists, and empty-object-selector rejection. Object families: destruction, damage (incl. source-power & any-target), counters, power/toughness (mod + set/switch), ability grant/removal, tap/untap, fight, type-change, control-change, and damage-prevention. **Phase-4a participant families:** DRAW and LIFE (gain/lose) — player-directed records that bind to a PARTICIPANT (same-participant binding, e.g. Reverent Howl's draw+lose-life) and are **stochastic/participant-level, so they never fan out to card pairs**; `Pay N life` is a cost, not an effect. **Phase-4b participant families:** DISCARD (hand→graveyard) and MILL (library→graveyard) — likewise participant-level/stochastic with no card-pair fan-out, each carrying `source_zone`/`dest_zone`/`event`; discard distinguishes an activation-cost discard ('Discard a card: …') and a condition ('If you discard …') from a real discard effect. **Phase-4c:** SACRIFICE (battlefield→graveyard) integrates the portable `sac_schema` extractor — reusing its selector/cost parsing — classifying each outlet as a `cost` (activated / additional-cast / kicker) or an `effect` (optional `may`, edict, or conditional self-sacrifice), with the eligibility `card_selector` (self / fodder type / subtype / OR) and no card-pair fan-out; Saga 'Sacrifice after N' self-timers, quoted token abilities, and 'Whenever you sacrifice …' triggers are dispositioned, not extracted. **Phase-4d:** SEARCH/tutor is the DETERMINISTIC family — per the spec it 'projects to eligible choices', so the searched-for card selector fans out to every eligible HOB card as a `SEARCHES_FOR` relation (source `library`/`hand_and_library`, destination hand / battlefield(±tapped) / exile / library_top, with quantity, reveal, shuffle, and the searcher participant — Settle the Wreckage binds `target_player` + a variable count); cycling-reminder tutors are keyword-layer (not extracted). **Phase-4e:** RETURN/recursion (bounce + reanimation) is object-directed — it PROJECTS to eligible objects (`CAN_RETURN`), moving a card graveyard→hand/battlefield (reanimation/recursion), battlefield→hand (bounce), or source→source (self-return); blink (exile-and-return) and stack-object spell-bounce are dispositioned pending the exile slice. **Phase-4f:** EXILE — stochastic top-library exile (participant-level, no fan-out, with a play-permission) and targeted/mass permanent/card exile (object-directed → `CAN_EXILE`, source→exile); blink is completed (its RETURN binds to the exiled objects) and Adventure/Flashback reminders + death/counter `exile … instead` replacements are dispositioned. Each effect is a validated record; projection aggregates all supporting effects/modes per pair (`supports`). Frozen core untouched. **Proposed schema extensions (documented, not casually invented):** `CAN_FIGHT`, `CHANGES_TYPE_OF`, `SETS_BASE_PT`, `SWITCHES_PT`, `REMOVES_ABILITY_FROM`, `EXCHANGES_CONTROL_OF`/`GAINS_CONTROL_OF`, `PREVENTS_DAMAGE_FROM`, `DRAWS_CARDS`, `GAINS_LIFE`/`LOSES_LIFE`, `DISCARDS_CARDS`, `MILLS_CARDS`, `SACRIFICES`, `SEARCHES_FOR`, `CAN_RETURN`, `CAN_EXILE`, `EXILES`. Every census clause in scope is reconciled (`reports/effect_reconciliation.md`, 0 unresolved).

- effects: **244** on 144 faces  · pairs: **9032**

| relation | pairs |  | op | effects |
|---|---:|---|---|---:|
| `ADDS_COUNTER_TO` | 1794 |  | `DRAW` | 34 |
| `MODIFIES_POWER_TOUGHNESS` | 1619 |  | `ADD_COUNTER` | 32 |
| `GRANTS_ABILITY_TO` | 1415 |  | `MODIFY_PT` | 31 |
| `CAN_DEAL_DAMAGE_TO` | 1120 |  | `SACRIFICE` | 22 |
| `CAN_DESTROY` | 603 |  | `GRANT_ABILITY` | 20 |
| `CAN_EXILE` | 537 |  | `RETURN` | 12 |
| `CAN_UNTAP` | 461 |  | `SEARCH` | 11 |
| `CAN_RETURN` | 456 |  | `DISCARD` | 11 |
| `CHANGES_TYPE_OF` | 225 |  | `GAIN_LIFE` | 10 |
| `CAN_TAP` | 224 |  | `EXILE` | 10 |
| `EXCHANGES_CONTROL_OF` | 150 |  | `DESTROY` | 10 |
| `SETS_BASE_PT` | 115 |  | `DEAL_DAMAGE` | 10 |
| `CAN_FIGHT` | 112 |  | `LOSE_LIFE` | 8 |
| `PREVENTS_DAMAGE_FROM` | 112 |  | `MILL` | 6 |
| `SEARCHES_FOR` | 89 |  | `UNTAP` | 5 |
|  |  |  | `SET_BASE_PT` | 4 |
|  |  |  | `CHANGE_TYPE` | 3 |
|  |  |  | `TAP` | 2 |
|  |  |  | `FIGHT` | 1 |
|  |  |  | `CONTROL_CHANGE` | 1 |
|  |  |  | `PREVENT_DAMAGE` | 1 |
