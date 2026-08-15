Commit [`98e514c`](https://github.com/coolnomad/magic_the_gathering_theorycrafting/commit/98e514c) correctly fixes all five defects from the previous review.

Verified:

* All 106 tests pass.
* No off-color mana projections remain.
* Island and Mountain obey colored-pip compatibility.
* Controller-owned Treasure paths are included.
* Bilbo’s opponent-owned Treasure remains excluded.
* Conditions, optionality, polarity, scope, and `creates_for` survive on individual path steps.
* Alternative mechanisms remain separate disjunctive paths.
* Real edges resolve to the stated Phase 4 edge and direction.
* Derived bridges have stable labeled IDs.
* Every path is continuous.
* Rebuilds are byte-identical.

The output is now 5,281 metaedges containing 5,914 alternative paths.

However, I found one remaining semantic blocker in `SUPPLIES_RESOURCE`.

## Participant identity is still missing for general resources

`creates_for` solves token ownership, but resource production and consumption are still joined without asking whose resource is affected.

For example, the projection contains:

```text
Well-Worn Spatula
  PRODUCES resource:life
    → SUPPLIES_RESOURCE →
Down, Down to Goblin-town
  CONSUMES resource:life
```

But these are different participants:

* Spatula gives its controller life.
* Down, Down causes the target opponent to lose life.

The controller’s accumulated life does not enable the opponent to lose life. Three plainly false projections result:

```text
Well-Worn Spatula → Down, Down to Goblin-town
Supper for Spiders → Down, Down to Goblin-town
Down, Down to Goblin-town → itself
```

By contrast, these are potentially valid:

```text
Well-Worn Spatula → Desolation Prowler
Supper for Spiders → Desolation Prowler
```

because controller life can pay Prowler’s activation cost.

Other resources have related ambiguity. For example, effects saying “that permanent’s owner draws” or “target player draws” should not automatically be interpreted as furnishing the card controller’s hand.

## Required fix

Generalize participant annotation beyond `creates_for`:

```text
resource_for:
  controller
  opponent
  target_player
  object_owner
  each_player

resource_role:
  gain
  spend
  loss
  requirement
```

Then `SUPPLIES_RESOURCE` should require compatible participants and roles:

```text
controller gain → controller spend       valid
controller gain → opponent loss          invalid
target-player gain → controller spend    conditional/unresolved
```

If Phase 4 lacks enough information to resolve the participant, either:

* retain the path as `participant_unresolved`, not an asserted supply relationship; or
* queue it for the Part 2 semantic audit.

Add regression tests for the life examples above.

The previously noted Storied class aliases also remain disconnected:

```text
obj:artifact                 vs obj:type:artifact
obj:legendary                vs obj:supertype:legendary
obj:saga                     vs obj:subtype:saga
```

That does not affect the current explicit `QUALIFIES_FOR` projection, but it should be canonicalized before richer Part 2 traversal.

Verdict: the mana and path machinery are now sound. Keep Part 1 open for one narrow participant-aware resource-flow correction; then it will be ready to freeze before the LLM pair audit.
