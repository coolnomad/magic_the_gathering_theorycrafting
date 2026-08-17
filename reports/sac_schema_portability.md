# Portability tracer bullet #2 — structured sacrifice schema on real FIN Oracle text

Validates the structured clause schema against small, **named, provenanced** samples of real *Final Fantasy* (FIN) cards (source: `data/raw/fin/scryfall_fin.json`; each carries its Scryfall `id`). Every card has a **manually-adjudicated** expected structured record (adjudicated to the rules, not to the parser); the parser output is scored **field by field** — a wrong or unsupported field fails.

Two splits, to answer the tracer-bullet-#1 review directly:
- **DEV** (parser tuned on these): 11/11 cards, 100.0% fields.
- **HELD-OUT** (parser frozen, never tuned on these; scored once): **2/6 cards, 95.2% fields**. This is the honest portability number.

## HELD-OUT split — the portability evidence (parser never tuned on these)

Real FIN cards chosen and adjudicated AFTER the parser was frozen. Misses are reported as-is and become backlog; they are not fixed in this slice.

- cards: **6**  · fully-correct (all fields): **2**
- field accuracy: **80/84 = 95.2%**

### Qiqirn Merchant  ·  FIN #65  ·  `a75a6ecc-a6a5-462c-bd92-ae57dde9b965`
- score: **13/14**
  - **sel_card_types**: expected `[]` · parser `['creature']`

### Sephiroth, Fabled SOLDIER  ·  FIN #115  ·  `85eaf5e7-77dc-4842-a70c-ce4ac7f724df`
- score: **13/14**
  - **ability_context**: expected `triggered_etb_or_attack` · parser `triggered_etb`

### Yiazmat, Ultimate Mark  ·  FIN #119  ·  `c3eb2ae5-10de-4c3d-91c8-8734befc80b2`
- score: **13/14**
  - **cost**: expected `["[['pay={1}{B}'], ['sacrifice=True']]"]` · parser `["[['pay={1}'], ['pay={B}'], ['sacrifice=True']]"]`

### Braska's Final Aeon  ·  FIN #104  ·  `4ec91fe8-b3da-47fa-b45e-94b62a260aba`
- score: **14/14**  — all fields correct

### Summon: Anima  ·  FIN #120  ·  `aa4f6703-21f8-4c29-ad5a-5afb54188ade`
- score: **14/14**  — all fields correct

### Blazing Bomb  ·  FIN #130  ·  `70f47277-ca47-428a-808f-0fb32e820a71`
- score: **13/14**
  - **sel_card_types**: expected `[]` · parser `['creature']`

## DEV split — the tuning set (parser was iterated to pass these)

Full marks here only demonstrate the schema can *represent* these clauses; it is train-set accuracy, not evidence of generalisation.

- cards: **11**  · fully-correct (all fields): **11**
- field accuracy: **141/141 = 100.0%**

### Cooking Campsite  ·  FIN #31  ·  `bdb5452e-d97f-409b-91d0-2664f39b09b8`
- score: **14/14**  — all fields correct

### Zack Fair  ·  FIN #45  ·  `f21f9161-5945-40da-8da0-446f6a4a1c23`
- score: **14/14**  — all fields correct

### Louisoix's Sacrifice  ·  FIN #59  ·  `4a6976f2-0bd5-449a-8fcf-f5a732ce22c1`
- score: **14/14**  — all fields correct

### Ahriman  ·  FIN #87  ·  `162a415c-5465-497e-8f4e-c6f09681641d`
- score: **14/14**  — all fields correct

### Phantom Train  ·  FIN #110  ·  `7a50d2ac-101d-41e1-b400-18fa7d2d7125`
- score: **14/14**  — all fields correct

### Cornered by Black Mages  ·  FIN #93  ·  `688fcf8a-0a44-416a-8086-83acf9a6fe69`
- score: **14/14**  — all fields correct

### Gaius van Baelsar  ·  FIN #102  ·  `a4ee8ba5-6a79-4652-b2a4-a3dae804bc28`
- score: **14/14**  — all fields correct

### Vayne's Treachery  ·  FIN #124  ·  `6de6d23b-7d42-41c1-be1c-010fe43ee586`
- score: **14/14**  — all fields correct

### Namazu Trader  ·  FIN #107  ·  `f9d25b34-990d-416c-aef7-1b5a73f19dd4`
- score: **14/14**  — all fields correct

### Zodiark, Umbral God  ·  FIN #128  ·  `9ba292d5-5139-42ea-950d-0a638445277f`
- score: **14/14**  — all fields correct

### Summon: Bahamut  ·  FIN #1  ·  `95318d85-4a08-47ac-a43d-ea83c0bea81c`
- score: **1/1**  — all fields correct

## What the FIN run establishes (and does not)

- **Establishes**: the structured schema (cost as `ALT`-of-`ALL`; selector-internal `or_types`; `actor`; `ability_context`; timing restriction) *represents* real FIN sacrifice clauses, and — the tracer-bullet-#1 review fix — the parser **flags** what it cannot model instead of silently mislabelling it (`cost_context` is never defaulted to activated; edicts are `resolution_effect` with an `actor`, not a cost).
- **Held-out misses = the measured backlog** for the next slices: dual-trigger `ability_context` ("enters or attacks"), coalescing multi-symbol mana (`{1}{B}`) into one cost atom, and any others surfaced above — each now quantified against real adjudicated second-set text rather than invented cards.
- The frozen HOB **data/graph layers are untouched**; this module is a read-only parser over `data/raw/fin/` and its own fixtures (shared loader `_load_dicts` is reused, not changed).
