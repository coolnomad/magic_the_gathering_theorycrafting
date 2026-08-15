# HOB Phase 5 — Card-Pair Projection (v2, mechanical)

- **cards**: 193  (possible ordered pairs: 37249)
- **projected metaedges**: 5281 (over 5201 ordered pairs; 5914 alternative paths)
- **infrastructure metaedges**: 4593
- **metaedges involving a gate**: 666
- **self-pairs**: 32

## By relation

- INFRASTRUCTURE_CASTING: 4593
- CONTRIBUTES_TO_GATE: 666
- SUPPLIES_RESOURCE: 18
- ENABLES_TRIGGER: 4

Derived by bounded traversal of the frozen primitive graph. Mana contribution is
colour-compatible; alternative mechanisms are kept as disjuncts; every step is a real
Phase 4 edge (forward/reverse) or a labelled derived bridge. Pairs with no allowed
functional path emit nothing (ontology-only sharing is excluded).

