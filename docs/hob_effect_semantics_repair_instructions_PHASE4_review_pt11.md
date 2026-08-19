---
phase: Phase 4
iteration: pt11
reviewed_commit: 300260e0307218f77646958175b7a2946a0111a2
parent_commit: caecefad5e41d91c3e9c6ef7639b7b3c7833e89c
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 3
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed implementation commit `300260e0307218f77646958175b7a2946a0111a2`
(`Effect-semantics Phase 4d: SEARCH / tutor`) against parent
`caecefad5e41d91c3e9c6ef7639b7b3c7833e89c`.

The commit adds the intended deterministic `SEARCHES_FOR` projection and keeps
the accepted Phase 4a/4b/4c records and non-search pair projections unchanged.
However, the authoritative `SEARCH` records still contradict Oracle zones and
drop important antecedent/quantity bindings. Phase 4d needs repair before
acceptance.

## Evidence Inspected

- `git status --short --branch`
- `git fetch origin`
- `git log --oneline --decorate -22 --all`
- `git show --stat --summary --format=fuller 300260e0307218f77646958175b7a2946a0111a2`
- `git show -s --format=full 300260e0307218f77646958175b7a2946a0111a2`
- `git diff --check caecefad5e41d91c3e9c6ef7639b7b3c7833e89c..300260e0307218f77646958175b7a2946a0111a2`
- `git diff --name-status caecefad5e41d91c3e9c6ef7639b7b3c7833e89c..300260e0307218f77646958175b7a2946a0111a2`
- `git diff caecefad5e41d91c3e9c6ef7639b7b3c7833e89c..300260e0307218f77646958175b7a2946a0111a2 -- src/hobkg/effect_semantics.py`
- `git diff caecefad5e41d91c3e9c6ef7639b7b3c7833e89c..300260e0307218f77646958175b7a2946a0111a2 -- tests/test_effect_search.py`
- Direct JSON queries over every generated `SEARCH` record.
- Direct JSON queries over `card_pair_projection_effect.jsonl` and
  `pair_index.jsonl` for `SEARCHES_FOR` and participant/resource fan-out.
- Oracle text from `data/normalized/faces.jsonl` for every generated `SEARCH`
  record.
- Portability search for audited search-card names in `src/hobkg/effect_semantics.py`.

## Tests and Commands Run

- `pytest tests/test_effect_search.py tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - Result: `126 passed`.
- `pytest -q`
  - Result: `396 passed`.
- Frozen manifest SHA-256 verification against
  `data/graph_global/frozen_manifest.json`
  - Result: `frozen_failures 0`.
- Direct projection query for `SACRIFICES`, `DISCARDS_CARDS`, `MILLS_CARDS`,
  `DRAWS_CARDS`, `GAINS_LIFE`, and `LOSES_LIFE`
  - Result: no participant/resource/sacrifice fan-out emitted in
    `card_pair_projection_effect.jsonl` or `pair_index.jsonl`.
- Direct comparison of accepted Phase 4a/4b/4c records
  (`DRAW`, `GAIN_LIFE`, `LOSE_LIFE`, `DISCARD`, `MILL`, `SACRIFICE`) between
  `42d5000` and `300260e`
  - Result: same 91-record subset hash,
    `c0ddae1393fb6f5551cf0b935ef13fa30fcc7edb9ee3bfcc3c7c6ac534c34f1e`.
- Direct comparison of non-search pair projections between `42d5000` and
  `300260e`
  - Result: same 7,950-pair subset hash,
    `460296b52b187b2a42beb4b3e90f442c0d594ba73edeaa508ca7d852bfc2586c`.
- `python -m hobkg.cli effect-reconcile`
  - Result: 324 clause/family pairs, 218 extracted, 4 deferred, 0 unresolved.
- `python -m hobkg.cli effect-build`, run twice
  - Result: 222 effects, 135 faces, 8,039 pair projections.
  - Byte-identical hashes:
    - `data/graph_global/effect_records.jsonl`
      `4e3b632c4bd43f573172fef661a5a66938dc8a0916e6a81b0663f336cac75bcf`
    - `data/graph_global/card_pair_projection_effect.jsonl`
      `61c409d350d6e1d3e340c03ab8ae4894b7850df9eb7ed089300cd4d087a25e35`
    - `data/graph_global/pair_index.jsonl`
      `4e93f673be65e051913ee7356c7410703551d34ce5f5168cc4889965f5be66ce`

## Frozen-Artifact Status

The protected frozen graph artifacts still match
`data/graph_global/frozen_manifest.json`. No frozen-baseline change was detected.

## Findings

### 1. SEARCH selectors incorrectly say the searched cards are on the battlefield

Impact: authoritative structured semantics.

Every generated `SEARCH` record uses `_sch.selector(phrase, ...)`, whose default
zone is `battlefield` when the phrase itself does not contain a zone. The record
also carries a separate `source_zone`, but the authoritative searched-card
selector still contradicts the Oracle search zone.

Concrete examples:

- `Seek the Heart`: Oracle says "Search your library for a legendary creature
  card..." The record has `source_zone: "library"` but
  `selector.zone: "battlefield"`.
- `Thrór's Map`, `Hobbit Hole`, `Elven Passage`, `Old Thrush`, `Down in the
  Valley`, `Wood Elves`, `Troop of Ponies`, `Roads Go Ever, Ever On`, and
  `Settle the Wreckage` all search a library, but their searched-card selectors
  also have `zone: "battlefield"`.
- `Last Light of Durin's Day` searches hand and/or library, but its searched
  selector has `zone: "battlefield"` instead of representing
  `hand_and_library`.

