# HOB gold-set — HUMAN audit RESULT

**Adjudicator:** the project owner (external human). **Instrument:** `reports/human_audit_worksheet.md`
(128 gold-set items, 9 strata), each read against printed Oracle text + the cited CR.
**Verdicts:** `data/review/human_audit_verdicts.jsonl`.

## Headline

| Verdict | Count |
|---|---:|
| correct | **116** |
| wrong | **10** |
| unsure (nuanced — partially correct) | **2** |
| **total** | **128** |

No asserted relation was found to be **directionally** backwards, and no wrong-assertion was found in
the Adventures, Recruit, Sagas, Storied, Replacement, or multi-token strata. All 10 "wrong" verdicts
are **missed relations (false negatives)** or **loose edge typing**, plus one false self-reflexive
edge. Two prior sub-agent concerns were **rejected by the human** (Óin #125, and the Belladonna nulls
turned out to hide P/T modifications, not the token trigger the sub-agent guessed — except Clap! Snap!).

## Findings by class (verbatim owner notes)

### Class 1 — `SUPPLIES_RESOURCE` used where the relation is a TRIGGER, not consumption
The owner's governing principle (#54): *"There's a difference between a card **consuming** something
… and being **triggered**. Kíli is listening for a dwarf entering event but doesn't consume the dwarf.
… we'll need to identify triggers vs costs and change the edge types of the triggers."*
- **#58 Plunder the Trollshaws → Uncover the Moon-Letters** — **wrong**: *"remove the SUPPLIES_RESOURCE
  edge here. Casting the spell triggers the enchantment. It doesn't consume the spell."*
- **#54 Nori → Kíli the Resourceful** — *correct but* *"ENABLES_TRIGGER is a better type."*
→ **Disposition:** reclassify `SUPPLIES_RESOURCE` edges whose target is *triggered by* (not *consuming*)
the source into `ENABLES_TRIGGER`. A mechanism-layer edge-typing pass (additive). Scope: enumerate all
`SUPPLIES_RESOURCE` edges, split trigger vs cost.

### Class 2 — Missed relations (false negatives): three mechanism families
- **Anthem P/T modification** — The Arkenstone (*"Creatures you control get +1/+1"*) modifies every
  creature its controller controls. Missed `MODIFIES` edges: **#66 / #72** (↔ Rhovanion Rampager),
  **#74** (→ Tom, Bert, and William).
- **Targeted +1/+1 counter / buff** — Meager Meal (*"+1/+1 counter on target creature"*), Lake-town
  Toymaker, etc. modify a target creature's P/T (an `ADDS_COUNTER` / `MODIFIES` operation). Missed:
  **#67 / #68** (Belladonna Took), **#71** (Head of the Hunt), **#75** (Lake-town Toymaker → Belladonna).
- **Token creation → token-enters trigger** — **#82 Clap! Snap!** (*"creates a token if no token
  already exists, this will trigger Belladonna Took."*). This is the token-enters class.
- Also **#74**: Seek the Heart (tutor) *"can find Tom … the creature is a resource supplied to the
  Seek the Heart side"* — a tutor `SUPPLIES_RESOURCE`/eligibility relation, in addition to the anthem.
→ **Disposition:** additive completeness gaps — three new relation classes (anthem `MODIFIES`, targeted
`ADDS_COUNTER`, token-creation → `ENABLES_TRIGGER`). A scoped repair round (like the pt4 rounds).

### Class 3 — False self-reflexive edge (self_pairs stratum)
- **#111 Head of the Hunt** — **wrong**: *"doesn't trigger itself. It requires the creature to be
  under an opponent's control when it dies."* The reflexive self-edge is a false positive.
→ **Disposition:** locate the source edge; if it lives in the FROZEN mechanical projection, removing it
is a sanctioned corrective re-freeze (needs go-ahead).

### Class 4 — Nuanced self-pairs (unsure → correct-in-part; the reflexive framing is coarse)
- **#114 Woodland Weavemaster** — its P/T triggered ability needs a *separate* Elf to enter (a second
  copy won't trigger itself on entering), *but its mana ability is self-referential* → correct for the
  mana ability, imprecise for the P/T ability.
- **#115 Uncover the Moon-Letters** — triggered by *another* spell cast; a second copy triggers the
  first → the self-pair is correct in that sense.
