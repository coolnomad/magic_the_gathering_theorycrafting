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

---

## Phase 4 v3 acceptance gate (completeness — post-v2 review)

v2 was a valid *structural* assembly but not yet a complete *mechanistic* one: it
carried no normalized characteristics, discarded token data, left conditions as
prose, and only did endpoint (not path) template dedup. v3 adds these gates (all
**0** unless noted; asserted in `tests/test_assemble.py`):

1. **Normalized characteristics materialized.** Every face node retains
   `role/type_line/mana_cost/power/toughness/produced_mana/oracle_text`; every card
   node retains `layout/rarity/color_identity/colors/cmc/set_code/collector_number/
   oracle_id/scryfall_id/keywords`. Canonical `CardFace --HAS_TYPE--> obj:{type,
   subtype,supertype}:{slug}` ObjectClass nodes for every declared type
   (`faces_missing_type_data`, `faces_missing_type_edges` = 0); a structured
   `CardFace --HAS_COST--> cost:{face}:cast` for every mana-cost face
   (`faces_missing_cost_edge` = 0); every normalized mana producer has a mana
   operation `op:… PRODUCES resource:mana` (`mana_faces_without_operation` = 0).
2. **Token characteristics materialized.** All 12 TokenSpec nodes retain their
   normalized data and get canonical `HAS_TYPE` edges (+ a mana operation where they
   produce mana). `tokens_missing_characteristics` = 0.
3. **Conditions structured or explicitly unresolved.** Common families are converted
   to machine-evaluable expressions (`state_active`, `mode_selected`,
   `event_identity`, `eq`, `gte`, `cast_from`, `cost_paid`, `card_type_identity`);
   anything unparsed is a `raw_unresolved`, `executable:false` record. **No raw
   condition is executable** (`raw_executable_conditions` = 0) and every raw one is
   marked unresolved (`raw_conditions_not_marked_unresolved` = 0).
4. **Path-level Adventure dedup.** All 17 authoritative object-bound Adventure
   resolution paths (`op:{card}:1:resolve PRODUCES state:{card}:adventure-exiled`)
   are preserved (`adventure_resolution_state_paths` = 17); the LLM reminder
   "(Then exile this card …)" `MOVES_TO zone:exile` edges are dropped and their
   provenance merged onto the template path (`llm_reminder_adventure_exile_paths`
   = 0). Genuine effect-exiles ("exile them face down", "exile two target creatures")
   are retained. Storied's `PRODUCES state:enduring_story` is likewise folded onto
   `gate:storied`; endpoint-owned recruit/amass/hone outputs are merged, not just
   dropped.

---

## Phase 4 v4 acceptance gate (semantic safety — post-v3 review)

v3 was complete but had three semantic defects (pt4). v4 closes them (all **0**):

1. **Mechanistic mana reachability, no false direct edges.** A synthetic direct
   `op:{face}:produce-mana PRODUCES resource:mana` is created ONLY when the face's
   Oracle text contains a real mana ability of the card itself
   (`_has_direct_mana_ability`, which strips token-granted quoted abilities and token
   reminder parentheticals). The 5 indirect producers (Treasure-makers: Long-Bodied
   Grey Dog, Bilbo's Gambit, Dori, Misty Mountains Cold, Bejeweled Warg) get NO
   direct edge (`false_direct_mana_operations` = 0); instead the completeness gate
   requires a **mechanistic path** — a direct mana op OR a created token that itself
   produces mana (`mana_faces_without_mana_path` = 0).
2. **Conditions lossless or unresolved.** `_parse_condition` now full-matches the
   entire normalized condition (patterns ordered specific → general, with explicit
   negation families). A structured/executable result is emitted only when the whole
   condition — including negation and every conjunct — is represented; otherwise the
   record stays `raw_unresolved`/`executable:false`. Fixes the four pt4 cases:
   `"you do not have an enduring story"` → `not(state_active)` (not positive);
   `"combat damage to a player, mode: second option chosen"` → unresolved (conjunct
   not dropped); `"X = number of cards discarded this way"` → variable binding (beats
   the general discard rule); `"third resolution this turn"` → `eq(resolutions, 3)`.
3. **Provenance on every asserted edge.** All materialized primitives (HAS_FACE,
   HAS_TYPE, HAS_COST, token/synthetic mana) and the reification/namespacing edges
   carry derivation provenance (`{source, source_id, field?, derivation}`); the few
   Phase 2 template edges that shipped provenance-less get a `template_expansion`
   citation. `materialized_edges_without_provenance` = 0 (every edge in the graph
   has non-empty provenance).
