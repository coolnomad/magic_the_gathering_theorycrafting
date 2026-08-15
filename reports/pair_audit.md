# HOB Phase 5 Part 2 — Pairwise LLM Audit (high-signal pass)

- **verdicts**: 44
- **accepted relations (grounded)**: 9
- **rejected (ungrounded)**: 0
- **NO_RELATION**: 35

## Accepted relations by type

- SUPPLIES_RESOURCE: 4
- AMPLIFIES_EFFECT: 3
- ENABLES_TRIGGER: 2

## Accepted relations

- **Smaug, Wicked Worm → Smaug the Magnificent** [SUPPLIES_RESOURCE/high] — Source creates Treasure tokens that the target's attack trigger counts to determine its damage.
- **Thranduil, the Elvenking → Thranduil, Sindarin Liege // Silvan Rally** [ENABLES_TRIGGER/high] — The target is a legendary Elf whose entering the battlefield triggers the source's draw-two-discard-one ability.
- **The Great Goblin → Great Ugly-Looking Goblin // Clap! Snap!** [ENABLES_TRIGGER/high] — Target's Amass Goblins 2 puts +1/+1 counters on a Goblin Army you control, which triggers the source's deal-2-damage ability.
- **Smaug the Magnificent → Smaug, Wicked Worm** [SUPPLIES_RESOURCE/medium] — The source repeatedly creates Treasure tokens whose sacrifice supplies the Treasure mana that specifically triggers the target's draw-and-lose-life ability.
- **Desolation of Smaug → Smaug the Magnificent** [SUPPLIES_RESOURCE/medium] — Desolation of Smaug produces mana usable only to cast Dragon spells, and the target Smaug the Magnificent is a Dragon creature spell that mana can pay for; its non-Dragon damage also spares the Dragon.
- **Desolation of Smaug → Smaug, the Great Calamity // Spew Flame** [SUPPLIES_RESOURCE/medium] — Desolation of Smaug adds mana spendable only on Dragon spells, and the target's front face Smaug, the Great Calamity is a Dragon creature spell that mana can cast.
- **Bard, King of Dale → Beorn the Fierce** [AMPLIFIES_EFFECT/high] — Bard's draw-replacement turns Beorn's 'draw two cards' payoff into four cards.
- **Bard, King of Dale → The Chief Warg** [AMPLIFIES_EFFECT/high] — Bard's draw-replacement doubles The Chief Warg's Ferocious 'you draw a card' into two cards.
- **Bard, King of Dale → Old Fat Spider** [AMPLIFIES_EFFECT/high] — Bard's draw-replacement turns Old Fat Spider's targeted 'draw a card' trigger into two cards.
