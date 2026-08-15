I read commits `c089f90`, `7de394e`, and latest [`75b2097`](https://github.com/coolnomad/magic_the_gathering_theorycrafting/commit/75b2097). The Storied corrections are good, and all 117 tests pass. Stage A is a reasonable start, but Stage B’s nine “accepted” relations are not yet trustworthy enough to merge into the graph.

## Defects in Stage B

### 1. Two accepted relations have reversed direction

These reports say that the target enables the source, while recording `source_to_target`:

```text
Thranduil, the Elvenking → Thranduil, Sindarin Liege
```

The target is the legendary Elf entering; it triggers the source. The mechanistic direction is:

```text
Thranduil, Sindarin Liege → Thranduil, the Elvenking
```

Likewise:

```text
The Great Goblin → Great Ugly-Looking Goblin
```

The target’s Amass places counters, triggering The Great Goblin. The correct direction is:

```text
Great Ugly-Looking Goblin → The Great Goblin
```

The ingestion layer stores the submitted direction but never verifies it against the mechanism.

### 2. Two accepted relations duplicate Part 1

These candidates already list `INFRASTRUCTURE_CASTING`:

```text
Desolation of Smaug → Smaug the Magnificent
Desolation of Smaug → Smaug, the Great Calamity
```

The LLM then accepts essentially the same Dragon-only mana relationship as `SUPPLIES_RESOURCE`. That is not a newly discovered missing relation. The “non-Dragon damage spares a Dragon” clause is also absence of harm, not an enabling mechanism.

The audit should accept a relation only when its type or primitive path is absent from `mechanical_relations`.

### 3. The grounding validator is far too weak

The acceptance check effectively asks whether each proposed grounding phrase contains at least one word longer than three characters that appears somewhere in the concatenated Oracle texts.

It does not verify:

* an exact quotation or span;
* which card contains each grounding statement;
* relation direction;
* relation type;
* logical connection between the statements;
* a primitive graph path.

Therefore, “0 rejected as ungrounded” is not meaningful.

Grounding should identify:

```json
{
  "card_id": "...",
  "face_id": "...",
  "oracle_span": [start, end],
  "text": "exact substring"
}
```

The ingest validator should verify exact substring equality against that face.

### 4. Accepted results do not contain primitive-grounded paths

The notebook says the audit must return “a primitive-grounded path or `NO_RELATION`,” but accepted records contain prose mechanisms and grounding phrases only.

There are no:

* Phase 4 edge IDs;
* forward/reverse traversal directions;
* explicit derived bridges;
* conditions;
* participant annotations;
* optionality or polarity.

Consequently, the results cannot yet be incorporated into the typed projection with the same epistemic standard as Part 1.

### 5. There is no independent critic/reconciliation stage

This is a single sub-agent verdict pass. Phase 3 already demonstrated why extractor–critic agreement matters. At minimum:

```text
extractor verdict
→ independent critic
→ deterministic validation
→ reconcile disagreements
```

The reversed directions and duplicated relations are exactly the errors a critic should catch.

## Candidate coverage issues

Stage A generated 116 candidates and audited only the 44 high-signal candidates. That is fine for a labeled high-signal pass, but it is not Part 2 completion.

Two buckets also need redesign:

* `copy_effect` creates only a self-pair. A copier should be paired with cards that produce objects it can legally copy.
* `ambiguous_scope` does not generate candidates; it merely annotates pairs selected by another bucket. Thus an ambiguous referent cannot independently cause a missed pair to be reviewed.

The 76 shared-vocabulary candidates also remain unaudited.

## Assessment of the nine accepted findings

After manual review:

* 5 appear valid with the current direction:

  * the two Treasure/Smaug relationships;
  * the three Bard draw-replacement relationships.
* 2 are valid relationships but directionally reversed:

  * Sindarin Liege → Elvenking;
  * Great Ugly-Looking Goblin → Great Goblin.
* 2 duplicate existing infrastructure relations:

  * Desolation → the two Dragon cards.

So the likely result of this pass is seven novel relations, not nine, with two requiring endpoint reversal.

## Required next pass

1. Require exact per-face Oracle spans.
2. Require a primitive or explicitly derived typed path.
3. Normalize endpoints from the submitted direction.
4. Reject paths already represented in `mechanical_relations`.
5. Run an independent critic and reconcile.
6. Regenerate copy candidates against eligible produced objects.
7. Make ambiguous-scope selection operational rather than annotation-only.
8. Store accepted audit paths in a separate augmented projection layer with `origin: llm_audit`.
9. Then process the remaining shared-vocabulary candidates.

Verdict: Stage A is useful and the high-signal audit surfaced real missed relationships, but commit `75b2097` should remain an audit draft. Do not merge its nine accepted relations into the canonical projection yet.
