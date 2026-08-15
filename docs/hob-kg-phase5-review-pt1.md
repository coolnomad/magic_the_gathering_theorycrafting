Phase 5 Part 1 is a useful scaffold, but commit [`a00f036`](https://github.com/coolnomad/magic_the_gathering_theorycrafting/commit/a00f036) is not ready to freeze. All 103 tests pass, but the tests miss several important semantic errors.

## Blocking defects

### 1. Mana projection ignores color compatibility

The implementation joins every direct mana producer to every nonzero casting cost:

```python
for a, pe in producers.items():
    for b, ce in castable.items():
```

This produces 3,060 edges exactly because it is:

```text
17 direct producers × 180 cards with mana costs
```

Consequently, red mana is projected as satisfying `{B}`, `{W}`, `{G}`, and `{U}` costs. I found 108 incompatible projections even after allowing generic and `{X}` costs.

For example:

```text
red-producing card → INFRASTRUCTURE_CASTING → card costing only {B}
```

This violates the existing mana invariant. The relation should mean “can contribute to this casting cost,” with compatibility rules:

* colored mana → matching pip or generic/variable component;
* colorless mana → generic or explicit `{C}`;
* any-color mana → any colored pip or generic;
* never red → black-only, blue → white-only, etc.

The synthetic predicate should be something like `CONTRIBUTES_TO_COST`, not `SATISFIES`, because one mana source normally does not satisfy the entire cost.

### 2. Four controller-side Treasure producers are omitted

Phase 4 identified:

```text
21 controller mana paths
1 opponent-only mana path
```

Phase 5 only uses 17 direct producers and skips every token mana operation. This correctly excludes Bilbo, but also excludes the four legitimate controller Treasure paths.

The traversal must include:

```text
Card A
→ ability/operation
→ CREATES_OBJECT Treasure [creates_for=controller]
→ Treasure mana ability
→ PRODUCES mana
→ compatible component of B’s cost
```

It must retain optionality and conditions such as combat damage, mode selection, ETB, or Saga chapter.

### 3. Required edge properties are discarded

The frozen Phase 4 notebook explicitly required Phase 5 to propagate:

* `creates_for`;
* `condition_ids`;
* `optional`;
* `polarity`;
* scope.

The projected records preserve condition IDs only. Across all 3,748 metaedges:

```text
optional field:    0
creates_for field: 0
polarity field:    0
```

Therefore, a conditional Treasure, mandatory land ability, optional effect, opponent resource, and negative/preventive interaction can become indistinguishable at projection time.

Each primitive step—or each path summary—must preserve these properties.

### 4. Deduplication conflates alternative mechanisms

`_dedup()` keeps one path per `(source, target, relation)` and unions condition IDs from discarded paths.

That is not generally valid. Alternative paths are disjunctions:

```text
path 1 works under condition A
OR
path 2 works under condition B
```

Unioning the conditions onto one retained path can imply:

```text
A AND B
```

It also discards the alternative path, its provenance, and its edge IDs despite the docstring claiming these are unioned.

Keep separate mechanistic path instances or store:

```json
{
  "relation": "...",
  "alternative_paths": [
    {"conditions": [...], "edges": [...]},
    {"conditions": [...], "edges": [...]}
  ]
}
```

Deduplicate only identical path signatures.

### 5. Some “primitive paths” contain fabricated edges

The output claims to store complete primitive paths, but introduces:

```text
SATISFIES
HAS_COST_OF
USED_BY
PRODUCED_BY
```

These are not Phase 4 edges. Some reuse the edge ID of a different, reverse-direction predicate; all mana bridges use the nonunique ID `"derived"`.

Represent reverse traversal explicitly:

```json
{
  "edge_id": "real-edge-id",
  "direction": "reverse"
}
```

Derived bridge steps need stable derived IDs and must be labeled as derived rather than primitive.

## What is good

* Ontology-only joins are excluded.
* Directional source/beneficiary pairs are retained.
* Bilbo is not treated as controller mana.
* Storied is represented as contribution rather than pairwise sufficiency.
* Outputs are deterministic and provenance-bearing.
* The separation between mechanical projection and the later LLM audit is sound.

## Recommended closure

Have the agent revise Part 1 before starting the LLM audit:

1. Implement color- and generic-compatible mana contribution.
2. Traverse controller-owned Treasure paths.
3. Propagate all semantic edge properties.
4. Preserve alternative paths instead of merging their conditions.
5. Distinguish real primitive steps, reverse traversals, and derived bridges.
6. Add exact regression tests:

```text
Island contributes to {U} and generic costs, never {W}-only.
Mountain never contributes to {B}-only.
Long-Bodied Grey Dog reaches mana through Treasure.
Bilbo reaches opponent mana only.
Conditional Treasure paths retain their conditions and optionality.
Two alternative paths remain two alternatives.
Every primitive edge ID resolves to the stated Phase 4 edge.
Every derived step has a stable unique derived ID.
```

The Storied class-ID mismatch noted in the notebook should also be canonicalized before richer traversal grammars depend on `COUNTS`.

Verdict: keep Phase 5 Part 1 open. The architecture is reasonable, but the current 3,748 metaedges are not yet a mechanically faithful card-pair projection.
