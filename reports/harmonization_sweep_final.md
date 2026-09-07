# Card 002 harmonization sweep — FINAL

- Ports: 210
- Edges: 2242
- Distinct predicates: 81

## Delta across all axes

| Axis | v1 (baseline) | v2 (mid) | Final |
|------|---------------|----------|-------|
| 1. Low-count predicates (<3 faces) | 51 | 51 | 34 |
| 2. Predicate/field gaps (10-90%) | 266 | 194 | 212 |
| 3. Predicates with heterogenous amount types | 8 | 9 | 10 (see amount_kind field) |
| 4. Predicates mixing endpoint shape | 20 | 20 | 13 |
| 5. Keyword involvement misses | 50 | 6 | 6 (all false positives) |
| 6. Cost edges missing purpose | 7 | 1 | 1 |
| 7. Target-scoped edges missing selector | 9 | 9 | 0 |
