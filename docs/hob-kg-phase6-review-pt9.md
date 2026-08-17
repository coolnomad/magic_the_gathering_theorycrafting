The central pt8 repair works: the Crude Bent Blade sacrifice lifecycle is now represented as a genuinely continuous traversal.

For Stir Up Trouble and Snowslope Hunter, the graph now reaches:

```text
consumer card
→ sacrifice ability
→ sacrifice operation
→ consumes Artifact
→ Crude Bent Blade
→ Crude sacrifice transition
→ terminates Crude attachment state
```

The generated paths are continuous, card-grounded, and end at the correct attachment state. The tests now verify reachability rather than merely checking that the pieces exist. The generic “leave battlefield → graveyard” operation was also correctly replaced with a cause-specific sacrifice transition, and the rules citations were corrected.

One substantive problem remains.

### Stir’s OR gate still is not executable correctly

The current structure is effectively:

```text
Stir sacrifice ability
├── REQUIRES → OR gate
└── CAUSES → sacrifice operation

OR gate
├── HAS_ALTERNATIVE → sacrifice gate
└── HAS_ALTERNATIVE → pay {4}
```

Because the ability unconditionally `CAUSES` the sacrifice operation, satisfying the `pay {4}` branch still leads to the sacrifice operation. The alternatives are now reachable, but they do not govern mutually exclusive execution.

The structure needs to be closer to:

```text
Stir additional-cost operation
→ REQUIRES OR gate

OR gate
├── sacrifice branch → executes sacrifice operation
└── pay branch → executes pay-{4} operation
```

Only the chosen branch should execute. A regression should explicitly execute the pay branch and confirm that no permanent is consumed and no attachment terminates.

Two smaller observations:

* `CardFace HAS_ABILITY op:sacrifice:H` is useful for traversal, but it is not literally an ability possessed by the Equipment. A predicate such as `CAN_UNDERGO` or a parameterized object transition would be semantically cleaner.
* `HANDOFF.md` now says seven tiers in the new section but retains stale references below to six tiers, 3,235 edges, 9,967 relations, and the old build order.

Verdict: accept the sacrifice-to-attachment-termination repair. It closes the principal Crude/Snowslope/Stir connectivity failure. Do not yet call Stir’s alternative cost autonomously executable. Portable sacrifice-clause extraction also remains open, as acknowledged.
