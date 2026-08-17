The current commit is `2532566`, Phase 1: census, frozen-hash manifest, and specification entry.

Overall: good foundation, but I would treat Phase 1 as provisionally accepted rather than complete. There are two issues worth correcting before the schema is built around this census.

## What is correct

* It scans all 210 faces, including permanents.
* The implementation contains no card-name or UUID branches.
* It creates deterministic machine-readable and human-readable outputs.
* Reminder-text matches are flagged rather than silently discarded.
* All 474 candidates are explicitly marked `pending_structuring`.
* The seven listed frozen artifacts are unchanged from the previous commit.
* The important regression cards appear in the census:

  * Warg Tactics
  * Reverent Howl
  * Pinecone Strike
  * Settle the Wreckage
  * Stone by Sunlight
  * Thranduil’s Decree
* The commit is appropriately bounded: it does not prematurely add graph edges or semantic schemas.

## Finding 1: these are keyword hits, not yet effect clauses

The report calls its 474 records “candidate clauses,” but each record is currently a regex match fragment:

* Settle the Wreckage’s exile record contains only `Exile`.
* Warg Tactics’ ability-grant record contains `gains trample`, not the full instruction granting both trample and hexproof.
* Pinecone Strike’s replacement effect is represented by an isolated `exile` hit.
* Modal structure and object binding are absent, as expected for Phase 1—but the census row does not retain enough clause context to adjudicate the clause independently.

This is fixable without doing Phase 2 early. Each census record should additionally retain:

* the complete Oracle instruction or clause span;
* the matched detector span;
* ability/paragraph index;
* sentence/instruction index;
* preliminary mode index where mechanically detectable;
* all matched families attached to the same clause.

The current `oracle_span` should be renamed `match_span`, with a separate `clause_span`. Otherwise later dispositions will attach to words rather than semantic clauses, and one clause may be adjudicated inconsistently across several rows.

For example, Warg Tactics should have one second-mode clause carrying:

* `add_counter`
* `grant_ability`
* both `trample` and `hexproof`
* a common clause/mode identifier

The complete binding can wait for Phase 2.

## Finding 2: the census does not yet cover every required family

The instructions require a disposition for other material effects too, including:

* scry, surveil, look, and reveal;
* copying spells, abilities, or objects;
* cost modification;
* additional-land permissions;
* attack, block, and cast restrictions;
* ability removal;
* power/toughness setting or switching;
* counter removal;
* delayed effects;
* replacement effects as a distinct family;
* permissions that do not use the exact phrase `may play` or `may cast`.

Those are not represented among the present 22 families. Some existing detectors are also deliberately narrow:

* `modify_pt` finds literal numeric `gets +N/+N`, but not variable modifications such as `+X/+X`, characteristic setting, or switching power and toughness.
* `grant_ability` searches a fixed keyword list and can miss non-keyword granted abilities.
* `type_change` only recognizes the “becomes … in addition” form.
* `control_change` recognizes “gains control” but not exchanges or other control wording.

It is fine for Phase 1 to produce false positives. It is not fine for the completeness ledger to systematically omit whole required families. Expand the census now; otherwise Phase 7 cannot honestly establish that every material clause received a disposition.

## Finding 3: strengthen the freeze guard

The manifest correctly protects the seven listed core artifacts, but the test trusts whatever hashes currently appear in the manifest. A future change that modifies both an artifact and its manifest would still pass.

I recommend:

* Confirm from the project’s freeze ledger that these are the complete protected artifacts, including any separately frozen Phase 5 outputs.
* Pin the expected manifest contents or manifest digest in the test/code rather than treating the manifest as a freely regenerated baseline.
* Document that changing the pinned baseline requires a sanctioned re-freeze.

This is not a defect in the graph; it is a weakness in the enforcement mechanism.

## Recommended instruction to the agent

> Phase 1 is directionally correct and may remain a separate commit. Before treating it as complete, add a small Phase 1.1 correction:
>
> 1. Distinguish regex `match_span` from complete `clause_span`.
> 2. Assign stable clause/instruction IDs and group multiple detected families under the same clause.
> 3. Retain enough complete clause text to adjudicate each disposition.
> 4. Expand the candidate families to cover every effect family required by the repair specification, especially scry/look/reveal, copy, cost modification, additional-land permissions, restrictions, replacement/delayed effects, variable or setting P/T effects, counter removal, and non-keyword ability grants.
> 5. Strengthen the frozen-artifact test so updating an artifact and regenerating the manifest cannot silently redefine the frozen baseline.
> 6. Regenerate the census and report; keep every row pending until its later phase adjudicates it.
>
> Do not begin pair projection in this correction. The current commit’s separation between census and semantic materialization is correct.

I would not ask the agent to undo this commit. It is a sound Phase 1 scaffold; it just needs the census promoted from a keyword-hit inventory into a reliable clause-level completeness ledger before Phase 2 depends on it.
