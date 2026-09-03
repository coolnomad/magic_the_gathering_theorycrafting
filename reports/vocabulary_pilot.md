# Layer 2 Vocabulary Report — Pilot Run

**Generated:** 2026-09-03  
**Faces processed:** 11 (10 pilot + 1 adventure back)  
**Port records emitted:** 11  
**Total edges:** (computed from output)  
**Unresolved abilities:** 0

## Summary

All 11 pilot faces derived successfully with zero unresolved abilities. The
derivation procedure maps extraction verbs through declared op_map entries,
builds selectors from target/controller/restriction fields, and classifies
edges by predicate into properties/installs/consumes/produces/costs.

## Concept Coverage

### Used Concepts

From the 11 pilot faces:

- **Types:** `obj:type:creature`, `obj:type:instant`, `obj:type:sorcery`,
  `obj:type:artifact`, `obj:type:enchantment`
- **Categories:** `obj:category:permanent`, `obj:category:nonpermanent`,
  `obj:category:spell`
- **Events:** `event:this-creature-attacks`, `event:this-creature-dies`,
  `event:this-creature-enters`, `event:this-creature-enters-or-attacks`,
  `event:you-cast-spell`, `event:you-activate-creature-ability`
- **Gates:** `gate:storied`
- **Keywords:** `keyword:flying`, `keyword:hexproof`, `keyword:indestructible`,
  `keyword:lifelink`, `keyword:prowess`
- **Zones:** `zone:battlefield`, `zone:exile`, `zone:graveyard`
- **Counters:** `counter:+1/+1`, `counter:lore`
- **Tokens:** `token:treasure`, `token:human-soldier`

### Proposed Concepts

No proposals submitted. The seed vocabulary from `vocabulary_seed.jsonl` covered
all pilot needs.

## Effect Verb Mappings

33 verb→predicate mappings declared in `op_map.jsonl`. All pilot effects mapped
successfully:

- **Movement:** `exile`, `return_to_battlefield`, `sacrifice`
- **Modification:** `add_counter`, `put_counter`, `modify_pt`, `grant_keyword`,
  `grant_ability`
- **Resource:** `draw`, `discard`, `lose_life`, `deal_damage`
- **Object creation:** `create_token`, `amass`
- **Interaction:** `destroy`, `attach`, `replacement`
- **Cost/gate:** `pay_mana`, `additional_cost`, `additional_cost_definition`
- **Watcher:** `storied`
- **Doubling:** `double_triggered_ability`, `duplicate_trigger`
- **Saga:** `lore_count_reaches`, `saga_lore_counter_management`
- **Adventure:** `exile_this_card`
- **Mechanic:** `recruit`

Source keys handled: `op`, `effect`, `action`, `type`

## Derived Type Rules

Type→category mapping sourced from `type_categories.jsonl` (15 rows, all citing
comprehensive rules):

- **Permanent types** (CR 110.4a): Artifact, Battle, Creature, Enchantment, Land,
  Planeswalker → `obj:category:permanent`
- **Nonpermanent types** (CR 110.4): Instant, Sorcery → `obj:category:nonpermanent`
- **Spell types** (CR 110.4b, 112.1): all except Land → `obj:category:spell`

Every pilot face carries IS_A edges for its printed types and for the derived
categories those types imply.

## Selector Grammar

No selector-in-name concepts emitted. All edges reference bare classes
(`obj:type:creature`, not `obj:target-creature`) and encode targeting/restriction
as structured edge data. See `data/vocabulary/selectors.md`.

## Watcher Rule

**Bifur, Melodic Rider** installs `gate:storied` (Storied keyword).  
**Smaug, Wicked Worm** does not, despite qualifying (no Storied keyword printed).

The rule: only abilities with `keyword: "Storied"` in the extraction install the
watcher. QUALIFIES_FOR is watcher-derived and never a card output.

## Trigger Mapping

Triggers map to Event concepts and appear under `consumes`:

| Extraction `event` | Maps to |
| --- | --- |
| `"this creature attacks"` | `event:this-creature-attacks` |
| `"this creature dies"` | `event:this-creature-dies` |
| `"this_creature_enters"` | `event:this-creature-enters` |
| `"enters_or_attacks"` | `event:this-creature-enters-or-attacks` |
| `"you_cast_spell"` | `event:you-cast-spell` |
| contains "activate" + "creature" | `event:you-activate-creature-ability` |

Normalization handles both underscore and space variants.

## Structural Findings

### Costs

Additional costs (Stir Up Trouble), sacrifice outlets (Rampager), and equip
costs (Wizard's Staff) all appear under `costs`, not `produces`.

### Modality

The Phase 3 extraction does not currently emit modal structure -- Pinecone
Strike's extraction has `modality: null` and two independent `spell_effect`
abilities rather than a modality object with numbered modes. The port record
preserves this faithfully (`modality: null`) rather than inventing structure
the extraction does not carry. Adding modal parsing is a separate task; when
the extraction gains modes, ports.py will surface them.

### Conditions

Conditions from the extraction (Elrond's `"only once each turn"`, Smaug's
`"intervening-if"`) attach to the port entry they qualify. No orphans.

### Role Bindings

Wizard's Staff grants prowess to `binding: equipped` (not yet implemented in
this iteration — falls under `GRANTS` without explicit binding field).

## Holdout Test

Three holdout faces (Gollum Silent Slinker, Belladonna Took, Tom Bert and William)
derived without code changes. All three produced valid port records.

Stability test: pilot records byte-identical whether emitted alone or with holdouts.

## Next Steps

- [ ] Extend selector grammar for `binding:` field (Equipment/Aura role references)
- [ ] Handle modal spell structure (mode[0], mode[1] in output)
- [ ] Map delayed/replacement effects to structured timing fields
- [ ] Extend event catalog for full-set coverage
- [ ] Validate oracle_span coverage (every clause of every ability)
