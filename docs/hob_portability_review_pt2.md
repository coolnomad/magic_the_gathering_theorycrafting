The two-commit freeze/evaluate design is correct, and most requested engineering changes are present. But the set-wide evaluation has two important defects, so I would not accept the reported clause score yet.

What passed:

* Parser frozen in `a042bc3`; unseen fixture added afterward in `817cd0b`.
* All 50 FIN faces containing `sacrif` were adjudicated.
* `extract_all()` supports multiple clauses.
* Sacrifice cost atoms now carry selectors.
* Adjacent mana symbols are coalesced.
* Primary versus secondary metrics are labeled honestly.
* Agent-authored annotations are correctly distinguished from human validation.
* Face-level detection results appear internally consistent: precision 86.7%, recall 96.3%.

What needs correction:

1. Clause exact-match ignores surplus predictions.

The reported `25/28 = 89.3%` scores only expected clauses. There are 33 predicted clauses; extra predictions are not included in the denominator, and `face_perfect` does not require equal clause counts.

Using the current alignment literally:

* exact matched clauses: 25
* expected clauses: 28
* predicted clauses: 33
* clause precision: 25/33 = 75.8%
* clause recall: 25/28 = 89.3%
* clause F1: 82.0%
* fully exact faces: 42/50
* fully exact outlet faces: 23/27

2. Gaius van Baelsar’s reference annotation is wrong.

It has three modal sacrifice options:

* creature token;
* nontoken creature;
* enchantment.

The fixture expects only the first option and classifies the other two parser outputs as over-extraction. Those are real printed clauses, not false positives. Either annotate three linked modal alternatives or represent one modal effect with three selector branches.

Correcting Gaius will improve the genuine clause metrics somewhat, but they must be recomputed.

3. Subtypes remain absent from the schema.

Quina’s “Sacrifice a Frog” is correctly identified as the false negative, but the expected record also contains no `Frog` field. Even after detection is fixed, the current schema cannot preserve what may be sacrificed. Add `sel_subtypes` to:

* selector schema;
* sacrifice-atom selector signature;
* scorer;
* adjudicated fixture.

My disposition: **accept `a042bc3` as the improved frozen parser and accept `817cd0b` as the correct set-wide evaluation framework, but require a small evaluation correction before accepting its reported performance.**

The next commit should:

* fix Gaius’s modal gold annotation;
* penalize unmatched predicted clauses;
* report clause precision, recall, and F1;
* require equal expected/predicted clause counts for an exact face;
* add subtype representation and leave Quina pinned as the frozen parser’s known miss until a subsequent parser commit.

After that, the sacrifice tracer bullet will be a credible completed first portability slice.
