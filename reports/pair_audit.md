# HOB Phase 5 Part 2 — Pairwise LLM Audit (extractor + critic, typed paths)

- **coverage**: 142/142 candidates audited (0 shared-vocabulary candidates unaudited)
- **accepted faithful typed paths (origin: llm_audit)**: 5
- **routed to graph-repair queue**: 11
- **critic disagreement**: 11
- **duplicate of mechanical**: 1
- **ungrounded**: 0
- **NO_RELATION**: 114

## Accepted faithful typed paths (origin: llm_audit)

- **Bard, King of Dale → Beorn the Fierce** [AMPLIFIES_EFFECT] via `event:draw` — REPLACES → AMPLIFIES_EFFECT → CAUSES
- **Bard, King of Dale → The Chief Warg** [AMPLIFIES_EFFECT] via `event:draw` — REPLACES → AMPLIFIES_EFFECT → CAUSES
- **Bard, King of Dale → Old Fat Spider** [AMPLIFIES_EFFECT] via `event:draw` — REPLACES → AMPLIFIES_EFFECT → CAUSES

## Graph-repair queue (credible relations lacking a primitive path)

- **Head of the Hunt → Chief Warg's Company** [SUPPLIES_RESOURCE] via `token:wolf` — needs: canonicalize the shared resource node so producer feeds consumer
- **Elrond, Moon-Reader → Gandalf, Wandering Wizard** [ENABLES_TRIGGER] via `resource:card-in-hand` — needs: add/canonicalize the intermediate event (life-lost / counter-placed / creature-ability-activated) and a TRIGGERS edge to the beneficiary ability
- **Gollum, Riddle Master → The Master of Lake-town** [ENABLES_TRIGGER] via `resource:card` — needs: add/canonicalize the intermediate event (life-lost / counter-placed / creature-ability-activated) and a TRIGGERS edge to the beneficiary ability
- **The Great Goblin → Great Ugly-Looking Goblin // Clap! Snap!** [ENABLES_TRIGGER] via `counter:+1/+1` — needs: add/canonicalize the intermediate event (life-lost / counter-placed / creature-ability-activated) and a TRIGGERS edge to the beneficiary ability
- **Reverent Howl → The Master of Lake-town** [ENABLES_TRIGGER] via `resource:life` — needs: add/canonicalize the intermediate event (life-lost / counter-placed / creature-ability-activated) and a TRIGGERS edge to the beneficiary ability
- **The Master of Lake-town → Rage into the Valley** [ENABLES_TRIGGER] via `resource:life` — needs: add/canonicalize the intermediate event (life-lost / counter-placed / creature-ability-activated) and a TRIGGERS edge to the beneficiary ability
- **The Master of Lake-town → The Sackville-Bagginses** [ENABLES_TRIGGER] via `resource:life` — needs: add/canonicalize the intermediate event (life-lost / counter-placed / creature-ability-activated) and a TRIGGERS edge to the beneficiary ability
- **Thranduil, Sindarin Liege // Silvan Rally → Down in the Valley** [AMPLIFIES_EFFECT] via `token:elf` — needs: canonicalize the shared modified event/resource node
