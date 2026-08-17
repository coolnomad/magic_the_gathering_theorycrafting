# Effect-semantics — structured effects (Phase 2a)

Additive `effect_semantics` layer over the frozen reference. Family: **targeted destruction** (`CAN_DESTROY`). Each effect is a validated record (selector + participant + mode + condition + duration + targeting/quantifier + pronoun binding + attempt/zone-transition + Oracle-span provenance); deterministic projection fans each targeted destroy to every eligible card, **aggregating all supporting effects/modes per pair** (`supports`). Frozen core untouched.

- destroy effects: **10** on 10 faces  · CAN_DESTROY pairs: **603**

| card | targeted | mode | selector | eligible cards | token specs |
|---|---|---|---|---:|---:|
| Azog, Moria's Ruin | yes | — | creature | 112 | 9 |
| Bilbo's Deadly Slice | yes | — | creature | 112 | 9 |
| Burn, Burn, Tree and Fern | yes | — | artifact | 18 | 3 |
| Giant's Boulder | yes | — | permanent | 163 | 11 |
| Pinecone Strike | yes | choose_one_or_both#1 | artifact [token] | 0 | 3 |
| Stir Up Trouble | yes | — | creature | 112 | 9 |
| Stone by Sunlight | yes | choose_one#0 | creature [power_ge≥4] | 32 | 2 |
| The Black Arrow | no | — | dragon | 4 | 1 |
| Thorin's Last Stand | yes | choose_one#1 | artifact|enchantment | 38 | 3 |
| Warg Tactics | yes | choose_one#0 | creature [flying] | 12 | 2 |
