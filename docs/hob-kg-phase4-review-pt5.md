I checked commit [`4b1fa17`](https://github.com/coolnomad/magic_the_gathering_theorycrafting/commit/4b1fa17f6e094771485f173771b6e12ee55b7476). It correctly fixes the three previous defects, and a clean rebuild passes all 91 tests.

Two residual issues remain.

1. Mana reachability is not controller-aware

Bilbo’s Gambit now correctly avoids a direct mana-production edge, but the completeness function still finds this path:

```text
Bilbo’s Gambit → creates Treasure → Treasure produces mana
```

The Treasure belongs to the opponent. The edge itself preserves that fact in:

```json
"scope": "the promised opponent creates the token"
```

But `_face_has_mana_path()` ignores scope/controller and counts it as Bilbo having a mana path. This becomes dangerous in Phase 5: Bilbo must not be projected as enabling the owner’s mana requirements.

The graph needs participant-relative effects, such as:

```text
creates_for: controller | opponent | target_player
resource_available_to: controller | opponent
```

At minimum, the mana completeness metric should distinguish:

```text
controller_mana_path
opponent_mana_path
```

Bilbo should have the second, not the first. Conditional and optional paths should also retain those properties during projection.

2. The rebuild is not fully deterministic

Rebuilding produces the same node and edge sets, but changes their JSONL ordering. More importantly, one condition changes semantically in its stored provenance:

```text
condition: gift promised
```

Depending on iteration order, it retains either:

* the Treasure-creation provenance; or
* the spell-lock provenance.

This happens because an existing condition does not accumulate provenance from subsequent edges using the same condition ID. Both citations should be retained. Outputs should then be canonically sorted before writing.

This matters because the project describes deterministic Python as the control plane; a canonical rebuild should be byte-identical.

Minor issue: `reports/assembly.md` still calls itself “v3.”

Verdict: v4 genuinely closes the previous review. I would request a small v4.1 closure—not another broad Phase 4 reopening:

* make resource reachability participant-aware;
* preserve all provenance for shared conditions;
* sort all JSONL outputs canonically;
* add a rebuild-idempotence test;
* add a test that Bilbo provides mana to the opponent, never its controller.

After those fixes, Phase 4 is ready to freeze and Phase 5 pair projection can begin.
