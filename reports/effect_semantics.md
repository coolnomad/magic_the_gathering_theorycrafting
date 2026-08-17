# Effect-semantics — structured effects (Phase 3: targeted-object families)

Additive `effect_semantics` layer over the frozen reference. Families: destruction, damage, counters, power/toughness, ability grants, tap/untap, fight, and type-change. Each effect is a validated record (selector + participant + mode + condition + duration + targeting/quantifier + **same-object variable binding** + Oracle-span provenance); deterministic projection fans each targeted effect to every eligible card, **aggregating all supporting effects/modes per pair** (`supports`). Frozen core untouched. Two predicates are proposed schema extensions (documented): `CAN_FIGHT`, `CHANGES_TYPE_OF`.

- effects: **69** on 52 faces  · pairs: **6098**

| relation | pairs |  | op | effects |
|---|---:|---|---|---:|
| `ADDS_COUNTER_TO` | 1424 |  | `ADD_COUNTER` | 19 |
| `GRANTS_ABILITY_TO` | 1362 |  | `MODIFY_PT` | 14 |
| `MODIFIES_POWER_TOUGHNESS` | 1253 |  | `GRANT_ABILITY` | 12 |
| `CAN_DEAL_DAMAGE_TO` | 672 |  | `DESTROY` | 10 |
| `CAN_DESTROY` | 603 |  | `DEAL_DAMAGE` | 7 |
| `CAN_UNTAP` | 336 |  | `UNTAP` | 3 |
| `CAN_TAP` | 224 |  | `TAP` | 2 |
| `CAN_FIGHT` | 112 |  | `FIGHT` | 1 |
| `CHANGES_TYPE_OF` | 112 |  | `CHANGE_TYPE` | 1 |
