# Effect-semantics — (clause_id, family) reconciliation (Phase 3 + Phase 4a draw/life + 4b discard/mill + 4c sacrifice + 4d search + 4e return + 4f exile)

Every `(clause_id, family)` carrying a Phase-3 object family or a Phase-4 participant family (draw, life, discard, mill) is EXTRACTED or DISPOSITIONED. Deferred / non-executable dispositions (life-payment / discard / cycling costs, draw/life/mill *triggers*, recruit) are counted separately from `unresolved`.

- (clause, family) pairs: **370**  · extracted: **240**  · deferred/nonexecutable: **4**  · unresolved: **0**

| disposition | (clause,family) |
|---|---:|
| extracted | 240 |
| reminder_text (family appears only in reminder text) | 58 |
| attachment_static (equip/aura layer) | 22 |
| amass (counters on an Army token — token/mechanism layer) | 13 |
| participant_effect (Phase 4: player-directed) | 5 |
| draw_trigger (a trigger event/condition, not a draw effect) | 5 |
| life_payment_cost (a cost, not a life effect) | 4 |
| death_replacement (exile-instead-of-dying — a replacement effect) | 3 |
| combat_damage_trigger (a trigger, not a damage effect) | 2 |
| granted_ability (quoted ability on another/created object — deferred execution) | 2 |
| discard_cost (a cost, not a discard effect) | 2 |
| grants_nonkeyword_ability — DEFERRED | 2 |
| counter_as_condition (census false positive — a counter reference, not an add) | 1 |
| search_destination (the searched cards are exiled — see the SEARCH record) | 1 |
| play_from_graveyard (flashback-style exile after casting from graveyard — mechanism/deferred) | 1 |
| source_power_bound_damage — DEFERRED | 1 |
| life_change_trigger (a trigger event, not a life effect) | 1 |
| restriction (doesn't-untap — restriction family) | 1 |
| attachment (equip layer — not a type change) | 1 |
| divided_damage — DEFERRED | 1 |
| counter_replacement (exile-instead-of-graveyard on a countered spell — replacement) | 1 |
| sacrifice_trigger (a trigger event, not a sacrifice effect) | 1 |
| spell_bounce (a stack-object bounce, not a card-identity move — deferred) | 1 |
| stochastic_look_exile (look-then-exile from library — deferred) | 1 |
