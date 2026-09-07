# Card 002 harmonization sweep

- Ports: 210
- Edges: 2195

## 1. Predicate stability (edges per predicate; low-count predicates likely aliases)

| Predicate | Edges | Faces | Sample cards |
|-----------|-------|-------|--------------|
| **GIFTS** | 1 | 1 | Bilbo's Gambit |
| **PREVENTS_CASTING** | 1 | 1 | Bilbo's Gambit |
| **KICKER_COST** | 1 | 1 | The Eagles Are Coming! |
| **TARGETS** | 1 | 1 | The Eagles Are Coming! |
| **RETURNS_FROM_EXILE** | 1 | 1 | Roads Go Ever, Ever On |
| **DELAYED_TRIGGER** | 1 | 1 | Roads Go Ever, Ever On |
| **REPLACES_ON** | 1 | 1 | An Unexpected Party |
| **EXCHANGES_CONTROL** | 1 | 1 | Burglar's Plot |
| **REMOVES_COUNTERS** | 1 | 1 | Enchanted River's Grasp |
| **REMOVES_ABILITIES** | 1 | 1 | Enchanted River's Grasp |
| **SHUFFLES_INTO_LIBRARY** | 1 | 1 | Gandalf, Wandering Wizard |
| **CREW** | 1 | 1 | Great Gilded Boat |
| **PREVENTS_DAMAGE** | 1 | 1 | Old Fat Spider Can't See Me |
| **OPPONENT_CHOOSES** | 1 | 1 | Riddles in the Dark |
| **PARTITIONS** | 1 | 1 | Riddles in the Dark |
| **MOVES_TO_LIBRARY** | 1 | 1 | Uneasy Partings |
| **REVEALS_HAND** | 1 | 1 | Down, Down to Goblin-town |
| **YOU_CHOOSE** | 1 | 1 | Down, Down to Goblin-town |
| **CHOOSES_DESIGNATION** | 1 | 1 | Gollum, Riddle Master |
| **MOVES_CARD** | 1 | 1 | Gollum the Abandoned |
| **ALTERNATIVE_COST** | 1 | 1 | Inside Information |
| **ADDITIONAL_COST** | 1 | 1 | Stir Up Trouble |
| **CHANGES_CHARACTERISTICS** | 1 | 1 | Supper for Spiders |
| **ADDS_COMBAT_PHASE** | 1 | 1 | Desert Were-Worm |
| **RESTRICTS_MANA** | 1 | 1 | Desolation of Smaug |
| **EXILES_FACE_DOWN** | 1 | 1 | Flameshape |
| **REORDERS_ZONE** | 1 | 1 | Getaway Barrel |
| **FLASHBACK** | 1 | 1 | Tidings of War |
| **CANNOT_BE_COUNTERED** | 1 | 1 | Gigantic Big Bear |
| **CANNOT_BE_BLOCKED_BY** | 1 | 1 | Old Fat Spider |
| **REVEALS_UNTIL** | 1 | 1 | Part in Friendship |
| **FIGHTS** | 1 | 1 | Troll Negotiations |
| **MOVES_REST** | 1 | 1 | Dáin's Company |
| **REVEALS_AND_TAKES** | 1 | 1 | Dáin's Company |
| **RESTRICTS_BLOCK** | 1 | 1 | Duskwatch Hunter |
| **EXILES_FROM_LIBRARY** | 1 | 1 | The Great Goblin |
| **GRANTS_EXTRA_LAND_PLAY** | 1 | 1 | Thranduil's Company |
| **SETS_TYPE** | 1 | 1 | Tom, Bert, and William |
| **MOVES_CARDS** | 1 | 1 | Gleam of Death |
| **BEHOLDS** | 1 | 1 | Elven Passage |
| **TYPECYCLING** | 1 | 1 | Hobbit Hole |
| **RESTRICTS_ATTACK** | 2 | 2 | Dáin, Lord of the Iron Hills, Chief Warg's Company |
| **CHANGES_TYPE** | 2 | 2 | Great Gilded Boat, Stone by Sunlight |
| **ENCHANTS** | 2 | 2 | Enchanted River's Grasp, Eagle's Rescue |
| **PREVENTS_UNTAP** | 2 | 2 | Enchanted River's Grasp, Bombur, Gentle Dreamer |
| **MOVES_ZONE** | 2 | 1 | Riddles in the Dark |
| **COUNTERS_SPELL** | 2 | 2 | Thranduil's Decree, Sound the Trumpets |
| **DOUBLES_TRIGGER** | 2 | 2 | Bifur, Melodic Rider, Wizard's Staff |
| **REVEALS** | 2 | 2 | Seek the Heart, Getaway Barrel |
| **ADDS_TYPE** | 2 | 2 | Beorn the Fierce, Beorn's Hospitality |
| **SHUFFLES** | 2 | 2 | Seek the Heart, Wood Elves |

→ **51 predicates appear on <3 cards** — inspect for alias-of-something-bigger.

## 2. Field-name stability per predicate

For each predicate, fields that appear on some edges but not others (potential drops).

