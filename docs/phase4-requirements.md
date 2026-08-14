# Phase 4 (Global Assembly) — Deferred Invariants & Requirements

Accumulated from the Phase 3 reviews. Phase 4 merges the Phase 2 template graph
with the Phase 3 accepted per-face extractions into the global typed multigraph,
canonicalizes shared nodes, and namespaces card-local ids. These invariants MUST
hold after assembly (each should get a validation test in Phase 4).

## 1. Canonicalize actor-subject edges into Operation nodes

Phase 3 accepts a **card-local convention**: "actor" predicates (`MOVES_FROM/TO`,
`CREATES_OBJECT`, `ADDS_COUNTER`, `PRODUCES`, `CAUSES`, `MODIFIES`, `SCALES_WITH`,
`REFERENCES_RULE`, `INSTANTIATES`, `HAS_KEYWORD`, `HAS_COST`, `REQUIRES`) may take
a `CardFace`/`Ability` subject (e.g. `face -MOVES_TO-> zone:hand`). Phase 4 must
convert these into explicit `Operation` nodes (`op:{face}:{n}` etc.), re-source the
edges onto the operation, and then enforce **strict** predicate domain/range
(`phase3.PREDICATE_SIGNATURES` extended to all predicates) with **no `Unknown`
endpoint types remaining**. (Phase 3 review pt1; pt2 verdict.)

## 2. Amass canonicalization — Operation → INSTANTIATES → op:amass

All Amass assertions must canonicalize to a card-specific Operation instantiating
the generic operation:

```text
op:{card-face}:amass  --INSTANTIATES-->  op:amass
```

with **no `CardFace -INSTANTIATES-> rule:amass` (or `Ability -INSTANTIATES-> rule:*`)
face-to-rule instantiation edges remaining** after assembly. The Phase 2 template
already emits the correct `op:{face}:amass INSTANTIATES op:amass` form (with
`army_subtype` + `n` on the instance and an Oracle span); the Phase 3 accepted LLM
layer currently uses the card-local `face INSTANTIATES rule:amass` convention (14
edges). Phase 4 merges these into the single canonical operation-level edge and
drops the face-to-rule form. (Phase 3 review pt2, closure directive.)

Concretely, after assembly:
- `count_amass_instantiations() == 14` (all as `op:{face}:amass INSTANTIATES op:amass`),
- `count_inline_amass_expansions() == 0`,
- no edge matches `* -INSTANTIATES-> rule:amass`.

## 3. Namespace card-local ability ids

Phase 3 ability ids are card-local (`a1`, `a2`, `clapsnap-amass`, …) and only
unique within a face. Assembly must namespace them globally (e.g.
`ability:{face_id}:{ability_id}`) and rewrite all edge endpoints accordingly, so
no two cards' `a1` collide.

## 4. Process every normalized face

Assembly consumes all **210** face dispositions (209 `extracted` + 1
`reviewed_empty`), not just Oracle-bearing faces. `data/review/llm_face_status.jsonl`
is the denominator of record.

## 5. Merge Phase 2 templates with Phase 3 accepted edges; canonicalize shared nodes

Recruit/Storied/hone/Adventure/Saga/Amass/typecycling template fragments
(`data/graph/*`) and the Phase 3 accepted edges (`data/review/llm_accepted.jsonl`)
reference overlapping canonical nodes (`rule:*`, `op:*`, `token:*`, `gate:*`,
`state:*`, `counter:*`, zones). Assembly must canonicalize (single node per
concept), dedup edges, and keep provenance closure — then re-run the full
domain/range validation with zero violations and zero dangling endpoints.

## 6. Keep the two unresolved / ambiguous records out of the accepted graph

`data/review/llm_unresolved.jsonl` (currently the Thranduil "gains abilities of Elf
cards in graveyard" edge) and any `keyword_attribution_ambiguous.jsonl` entries are
excluded from the accepted primitive graph and must not be silently reintroduced by
assembly.