→ **Disposition:** the `self_pairs` reflexivity label conflates genuinely-reflexive statics with
"triggers on a copy." Precision note; low priority.

## Confirmations worth keeping (owner-verified positives)
- **#125 Óin the Brave** — *"Legendary creatures qualify for their own storied gates."* (sub-agent's
  spurious-storied concern **rejected**.)
- **#118 Ori, Keeper of Songs** — *"Ori satisfies his own storied gate."*
- **#112 Balin / #113 Smaug / #116 Dori** — genuine reflexive self-effects, confirmed.
- **#69, #76, #84** — true nulls (no token payoff to wire).
- **#77, #78, #79, #80** — Rhovanion null pairs confirmed; **#80 Gnashing of Teeth** has a replacement
  effect that *prevents* the dies-trigger — correctly null.

## Resolution — additive `audit_repair` layer (`src/hobkg/audit_repair.py`)

All corrections were applied as a new additive layer that **does not touch the frozen core graph**
(nodes/edges/conditions stay byte-stable; a test asserts it). Each corrected mechanism is represented
**once at the object-class level** (a canonical class edge grounded in the responsible card's Oracle
text), and every eligible card pair is **derived mechanically from card characteristics** — no audited
pair is hard-coded. Derived pairs are tagged `generic:true` / `origin:audit_repair` and land in their
own `audit_repair` column of `pair_index.jsonl`, so the object-class expansions are **filterable**.

- **Class 1** — retype: `kili-tribal-entry` adds `ENABLES_TRIGGER` for all Dwarf/Equipment → Kíli the
  Resourceful (32 derived) and **suppresses** the mechanism-layer `SUPPLIES_RESOURCE` it replaces;
  Plunder → Uncover's coincidental `SUPPLIES_RESOURCE` is **suppressed** (the real cast-trigger
  `ENABLES_TRIGGER` was already present in the mechanism layer).
- **Class 2** — add, **generalized to ALL anthem/pump cards** (sources detected by Oracle pattern,
  not the three audited anchors): `MODIFIES obj:creature-you-control` for the **5** mass-anthem cards
  ("creatures you control get +N/+N": The Arkenstone, Bard's Company, Dwarven Provisioner, Fíli the
  Pathfinder, Thorin's Last Stand); `MODIFIES obj:target-creature` for the **4** targeted-pump cards
  (Lake-town Toymaker, Reverent Howl, Roads Go Ever, Ever On, Smaug's Fury); `ADDS_COUNTER
  obj:target-creature` for the **11** targeted-+1/+1-counter cards (Meager Meal, Moment of Glory,
  Duskwatch Hunter, Troll Negotiations, Warg Tactics, Beorn's Hospitality, Bard the Bowman, Bifur,
  Dancing from Dark to Dawn, Thranduil's Company, The Mountain-king's Return). Equipment
  ("Equipped creature …"), self-pumps ("This creature …"), tribal anthems ("Other Elves …", partly
  in graph_repair) and Amass ("… on an Army") are excluded by the patterns. Plus the two anchored
  mechanisms: tutor `SUPPLIES_RESOURCE` (Seek the Heart → 48 legendary creatures) and token-enter
  `ENABLES_TRIGGER` (48 token-makers → Belladonna Took). **23 class edges → 2,359 derived generic
  pairs.**
- **Class 3** — suppress: the false `ENABLES_TRIGGER` self-loop on Head of the Hunt.
- **Class 4** — precision note (no graph change): the `self_pairs` reflexivity label conflates a
  genuine self-referential static (e.g. Woodland Weavemaster's mana ability, #114) with an effect that
  only triggers on a *second copy* (Woodland Weavemaster's P/T ability; Uncover the Moon-Letters, #115).
  A future self-pair projection could split "reflexive-static" from "triggers-on-a-copy"; recorded here.

Every "wrong" verdict is resolved and re-verified in `pair_index.jsonl`; frozen core untouched;
259 tests pass.

## Acceptance status
The frozen HOB graph **passes independent human semantic validation** on the designed gold set: 116/128
correct, zero directional errors, zero wrong assertions in the structural strata. The 12 non-correct
items are a **bounded, characterized backlog** of missed-relation classes + edge-typing precision +
one false self-edge — none of which invalidates an existing asserted mechanism; they are additions and
one correction. Disposition of each class awaits the owner's go-ahead (Class 3 and any frozen-graph
edit require a sanctioned corrective re-freeze).
