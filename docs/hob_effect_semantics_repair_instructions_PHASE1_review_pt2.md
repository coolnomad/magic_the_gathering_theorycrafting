The latest commit is `98bb8d2`, following Phase 2 at `93c3744`.

Verdict: the three requested Phase 1.1 corrections were implemented correctly, but one completeness issue remains before the census should be frozen.

What is now correct:

* Regex hits are grouped into clause-level records.
* Records include stable IDs, clause spans, match spans, ability/mode/sentence indices, and all detected families.
* Warg Tactics correctly groups counter placement with trample and hexproof.
* Reverent Howl groups draw and life loss on the same modal branch.
* The family inventory expanded from 22 to 32.
* The frozen manifest itself is pinned by a hard-coded digest.
* The protected set is explicitly documented as the seven frozen core artifacts.
* No pair projection was added as part of Phase 1.1.
* Frozen graph files remain unchanged.

## Remaining issue: the ledger still depends on detecting an effect family

Only clauses with at least one regex match enter the census. Consequently, a material effect that lacks a detector disappears entirely.

A concrete false negative is:

> Iron Hills Stalwart — “When this creature enters, attach target Equipment you control to up to one target creature you control.”

Iron Hills Stalwart has no census row at all because there is no attachment family. Likewise:

> Glóin the Mighty — “At the beginning of your first main phase, add {R}{R}.”

Glóin has no row because mana production is absent from the family inventory.

Even if attachment and mana are already represented elsewhere, the completeness ledger needs to record them and assign a disposition such as “already represented by equipment layer” or “already represented by mana infrastructure.” Otherwise the final claim that every material clause received a disposition will not be auditable.

The robust solution is not merely to keep adding regexes. The census should emit every segmented Oracle clause, including clauses with zero detected families:

```json
{
  "families": [],
  "disposition": "pending_classification"
}
```

Then later phases must resolve each one as:

* structured/projected;
* structured/not projected;
* already represented by another layer;
* intrinsic characteristic/reminder text and deliberately ignored;
* unresolved.

This would also ensure that an undetected sentence cannot hide inside a larger ability paragraph that happened to match another family.

## Small data-loss issue

`clause_text` is still truncated to 260 characters:

```python
"clause_text": text[g["start"]:g["end"]].strip()[:260]
```

At least nine clauses exceed that limit, including:

* Bolg of the North: 378 characters
* Part in Friendship: 366
* Azog, Moria’s Ruin: 362
* The Eagles Are Coming!: 300

The full text can technically be recovered using `face_id` and `clause_span`, but there is no reason to truncate a 210-card machine-readable ledger. Store the full clause text.

## Recommended instruction

> Phase 1.1 resolves the prior review findings, with one remaining completeness correction:
>
> 1. Emit every segmented Oracle clause, even when no effect-family detector matches it.
> 2. Give unmatched clauses `families: []` and `disposition: pending_classification`.
> 3. Add detector families for at least attachment/detachment and mana production, while retaining all-clause emission as the safeguard against future detector omissions.
> 4. Remove the 260-character truncation from `clause_text`.
> 5. Add regression tests showing that Iron Hills Stalwart’s attachment clause and Glóin the Mighty’s mana-production clause appear in the census.
> 6. Verify that every nonempty Oracle-text paragraph maps to a census clause or an explicitly recorded segmentation exception.
>
> No projection or frozen-graph change is required.

After that correction, I would consider Phase 1 genuinely complete. The current implementation is otherwise a substantial improvement and does not need to be rolled back.