| Predicate | Field | Faces w/ | Faces w/o | Fraction |
|-----------|-------|---------:|----------:|---------:|
| HAS_KEYWORD | `note` | 44 | 46 | 49% |
| TRIGGERS_ON | `controller` | 30 | 85 | 26% |
| MODIFIES_PT | `target_text` | 26 | 11 | 70% |
| GRANTS | `target` | 25 | 3 | 89% |
| MODIFIES_PT | `class` | 24 | 13 | 65% |
| TRIGGERS_ON | `subject` | 23 | 92 | 20% |
| ADDS_COUNTER | `class` | 21 | 8 | 72% |
| DRAWS | `amount` | 21 | 10 | 68% |
| TAPS | `purpose` | 21 | 3 | 88% |
| TAPS | `subject` | 21 | 3 | 88% |
| CREATES_TOKEN | `token` | 19 | 3 | 86% |
| GRANTS | `target_text` | 19 | 9 | 68% |
| ADDS_COUNTER | `quantity` | 18 | 11 | 62% |
| ADDS_COUNTER | `selector` | 18 | 11 | 62% |
| GRANTS | `class` | 18 | 10 | 64% |
| GRANTS | `duration` | 17 | 11 | 61% |
| MODIFIES_PT | `duration` | 17 | 20 | 46% |
| SACRIFICES | `class` | 17 | 4 | 81% |
| SACRIFICES | `selector` | 17 | 4 | 81% |
| CREATES_TOKEN | `quantity` | 16 | 6 | 73% |
| DEALS_DAMAGE | `amount` | 15 | 1 | 94% |
| DEALS_DAMAGE | `target_text` | 15 | 1 | 94% |
| SACRIFICES | `purpose` | 15 | 6 | 71% |
| ADDS_COUNTER | `conditions` | 13 | 16 | 45% |
| AMASS | `amount` | 13 | 1 | 93% |
| MODIFIES_PT | `power_delta` | 13 | 24 | 35% |
| MODIFIES_PT | `toughness_delta` | 13 | 24 | 35% |
| PRODUCES_MANA | `amount` | 13 | 5 | 72% |
| AMASS | `detail` | 12 | 2 | 86% |
| DEALS_DAMAGE | `selector` | 12 | 4 | 75% |

→ **266 predicate/field pairs** carry the field on some edges and not others — possible descriptor drops or version drift. Top 30 shown.

## 3. Amount canonicalization per predicate

