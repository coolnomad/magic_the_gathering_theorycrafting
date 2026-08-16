I checked latest commit `d4027d5`. The Equip path repair is successful, but the broader Crude Bent Blade lifecycle is still incomplete.

What the commit fixes correctly:

* All Equip-derived card-pair paths are now continuous from equipment card to candidate creature card.
* The attachment target, attachment state, and equipped creature are properly bound.
* Crude Bent Blade now projects to every creature—including Snowslope Hunter—with:

  * `CAN_ATTACH_TO`
  * `MODIFIES_WHEN_ATTACHED` with `+2/+1`
* Equip `{2}`, controlled-creature targeting, sorcery timing, attachment dependence, and Oracle provenance are represented.
* The full test suite passes: 205 tests.
* The regenerated layer reports 3,250 Equip metaedges with no signature failures.

For example, Crude → Snowslope Hunter now has a grounded path approximately equivalent to:

```text
Crude Bent Blade
  HAS_FACE → equipment face
  HAS_ABILITY → Equip ability
  CAUSES → attach operation
  REQUIRES → creature you control
  HAS_TYPE ↔ Creature
  ← Snowslope Hunter
```

The static bonus follows a separate, attachment-dependent path through the bound-creature object.

## Remaining Crude Bent Blade gap

The graph describes two of its three roles:

1. Its entry trigger makes the opponent sacrifice a creature.
2. It remains Equipment and can grant `+2/+1`.

It does not yet connect its third role:

3. Once on the battlefield, it is an artifact you can sacrifice to pay costs.

Consequently, there is currently:

* no Crude Bent Blade → Stir Up Trouble relationship;
* no Crude Bent Blade → Snowslope Hunter sacrifice-fodder relationship.

Crude is typed as an artifact, and Stir contains a `CONSUMES → an-artifact-or-creature` edge. But the graph has no rule that unifies a particular artifact permanent with that cost operand. Snowslope Hunter is even less complete: its sacrifice cost remains embedded in the ability record rather than being represented by a primitive `CONSUMES` edge.

This should be implemented generically, not as a Crude-specific repair.

```text
Crude Bent Blade
  HAS_TYPE → Artifact
  CAN_EXIST_AS → controlled battlefield permanent
  SATISFIES_ALTERNATIVE_COST →
    Stir Up Trouble's “sacrifice an artifact or creature” gate

Crude Bent Blade
  HAS_TYPE → Artifact
  CAN_EXIST_AS → controlled battlefield permanent
  SATISFIES_ACTIVATION_COST →
    Snowslope Hunter's “sacrifice another creature or artifact” gate
```

The underlying mechanisms should include:

* explicit cost gates with artifact/creature type alternatives;
* `CONSUMES` from the casting or activation operation to its selected permanent;
* controller and battlefield requirements;
* the Hunter-specific `another` constraint;
* Stir’s OR relationship between sacrificing and paying `{4}`;
* sacrifice moving the selected permanent to its owner’s graveyard;
* sacrifice of attached Equipment terminating its attachment state and continuous bonus.

That would let the graph express the real intervention:

```text
Use Crude as Equipment
        ↓
receive +2/+1 over some interval
        ↓
sacrifice Crude to Stir or Hunter
        ↓
gain the consumer’s effect
and lose the Equipment/attachment effect
```

## Other feedback on this commit

One important completeness issue remains inside the Equip audit itself. Several material Equipment clauses are recorded as `deliberately_ignored`, including:

* Glamdring’s spell-cost reduction;
* Orcrist’s combat-damage trigger;
* Sting’s hone-counter bonus;
* other complex attached-creature effects.

Recording them is honest, but I would classify these as `unresolved` or `schema_extension_required`, not successfully disposed. They are strategically important mechanisms and will matter when decks are projected into graph space.

The preceding review also identified unresolved system-wide gaps in second-card-drawn enablers, token-entry triggers, and sacrifice-outlet/dies-trigger relationships. The Crude example belongs to that same missing family: the graph is now good at static attachment compatibility, but it does not yet fully model permanents as resources that can change roles and be consumed.

So my verdict is: **accept `d4027d5` as a correct Equip-path repair, but not as complete Equipment/permanent-lifecycle handling.** The next reusable module should be a general typed-cost and permanent-consumption layer.
