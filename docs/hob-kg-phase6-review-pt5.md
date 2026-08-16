I inspected `bf16c01`/`2e613e7`. The second-draw repairs are good, but the Equipment layer is not ready. All 199 tests pass because the tests verify edge existence, not whether projected paths are actually continuous and grounded.

## Correctly fixed

* `cond:draw-is-second-this-turn` now resolves through `mechanism_conditions.jsonl`.
* The second-draw gate is an explicit 1→2 equality transition rather than `count >= 2`.
* The counter is controller-scoped and marked to reset each turn.
* All condition references across current layers resolve.
* Equipment costs, timing, controller restriction, and Wizard’s Staff’s alternative cost are represented.
* The five projection tiers and query layer are integrated.

## Blocking Equipment defects

### 1. `CAN_ATTACH_TO` paths are disconnected

A representative path is recorded as:

```text
Equipment face
→ Equip ability
→ Equip operation
→ obj:creature-you-control
→ creature face
```

But the final reversed edge is actually:

```text
obj:type:creature ← HAS_TYPE ← creature face
```

`obj:creature-you-control` and `obj:type:creature` are different nodes with no connecting edge. The serialization simply concatenates the steps and makes the path appear continuous.

The path validator only confirms that each edge ID exists. It does not assert:

```python
previous_step.target == next_step.source
```

This affects the primary `CAN_ATTACH_TO` relations—approximately 1,344 assertions.

Required repair: establish a formal class relationship such as:

```text
obj:creature-you-control
  REQUIRES_TYPE / SUBCLASS_OF
obj:type:creature
```

and incorporate controller binding, or derive the target match with an explicit typed binding step.

### 2. Modification and grant projections are not grounded to either card

A typical `MODIFIES_WHEN_ATTACHED` path is only:

```text
state:attachment:E
← REQUIRES ←
modify operation
→ MODIFIES →
obj:bound-creature:E
```

It contains neither:

* the source Equipment face; nor
* the target creature face.

The code loops over every creature card and assigns that card as `target_card`, but the computed creature `HAS_TYPE` edge is never added to the path. Thus 1,680 modification/grant relations are population expansion without a grounded path.

Required path:

```text
Equipment E
→ Equip operation
→ attachment state E-C
→ equipped-effect operation
→ bound creature C
→ resolved target creature card C
```

The binding step must prove that the abstract `C` is the projected target card.

### 3. Several printed Equipment effects are missing

The regex handles fixed P/T bonuses and a keyword list, but not the full Equipment semantics:

* **Glamdring:** equipped creature’s power determines instant/sorcery cost reduction.
* **Wizard’s Staff:** doubles triggered abilities of the equipped creature.
* **Sting:** Hone counters provide a scaling +1/+0 bonus to the equipped creature.
* **Orcrist:** equipped-creature combat damage enables the Equipment’s Treasure trigger.
* Other conditional or non-keyword granted abilities will similarly be missed in future sets.

These require structured extraction/template binding, not only regex matching.

### 4. Automatic attachment abilities are orphaned

The layer creates:

```text
ability:auto-attach:E → op:auto-attach:E
```

but does not add:

```text
face:E → HAS_ABILITY → ability:auto-attach:E
```

Therefore the automatic attachment operation is not connected back to its printed card.

Additionally, the automatic operation carries the condition “Equipment is attached” while causing the attachment state. That is circular: being attached is the result, not a prerequisite.

### 5. The Axe Equipment token is omitted

`token:axe` has:

* Equipment subtype;
* Equip `{2}`;
* “Equipped creature gets +1/+0.”

The implementation explicitly skips it because it has no card face. It must be represented at the primitive level. Its producing cards can then acquire conditional downstream relationships through the created Axe token.

### 6. Equip provenance is insufficient

The new Equip nodes and edges generally cite only:

```text
source: equip
derivation: ...
```

They do not carry exact Oracle spans or direct rule citations for the individual costs, targets, bonuses, and attachment effects. The spec requires exact provenance for assertions.

## Required new validation tests

Add tests that require:

```python
for path in every_projected_relation:
    assert path[0] resolves to source_card
    assert path[-1] resolves to target_card

    for left, right in adjacent_steps(path):
        assert traversed_endpoint(left) == traversed_start(right)
```

Also require:

* every automatic attachment ability has an incoming `HAS_ABILITY` edge from its face;
* no operation requires the state it causes;
* every `MODIFIES_WHEN_ATTACHED` target card appears in its primitive path;
* every source Equipment appears in its primitive path;
* all Equipment and Equipment tokens receive template coverage;
* every equipped-creature Oracle clause has a disposition: represented, deliberately ignored, or unresolved;
* individual assertions carry Oracle spans and Equip-rule provenance.

## Verdict

The second-draw repair can be accepted. The Equipment implementation demonstrates the intended architecture, but its 3,028 projected relations should not be accepted yet: most are not valid end-to-end graph paths, and several important Equipment mechanisms are absent.

One unrelated note: this commit also broadens `.claude/settings.json` permissions to allow `git checkout` and `git restore`. Those commands can overwrite local work, so keep that change only if you intentionally want the implementation agent to have that authority.
