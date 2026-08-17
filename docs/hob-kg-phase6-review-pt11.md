The implemented pt10 scope is now correct. I do not see another blocking structural defect in the sacrifice machinery it changed.

For Snowslope Hunter specifically:

```text
Sacrifice Crude Bent Blade
→ selected object is an artifact
→ no creature-dies event
→ Crude moves battlefield → graveyard
→ Crude’s attachment terminates
→ its +2/+1 effect ends
```

If Snowslope instead sacrifices a creature:

```text
Sacrifice creature
→ sacrificed object satisfies Creature
→ creature-dies event occurs
→ applicable dies triggers can fire
```

That distinction is now encoded through `cond:completeness-sacrificed-is-creature`.

The other corrections also check out:

* Stir’s OR gate is now the sole causal parent of its sacrifice operation.
* There is no residual direct `ability → sacrifice` causal edge for Stir.
* The sacrifice branch consumes the selected permanent.
* The pay branch consumes four generic mana and no permanent.
* Both completeness and lifecycle projections traverse the OR gate.
* Allure of Power correctly uses its Adventure `:1` face.
* Sacrifice provenance now cites `CR 701.21`.
* Additional-cost provenance cites `118.8` and `601.2b/f–h`.
* The tests directly cover the OR routing, mana payment, conditional death event, provenance, and flagship Crude relationships.

The boundary is now:

* **Sacrifice eligibility:** correct.
* **Artifact-versus-creature event consequences:** correct.
* **Equipment attachment termination:** correct.
* **Stir’s alternative payment:** correct.
* **Full Snowslope ability execution:** still incomplete by explicit deferral.

Snowslope still lacks:

```text
only during your turn
AND activation_count_this_turn < 1
→ increment activation count
→ reset at turn boundary
```

and its payoff remains unwired:

```text
exile top card
→ grant permission to play it
→ expire permission at end of next turn
```

The analogous trigger timing and payoff wiring for the other sacrifice outlets also remains future work, as does portable mechanical extraction of sacrifice clauses.

So: the sacrifice relationships themselves now work correctly, including Snowslope sacrificing Crude. What remains is modeling the complete abilities around those sacrifices, not repairing the sacrifice relationships again.
