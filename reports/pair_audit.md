# HOB Phase 5 Part 2 — Pairwise LLM Audit (extractor + critic)

- **extractor verdicts**: 94
- **accepted (critic-confirmed, grounded, novel)**: 11
- **critic-rejected**: 5
- **duplicate of mechanical**: 1
- **ungrounded**: 0
- **NO_RELATION**: 77

## Accepted augmented relations (origin: llm_audit)

- **Great Ugly-Looking Goblin // Clap! Snap! → The Great Goblin** [ENABLES_TRIGGER/semantic] via `counter:+1/+1`
- **Gollum, Riddle Master → The Master of Lake-town** [ENABLES_TRIGGER/grounded] via `resource:card`
- **Reverent Howl → The Master of Lake-town** [ENABLES_TRIGGER/semantic] via `resource:life`
- **Rage into the Valley → The Master of Lake-town** [ENABLES_TRIGGER/semantic] via `resource:life`
- **Gandalf, Wandering Wizard → Elrond, Moon-Reader** [ENABLES_TRIGGER/grounded] via `resource:card-in-hand`
- **Bard, King of Dale → Beorn the Fierce** [AMPLIFIES_EFFECT/grounded] via `event:draw`
- **Bard, King of Dale → The Chief Warg** [AMPLIFIES_EFFECT/grounded] via `event:draw`
- **Bard, King of Dale → Old Fat Spider** [AMPLIFIES_EFFECT/grounded] via `event:draw`
- **The Sackville-Bagginses → The Master of Lake-town** [ENABLES_TRIGGER/semantic] via `resource:life`