| Predicate | Amount types | Examples |
|-----------|--------------|----------|
| ADDS_COUNTER | mixed | **int** × 9 (1 (Lakeshore Apothecary)); **str** × 2 ("equal to the sacrificed creat (Rhovanion Rampager)) |
| AMASS | mixed | **int** × 11 (1 (Along the Crooked Way)); **str** × 3 ('X' (Azog, Moria's Ruin)) |
| CREATES_TOKEN | mixed | **int** × 4 (1 (The Misty Mountains Cold)); **str** × 1 ('X' (Smaug, Wicked Worm)) |
| DEALS_DAMAGE | mixed | **int** × 11 (5 (Magnificent End)); **str** × 4 ('number of Treasures you contr (Smaug the Magnificent)) |
| DRAWS | mixed | **int** × 19 (1 (Belladonna Took)); **str** × 2 ('one per graveyard with seven  (The Master of Lake-town)) |
| HAS_POWER | mixed | **int** × 111 (2 (Long-Bodied Grey Dog)); **str** × 2 ('*' (Esgaroth Garrison)) |
| HAS_TOUGHNESS | mixed | **int** × 112 (2 (Long-Bodied Grey Dog)); **str** × 1 ('*' (Mirkwood Pathmaker)) |
| MILLS | mixed | **int** × 3 (4 (Speak Secrets)); **str** × 1 ('equal to the amount of life l (The Master of Lake-town)) |

→ Predicates above have `amount` in multiple python types across cards.

## 4. Concept-vs-string endpoint per predicate

| Predicate | concept only | text only | both | neither |
|-----------|-------------:|----------:|-----:|--------:|
| ATTACHES_TO | 0 | 13 | 0 | 8 |
| DEALS_DAMAGE | 0 | 15 | 0 | 1 |
| DISCARDS | 0 | 1 | 0 | 14 |
| DRAWS | 0 | 4 | 0 | 28 |
| EXILES | 0 | 9 | 0 | 2 |
| GAINS_LIFE | 0 | 2 | 0 | 7 |
| GRANTS | 7 | 1 | 22 | 3 |
| GRANTS_PERMISSION | 0 | 2 | 0 | 8 |
| LOOKS_AT | 0 | 1 | 0 | 4 |
| LOSES_LIFE | 0 | 3 | 0 | 4 |
| MILLS | 0 | 2 | 0 | 4 |
| MODIFIES_PT | 0 | 27 | 0 | 11 |
| MOVES_TO_HAND | 0 | 3 | 0 | 1 |
| REPLACES | 0 | 2 | 0 | 5 |
| RETURNS | 0 | 5 | 0 | 1 |
| RETURNS_FROM_GRAVEYARD | 0 | 2 | 0 | 1 |
| SACRIFICES | 0 | 2 | 0 | 21 |
| SETS_PT | 0 | 3 | 0 | 1 |
| TAPS | 0 | 3 | 0 | 29 |
| TUTORS | 0 | 3 | 0 | 9 |

→ **20 predicates use more than one endpoint shape** — the same predicate points at a concept sometimes and a raw string other times.

## 5. Keyword coverage

| Keyword | In oracle | HAS_KEYWORD | Missing |
|---------|----------:|------------:|--------:|
| flying | 16 | 13 | 3 |
| vigilance | 10 | 10 | 0 |
| trample | 13 | 13 | 0 |
| reach | 10 | 10 | 0 |
| haste | 6 | 6 | 0 |
| flash | 8 | 7 | 1 |
| lifelink | 4 | 4 | 0 |
| menace | 6 | 6 | 0 |
| deathtouch | 4 | 4 | 0 |
| first strike | 4 | 4 | 0 |
| double strike | 2 | 2 | 0 |
| hexproof | 5 | 5 | 0 |
| indestructible | 2 | 2 | 0 |
| prowess | 1 | 1 | 0 |
| flashback | 3 | 3 | 0 |
| kicker | 1 | 1 | 0 |
| landfall | 10 | 10 | 0 |
| ferocious | 6 | 6 | 0 |
| threshold | 1 | 1 | 0 |
| ward | 4 | 2 | 2 |
| storied | 9 | 2 | 7 |
| equip | 16 | 1 | 15 |
| enchant | 2 | 1 | 1 |
| recruit | 10 | 3 | 7 |
| amass | 14 | 0 | 14 |

Missing coverage (card names):
- **flying**: The Eagles Are Coming!, The Misty Mountains Cold, Warg Tactics
- **flash**: Radagast of Rhosgobel
- **ward**: Gandalf, Wandering Wizard, Lake-town Mariners
- **storied**: Dáin, Lord of the Iron Hills, Fíli the Pathfinder, Kíli the Resourceful, Balin, Loremaster, Bombur, Gentle Dreamer, Óin the Brave, Bifur, Melodic Rider
- **equip**: Iron Hills Blacksmith, Kíli the Resourceful, Wizard's Staff, Crude Bent Blade, Dáin Ironfoot, Dwarven Mauler, Ragged Short Spear, Goblin Plate Mail ...
- **enchant**: Enchanted River's Grasp
- **recruit**: Celebrate the Mountain-king, Esgaroth Garrison, Lake-town Lookout, The Mountain-king's Return, The Queen of Dale, Sound the Trumpets, Patient Instructor
- **amass**: Along the Crooked Way, Azog, Moria's Ruin, Down, Down to Goblin-town, Gathering of Darkness, Clap! Snap!, Rage into the Valley, Rhovanion Rampager, Bothersome Noisemaker ...

## 6. Cost purpose vocabulary

| Purpose | Count |
|---------|------:|
| `cast` | 198 |
| `activation` | 99 |
| **missing** | 7 |

Missing-purpose cost edges (first 15):
- Crude Bent Blade  →  SACRIFICES
- Rhovanion Rampager  →  SACRIFICES
- The Sackville-Bagginses  →  SACRIFICES
- Stir Up Trouble  →  ADDITIONAL_COST
- Last Light of Durin's Day  →  SACRIFICES
- The Misty Mountains Cold  →  SACRIFICES
- Bolg of the North  →  SACRIFICES

## 7. Selector shape for target-scoped edges

- Edges with target/each/all phrases in target_text: 111
- With `selector` field: 102
- Missing `selector`: 9

Missing-selector edges (first 15):
- **Belladonna Took** ADDS_COUNTER target_text=`each creature you control`
- **The Eagles Are Coming!** RETURNS_TO_HAND target_text=`each chosen creature`
- **Great Ugly-Looking Goblin** GRANTS target_text=`each creature you control with a +1/+1 counter on it`
- **Balin, Loremaster** DEALS_DAMAGE target_text=`each opponent`
- **Dáin Ironfoot** GRANTS target_text=`each equipped attacking creature`
- **Desolation of Smaug** DEALS_DAMAGE target_text=`each non-Dragon creature`
- **Easy Pickings** DEALS_DAMAGE target_text=`each creature your opponents control`
- **Wilderland Scrounger** ADDS_COUNTER target_text=`each creature you control`
- **Dwalin, Weaponmaster** ADDS_COUNTER target_text=`each Equipment you control`

---

## Summary priorities

1. **51** low-count predicates to fold into their normalized cousins.
2. **266** predicate/field pairs where a descriptor is present on some cards and absent on others of the same predicate.
3. **8** predicates with heterogenous `amount` types (int vs str).
4. **20** predicates mixing concept-target and text-target endpoints.
5. **50** keyword-involvement misses across the set.
6. **7** cost edges missing `purpose` field.
7. **9** target-scoped edges missing structured `selector`.
