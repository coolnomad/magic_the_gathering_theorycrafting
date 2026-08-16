# HOB Phase 5 Part 2 — Pairwise LLM Audit (extractor + critic, typed paths)

- **coverage**: 142/142 candidates audited
- **accepted**: 5 verdicts → 3 augmented relations (deduped)
- **graph-repair**: 10 verdicts → 7 queue entries (deduped, unordered)
- **critic disagreement**: 12
- **duplicate of mechanical**: 1
- **ungrounded**: 0
- **NO_RELATION**: 114

## Accepted faithful typed paths (origin: llm_audit, direction mechanically proven)

- **Bard, King of Dale → Beorn the Fierce** [AMPLIFIES_EFFECT] via `event:draw` — REPLACES → AMPLIFIES_EFFECT → CAUSES  (conditions: cond:face:30ca8e92-5955-46a1-86c1-094a873f518f:0:c699f116e)
- **Bard, King of Dale → The Chief Warg** [AMPLIFIES_EFFECT] via `event:draw` — REPLACES → AMPLIFIES_EFFECT → CAUSES
- **Bard, King of Dale → Old Fat Spider** [AMPLIFIES_EFFECT] via `event:draw` — REPLACES → AMPLIFIES_EFFECT → CAUSES  (conditions: cond:face:8790f842-e842-4bed-adf4-5b3cc5fd68a9:0:c0cb0edbf)

## Graph-repair queue (unordered pair; proposed direction; needs a primitive path)

- **Head of the Hunt — Chief Warg's Company** [SUPPLIES_RESOURCE] candidate_concept `token:wolf` → add **Resource** (canonicalize the shared resource (token:wolf) so producer feeds consumer); proposed enabler: Head of the Hunt [proposed]
- **Great Ugly-Looking Goblin // Clap! Snap! — The Great Goblin** [ENABLES_TRIGGER] candidate_concept `counter:+1/+1` → add **Event** (add Event:counter-placed + TRIGGERS to the beneficiary ability); proposed enabler: Great Ugly-Looking Goblin // Clap! Snap! [proposed]
- **Elrond, Moon-Reader — Gandalf, Wandering Wizard** [ENABLES_TRIGGER] candidate_concept `resource:card-in-hand` → add **Event** (add Event:creature-ability-activated or card-drawn + TRIGGERS); proposed enabler: Gandalf, Wandering Wizard [proposed]
- **Gollum, Riddle Master — The Master of Lake-town** [ENABLES_TRIGGER] candidate_concept `resource:card` → add **Event** (add Event:creature-ability-activated or card-drawn + TRIGGERS); proposed enabler: Gollum, Riddle Master [proposed]
- **Reverent Howl — The Master of Lake-town** [ENABLES_TRIGGER] candidate_concept `resource:life` → add **Event** (add Event:life-lost + TRIGGERS to the beneficiary ability); proposed enabler: Reverent Howl [proposed]
- **The Master of Lake-town — Rage into the Valley** [ENABLES_TRIGGER] candidate_concept `resource:life` → add **Event** (add Event:life-lost + TRIGGERS to the beneficiary ability); proposed enabler: Rage into the Valley [proposed]
- **The Master of Lake-town — The Sackville-Bagginses** [ENABLES_TRIGGER] candidate_concept `resource:life` → add **Event** (add Event:life-lost + TRIGGERS to the beneficiary ability); proposed enabler: The Sackville-Bagginses [proposed]
