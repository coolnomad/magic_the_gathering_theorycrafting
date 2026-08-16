# HOB Phase 5 — Graph Repair + Reprojection

- **reprojected as faithful typed paths**: 8
- **still unrepaired**: 0
- **all path edges resolve (real Phase 4 or repair layer)**: True

## Reprojected relations (origin: graph_repair)

- **Head of the Hunt → Chief Warg's Company** [SUPPLIES_RESOURCE] via `token:wolf` — CREATES_OBJECT → REQUIRES (repair edges: 1)
- **Great Ugly-Looking Goblin // Clap! Snap! → The Great Goblin** [ENABLES_TRIGGER] via `event:counters-placed` — CAUSES → TRIGGERS (repair edges: 1)
- **Gollum, Riddle Master → The Master of Lake-town** [ENABLES_TRIGGER] via `event:player-loses-life` — CAUSES → TRIGGERS (repair edges: 1)
- **Reverent Howl → The Master of Lake-town** [ENABLES_TRIGGER] via `event:player-loses-life` — CAUSES → TRIGGERS (repair edges: 1)
- **Rage into the Valley → The Master of Lake-town** [ENABLES_TRIGGER] via `event:player-loses-life` — CAUSES → TRIGGERS (repair edges: 1)
- **Gandalf, Wandering Wizard → Elrond, Moon-Reader** [ENABLES_TRIGGER] via `event:activate-creature-ability` — CAUSES → TRIGGERS (repair edges: 1)
- **The Sackville-Bagginses → The Master of Lake-town** [ENABLES_TRIGGER] via `event:player-loses-life` — CAUSES → TRIGGERS (repair edges: 1)
- **Thranduil, Sindarin Liege // Silvan Rally → Down in the Valley** [AMPLIFIES_EFFECT] via `obj:subtype:elf` — MODIFIES → HAS_TYPE → CREATES_OBJECT (repair edges: 1)
