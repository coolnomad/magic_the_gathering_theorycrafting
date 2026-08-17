# Portability tracer bullet — deterministic sacrifice-clause extractor

## 1. Reproduce the frozen HOB catalogue (no card-specific hardcoding)

- accepted HOB outlets: **9**  · extracted: **9**  · reproduced (core fields): **9**
- **reproduces the catalogue exactly**: True  (mismatches: 0, spurious: 0)
- the parser is pure Oracle text — it never looks at a face-id.

## 2. HOB assumptions exposed by the adversarial second-set fixture

The HOB-tuned parser was run over 10 adversarial clauses. Each exposes a HOB assumption baked into the parser (a `MISS` = returned nothing; `INCOMPLETE` = returned a record but dropped/misread part of the clause):

- **Devour Ritual** — `MISS (returned nothing)`
  - clause: _generic 'permanent' — no card type named_ — a portable extractor should: recognize 'permanent' as any permanent type
  - **HOB assumption**: Fodder type is a fixed card-type enum — the generic 'permanent' is unhandled.
- **Goblin Bombardier** — `MISS (returned nothing)`
  - clause: _subtype/tribe fodder_ — a portable extractor should: recognize the subtype 'Goblin'
  - **HOB assumption**: Only card types are recognized — subtypes/tribes (Goblin, Dwarf) are not.
- **Twin Offering** — `MISS (returned nothing)`
  - clause: _fixed count > 1_ — a portable extractor should: capture quantity 2
  - **HOB assumption**: Exactly one permanent is sacrificed (a/an/another) — fixed counts >1 are missed.
- **Any-Color Cantor** — `MISS (returned nothing)`
  - clause: _sacrifices itself ('this')_ — a portable extractor should: recognize self-sacrifice ('this'/'~')
  - **HOB assumption**: Fodder is a separate object — self-sacrifice ('this'/'~') is unhandled.
- **Bitter Bargain** — `INCOMPLETE (returned a record but non-mana OR alternative (discard))`
  - clause: _non-mana OR alternative (discard)_ — a portable extractor should: record the 'or discard a card' alternative, not just 'or pay {N}'
  - **HOB assumption**: An OR alternative is only 'pay {mana}' — non-mana alternatives (discard/exile) are dropped.
- **Culling Rite** — `INCOMPLETE (returned a record but conjunctive AND cost)`
  - clause: _conjunctive AND cost_ — a portable extractor should: distinguish AND (both) from OR (either)
  - **HOB assumption**: Multiple types are read as OR (either) — conjunctive AND (both) is misread.
- **Diplomatic Purge** — `MISS (returned nothing)`
  - clause: _qualified type phrase_ — a portable extractor should: handle 'nonland permanent' qualifier
  - **HOB assumption**: Bare card types only — qualified phrases ('nonland permanent') are unhandled.
- **Cruel Edict II** — `MISS (returned nothing)`
  - clause: _another player sacrifices (edict), not the controller_ — a portable extractor should: capture WHO sacrifices (each player / target opponent), not assume the controller
  - **HOB assumption**: The activating player is assumed to sacrifice — edicts (each/target player sacrifices) are not captured.
- **Ritual of the Machine** — `INCOMPLETE (returned a record but activation timing/frequency restriction)`
  - clause: _activation timing/frequency restriction_ — a portable extractor should: extract 'only as a sorcery' and 'only once each turn' (cf. pt10.md #2)
  - **HOB assumption**: Activation timing/frequency ('only as a sorcery', 'only once each turn') is not extracted (cf. pt10.md #2).
- **Grave Tithe** — `MISS (returned nothing)`
  - clause: _variable count X_ — a portable extractor should: capture the variable quantity X
  - **HOB assumption**: Quantity is a constant — variable counts (X creatures) are unhandled.

## 3. Minimal restructure implied (NOT the broad engine/config split)

The tracer bullet reproduces HOB with zero hardcoding, so the parser logic is already set-agnostic in shape. The gaps above imply a *small*, evidence-driven restructure — a **declarative `rules/mechanics/sacrifice.yaml` clause schema** the parser consumes, rather than a full engine split:

1. **Fodder selector** as structured data, not a `{artifact,creature}` regex: `{card_types, subtypes, supertypes, qualifiers (non…), generic 'permanent', quantity (int|variable), self ('this'/'~')}`. Covers type_enum_only / no_subtypes / no_qualifiers / quantity_* / no_self_sacrifice.
2. **Cost model** as an alternatives list, not `or_pay:{mana}`: `cost = ALT[ sacrifice(selector), pay(mana), discard(n), exile(...), … ]`. Covers or_pay_mana_only; distinguish `ALL[…]` (AND) from `ALT[…]` (OR) — covers or_not_and.
3. **Actor/controller** field on the clause (`you` | `each player` | `target opponent`) — covers controller_scope; edicts become a distinct clause kind.
4. **Activation restrictions** captured as conditions (`timing: sorcery`, `frequency: once_per_turn`, `zone`, `turn: controller`) — covers no_timing_restrictions (and is exactly the pt10.md #2 deferral).
5. **LLM escalation** only for clauses the deterministic parser flags ambiguous (unmatched selector, unknown alternative) — the harness stays the control plane.

No `engine/` vs `sets/HOB/` repo split is warranted yet: the evidence says the next unit is the sacrifice **clause schema** + selector/cost/actor/restriction parsers, validated by this same reproduce-HOB + adversarial-fixture harness.
