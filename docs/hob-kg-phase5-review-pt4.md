Commit [`e7a2b15`](https://github.com/coolnomad/magic_the_gathering_theorycrafting/commit/e7a2b15) is a major improvement, but the augmented projection is not ready to freeze.

All 119 tests pass. The earlier directions are corrected, exact Oracle spans are now verified, existing mechanical relations are screened, and extractor/critic passes are present. The nine discovered relationships are generally plausible. The remaining defect is that six of them still lack faithful typed paths.

## Incorrectly “grounded” paths

### Gollum → Master of Lake-town

The real mechanism is:

```text
Gollum causes opponents to lose life
→ life-loss event
→ Master of Lake-town triggers
→ affected opponent mills cards
```

The stored path instead says:

```text
Gollum PRODUCES resource:card
→ ENABLES_TRIGGER
→ Master PRODUCES resource:card
```

That connects their unrelated card-draw effects. It does not represent the accepted mechanism.

### Gandalf → Elrond

The real mechanism is:

```text
activate Gandalf’s creature ability
→ creature-ability-activation event
→ triggers Elrond
→ draw a card
```

The stored path instead joins:

```text
Gandalf PRODUCES resource:card-in-hand
→ ENABLES_TRIGGER
→ Elrond PRODUCES resource:card-in-hand
```

Again, shared output is being mistaken for the triggering event.

The root cause is `_build_path()`: its generic beneficiary predicate set includes `PRODUCES` and `CAUSES`. Therefore, two cards producing the same output can be assembled into an `ENABLES_TRIGGER` path even when neither production triggers the other.

## Four accepted paths are semantic shortcuts

These are stored as direct derived card-to-card bridges:

* Great Ugly-Looking Goblin → The Great Goblin;
* Reverent Howl → The Master of Lake-town;
* Rage into the Valley → The Master of Lake-town;
* The Sackville-Bagginses → The Master of Lake-town.

The relationships are credible, but a single derived card-to-card edge is not the promised “primitive-grounded path.” Each should enter a graph-repair queue that adds or canonicalizes the missing intermediate event:

```text
counter placed on Goblin/Orc/Army
life lost by player
creature ability activated
```

Then normal mechanical projection should derive the pair relation.

At present, only the three Bard `AMPLIFIES_EFFECT` paths are faithful typed paths:

```text
Bard REPLACES event:draw
→ beneficiary CAUSES event:draw
```

## Critic agreement remains too weak

Reconciliation currently requires only:

```python
critic.verdict == "RELATION"
```

It does not require agreement on:

* relation type;
* connecting concept;
* enabler/direction;
* mechanism grounding.

The current accepted extractor/critic records happen to agree on these fields, but the validator would accept disagreement. Require equality after canonical direction normalization, and independently validate the critic’s spans too.

## Audit coverage is incomplete

The current files contain:

```text
143 candidates
94 extractor verdicts
94 critic verdicts
49 unaudited candidates
```

All 49 unaudited candidates are shared-vocabulary candidates. That is acceptable for a staged pass, but the report should say “94/143 audited” rather than implying completion.

## Copy candidate logic is still conceptually wrong

The new selector pairs The Notary Hobbits with 23 unrelated token-producing cards. But Notary copies itself—it does not copy their tokens. Extractor and critic correctly reject all 23.

The useful interactions are instead cards affected by:

```text
two token Halfling creature copies entering
additional Halflings controlled
creature tokens entering
multiple permanents entering simultaneously
```

Candidate construction should derive what the copy effect produces, not pair every copier with every token creator.

## Required closure

1. Define relation-specific path signatures:

```text
ENABLES_TRIGGER:
A → event E → TRIGGERS → B ability

AMPLIFIES_EFFECT:
A → REPLACES/MODIFIES E ← CAUSES/PRODUCES ← B

SUPPLIES_RESOURCE:
A → PRODUCES R ← CONSUMES/REQUIRES ← B
```

2. Require grounding spans to overlap the provenance of the selected primitive edges.

3. Route valid relations lacking a complete primitive path to `requires_graph_repair`; do not emit a semantic card-to-card shortcut.

4. Require extractor–critic agreement on the normalized relation tuple.

5. Report candidate coverage explicitly.

6. Replace the generic copy-candidate rule with output-aware candidates.

7. Audit the remaining 49 candidates.

Verdict: the semantic discoveries are useful—probably nine real missed relations—but only the three Bard relations currently meet the typed-path standard. The other six should drive repairs to the primitive graph, after which they can be reprojected mechanically.
