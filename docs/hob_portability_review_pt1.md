Commit `8e2d90a` is a strong correction to the previous tracer bullet. I’d accept it as a successful schema prototype and preliminary FIN validation, with several qualifications.

What is now solid:

* Real, source-provenanced FIN Oracle text replaces invented examples.
* Expected structures are compared field-by-field.
* `ALT` cost branches are separated from selector-level type alternatives.
* Edicts are no longer mislabeled as activated costs.
* Unknown contexts can be marked `unsupported`.
* Actor, quantity, ability context, self/another, and timing restrictions are represented.
* HOB graph/data layers remain untouched.

The central result should be stated as:

> On six curated held-out FIN cards, 2/6 were exactly correct; the remaining four each had one field error.

That is more informative than calling 95.2% field accuracy “the honest portability number.” The two metrics are:

| Metric                    |        Result |
| ------------------------- | ------------: |
| Exact card-level accuracy |   2/6 = 33.3% |
| Micro field accuracy      | 80/84 = 95.2% |

The field metric is inflated by numerous easy/default fields such as `modal=False`, empty qualifier lists, and `restriction_timing=None`. It remains useful diagnostically, but exact-record accuracy should be primary.

Remaining structural issues:

1. This tests parsing conditional on curated examples, not set-wide extraction.

   FIN has 50 card-face texts containing “sacrif”; the parser returns an outlet for 30. Only 17 cards are adjudicated in the fixtures. The other outputs and nonoutputs have not been classified, so recall and false-positive rate remain unknown.

2. The sacrifice atom is disconnected from its selector.

   The cost contains `{"sacrifice": True}`, while the selector is stored once at the record level. This cannot cleanly represent costs such as:

   * sacrifice an artifact **and** a creature;
   * sacrifice two differently qualified permanents;
   * sacrifice a creature **or** discard two cards, with branch-specific objects.

   Each sacrifice atom should carry or reference its own selector.

3. Only the first outlet is returned.

   `parse_structured()` returns one record. A portable card parser should return a list because a card or face can contain multiple sacrifice clauses.

4. “Held out” is not independently auditable from this commit.

   Parser, split, expected answers, and results arrived together. For future validation, freeze the parser in one commit, then add the unseen fixture and adjudication in a subsequent commit.

5. These are agent-authored reference annotations, not the independent human gold set.

   They are much better than the previous self-labeled adversarial cases, but should not be described as independent semantic validation.

Recommended next bounded slice:

* Adjudicate all 50 FIN texts containing “sacrif” as outlet/non-outlet.
* For every true outlet, annotate every clause—not merely one per card.
* Change the API to `extract_all() -> list[Clause]`.
* Attach a selector to each sacrifice cost/effect atom.
* Report set-wide detection precision/recall, clause-level exact match, and per-field accuracy.
* Preserve the current six held-out cases unchanged while fixing the three known parser errors.

So: the commit genuinely advances portability and answers most of the prior review. It does not yet establish a complete FIN sacrifice extractor, but it now provides the right foundation for measuring one.