Projection may still find eligible card faces because `_sch.matches_card()` is
type-based, but the structured effect record itself is semantically wrong. The
selector should represent the searched object in the searched zone, not a
battlefield permanent.

Required correction:

- Override or extend the searched-card selector zone to match `source_zone`.
- Add tests that fail if any `SEARCH` record's searched selector remains
  `battlefield` when the printed search source is a library or hand/library.
- Keep deterministic projection to eligible card identities if that is the
  intended abstraction, but do not encode those eligible cards as battlefield
  objects in the authoritative record.

### 2. `Settle the Wreckage` loses the "that many" antecedent binding

Impact: authoritative structured semantics and future execution semantics.

Oracle text:

`Exile all attacking creatures target player controls. That player may search
their library for that many basic land cards, put those cards onto the
battlefield tapped, then shuffle.`

The generated `SEARCH` record correctly has `participant: "target_player"`,
`optional: true`, `quantity: "variable"`, `source_zone: "library"`, and
`dest_zone: "battlefield"` with `dest_tapped: true`. It does not preserve what
the variable quantity means. The record has no `quantity_formula` or binding
that ties "that many" to the number of attacking creatures exiled by the prior
instruction.

Required correction:

- Add an explicit variable quantity formula or binding for `Settle the
  Wreckage`: amount searched equals the count of creatures exiled by the prior
  exile instruction.
- Preserve that the participant/searcher is the same target player whose
  creatures were exiled.
- Add a test that checks the binding, not merely `quantity == "variable"`.

### 3. `Last Light of Durin's Day` search uses a generic condition and loses the prior-action gate

Impact: authoritative structured semantics.

Oracle text:

`If it has six or more quest counters on it, sacrifice it. If you do, search
your hand and/or library for a Dragon card and put it onto the battlefield.`

The generated search record has `condition: {"kind": "conditional_effect"}`.
This says that some conditional effect exists, but does not preserve that the
search is gated by the prior self-sacrifice action. The preceding accepted
sacrifice record now correctly records the quest-counter threshold; the SEARCH
record should bind its `If you do` to that prior sacrifice action rather than
storing only a generic condition marker.

Required correction:

- Represent the search condition as a prior-action gate tied to the successful
  self-sacrifice, or otherwise preserve the antecedent explicitly.
- Preserve `source_zone: "hand_and_library"` and ensure the searched selector
  also reflects that source.
- Add a test that fails if the condition remains only
  `{"kind": "conditional_effect"}`.

## Required Corrections

1. Correct SEARCH selector zones so the searched-card selector agrees with the
   printed search source.
2. Add explicit antecedent/quantity binding for `Settle the Wreckage`.
3. Add explicit prior-action binding for `Last Light of Durin's Day`.
4. Regenerate `effect_records.jsonl`, `card_pair_projection_effect.jsonl`,
   `pair_index.jsonl`, `reports/effect_semantics.md`, and
   `reports/effect_reconciliation.md`.
5. Keep accepted Phase 4a/4b/4c records byte-identical unless explicitly
   authorized otherwise.

## Acceptance Tests for the Next Commit

The next review should include at least these checks:

- `pytest tests/test_effect_search.py tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
- `pytest -q`
- Frozen manifest SHA-256 verification.
- Two consecutive `python -m hobkg.cli effect-build` runs with byte-identical
  generated hashes.
- `python -m hobkg.cli effect-reconcile`.
- `python -m hobkg.cli pair-index`, preferably twice if pair-index determinism
  is still claimed.
- Direct JSON assertions that:
  - every `SEARCH` selector has a zone compatible with `source_zone`;
  - `Settle the Wreckage` binds "that many" to the count of exiled attacking
    creatures and preserves the target-player antecedent;
  - `Last Light of Durin's Day` binds its search condition to the prior
    self-sacrifice, not a generic conditional marker;
  - accepted Phase 4a/4b/4c records remain byte-identical;
  - non-search pair projections remain byte-identical.

## Phase Proceed Status

This Phase 4d implementation commit is not accepted. Phase 4 may continue only
with a repair commit addressing the blocking SEARCH findings or with an explicit
human decision to refine the phase specification.
