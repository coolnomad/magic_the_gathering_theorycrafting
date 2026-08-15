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

---

## Phase 4 v2 acceptance gate (post-v1 review)

The v1 prototype merged the layers but lost conditional/identity structure and left
a weakened acceptance bound. The gate is now **strict** — the assembler
(`src/hobkg/assemble.py`) fails unless every metric below is exactly **0**, and
`tests/test_assemble.py` asserts each:

1. **Zero signature violations.** The seven enumerated Phase-3 typing errors are
   individually re-typed in `_EDGE_CORRECTIONS` (Food sac → consume Food/produce
   life; Gollum return → `MOVES_FROM zone:graveyard`; Bolg sac → consume Goblin +
   `CAUSES event:sacrifice`; two mana ops → `PRODUCES resource:mana`; two
   attachments → the Equipment *object* is the `ATTACHED_TO` subject). No signature
   is loosened to fake a pass; `assembly_review.jsonl` must be empty.
2. **Zero leaked ability aliases.** Both `local` and `ability:local` alias forms map
   to `ability:{face}:{local}`; any un-namespaced `ability:*` endpoint within a face
   is namespaced to that face. No node matches `ability:*` unless it begins
   `ability:face:`. Ability count = 418 LLM + 29 Phase 2 = **447**.
3. **All edge semantics preserved.** Every accepted edge property (condition, scope,
   timing, optional, quantity, polarity, certainty, note) survives onto the global
   edge. Inline free-text conditions become structured records in a self-contained
   `data/graph_global/conditions.jsonl`; **every `condition_ids` reference resolves**.
4. **Full ability semantics retained.** Each Ability node's `data` keeps the complete
   accepted object (trigger/costs/conditions/effects/controller/optionality/
   unresolved/confidence), not just `kind`/`oracle_spans`.
5. **Property multigraph with stable ids.** Edges are keyed by the full assertion
   signature (source, predicate, target, condition_ids, scope, timing, quantity,
   optional, polarity — polarity/optional normalized to their defaults so an edge
   asserted explicitly by Phase 2 and silently by the LLM collapse). Parallel edges
   that differ by a meaningful property coexist; every edge carries an `edge_id`.
6. **Ability/clause-grouped reification.** A reified Operation is grouped by its
   originating ability (explicit id, then enclosing/overlapping Oracle span) or, if
   none, by Oracle clause span — its several consequences are edges out of that one
   operation. The per-edge `op:{face}:effN` splitting is removed.
7. **Template dedup for every mechanic.** For all seven templated mechanics
   (Recruit, Storied, Hone, Adventure, Saga, Amass, Typecycling) the LLM's
   re-derivation of a template-owned output (soldier/army object, hone counter,
   `rule:{amass,typecycling}` instantiation) is dropped; the Phase 2 mechanism edge
   (gate/operation-sourced) is authoritative. LLM-layer duplicate count = **0**.
