# Portability tracer bullet #2 — structured sacrifice schema on real FIN Oracle text

Structured sacrifice-clause schema + parser + a non-tautological field-by-field scorer, validated on **real, source-provenanced** *Final Fantasy* (FIN) Oracle text (`data/raw/fin/scryfall_fin.json`; every fixture record carries its Scryfall `id` and its text is byte-identical to source). Expected structures are adjudicated **to the rules, not to the parser** — and are **agent-authored reference annotations, NOT an independent human gold set** (review pt1 #5).

## PRIMARY — set-wide FIN evaluation (every face containing “sacrif”)

Detection is over ALL adjudicated FIN faces; clause-level exact match is the primary quality metric (per-field micro accuracy is secondary — it is inflated by easy default fields such as `modal=False` / empty lists / `restriction_timing=None`).

- faces adjudicated: **50**  (TP 26 · FP 4 · FN 1 · TN 19)
- **detection precision 86.7% · recall 96.3%** (outlet vs non-outlet)
- **clause-level exact match: 25/28 = 89.3%**  ← primary
- per-field micro accuracy: 374/392 = 95.4% (secondary/diagnostic)
- false-positive faces (parser saw an outlet, adjudication did not): ['Sleep Magic', 'Undercity Dire Rat', 'Tellah, Great Sage', 'Magic Pot']
- false-negative faces (adjudicated outlet the parser missed): ['Quina, Qu Gourmet']
- faces with any clause/field error: ['Sleep Magic', 'Sephiroth, One-Winged Angel', 'Undercity Dire Rat', 'Quina, Qu Gourmet', 'Tellah, Great Sage', 'Magic Pot', 'Eden, Seat of the Sanctum']

## Regression sets (parser tuned/known — not fresh evidence)

- DEV (11 curated, parser tuned to these): 11/11 cards exact, 100.0% fields.
- HELD-OUT (the original 6 pt#2 cases, now with the three known parser errors fixed): 6/6 cards exact, 100.0% fields. These previously exposed self-`this creature` type-leak, dual `enters or attacks` trigger, and multi-symbol mana `{1}{B}` — all now fixed and kept as regression fixtures.

## HELD-OUT regression detail

The six pt#2 held-out cards (unchanged text).

- cards: **6**  · fully-correct (all fields): **6**
- field accuracy: **84/84 = 100.0%**

### Qiqirn Merchant  ·  FIN #65  ·  `a75a6ecc-a6a5-462c-bd92-ae57dde9b965`
- score: **14/14**  — all fields correct

### Sephiroth, Fabled SOLDIER  ·  FIN #115  ·  `85eaf5e7-77dc-4842-a70c-ce4ac7f724df`
- score: **14/14**  — all fields correct

### Yiazmat, Ultimate Mark  ·  FIN #119  ·  `c3eb2ae5-10de-4c3d-91c8-8734befc80b2`
- score: **14/14**  — all fields correct

### Braska's Final Aeon  ·  FIN #104  ·  `4ec91fe8-b3da-47fa-b45e-94b62a260aba`
- score: **14/14**  — all fields correct

### Summon: Anima  ·  FIN #120  ·  `aa4f6703-21f8-4c29-ad5a-5afb54188ade`
- score: **14/14**  — all fields correct

### Blazing Bomb  ·  FIN #130  ·  `70f47277-ca47-428a-808f-0fb32e820a71`
- score: **14/14**  — all fields correct

## What this establishes (and does not)

- The structured schema (cost = `ALT`-of-`ALL` with a **selector on each sacrifice atom**; selector-internal `or_types`; `actor`; `ability_context` incl. dual triggers; timing restriction) represents real FIN sacrifice clauses; `extract_all()` returns EVERY clause on a face; the parser flags what it cannot model rather than mislabelling it.
- It does **not** yet establish a complete portable extractor: the set-wide false positives / false negatives / imperfect faces above are the measured backlog.
- These are agent-authored reference annotations, not independent human semantic validation. The frozen HOB **data/graph layers are untouched** (read-only parser).
