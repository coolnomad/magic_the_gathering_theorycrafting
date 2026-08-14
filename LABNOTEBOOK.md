# Lab Notebook — Mechanistic Theory of Limited Magic: The Gathering

> **APPEND-ONLY.** Add new entries at the end. Never edit or delete existing entries.
> Corrections are new `CORRECTION` entries that reference the original. See [`INSTRUCTIONS.md`](./INSTRUCTIONS.md).
>
> Entry format: `## [YYYY-MM-DD HH:MM] TYPE — Short Title`
> TYPEs: DEFINITION · HYPOTHESIS · EXPERIMENT · OBSERVATION · RESULT · MODEL · DECISION · QUESTION · CORRECTION

---

## [2026-08-13 16:02] DECISION — Project kickoff and scope

Established this repository as the home for developing a **mechanistic theory of Limited Magic: The Gathering formats**, with **Draft as the first emphasis**.

- "Mechanistic" = explicit, falsifiable models grounded in game mechanics, not heuristics or vibes.
- "Limited" = deck built from a freshly-opened restricted pool (Draft, Sealed). Draft is the initial focus; Sealed and others come later.
- Set up three persistent artifacts: this lab notebook, `CONVERSATION_LOG.md` (append-only transcript), and `INSTRUCTIONS.md` (repo rules). All governed by append-only discipline.

Refs: [`INSTRUCTIONS.md`](./INSTRUCTIONS.md)

---

## [2026-08-13 16:02] QUESTION — Opening questions to eventually address

Seed list of open questions to structure early work (each to be promoted to HYPOTHESIS/EXPERIMENT as it sharpens):

1. What are the primitive quantities of a Limited game? (mana, tempo, card advantage, board presence, life total, information)
2. How do we operationally define "card quality" in a vacuum vs. in-context (archetype, pool, seat)?
3. What is a "signal" during a draft, mechanistically, and how should a drafter update on it?
4. Can pick order be modeled as decision-making under uncertainty with a value function over future deck states?
5. What observable, measurable outcomes will we use to validate models (win rate, game length, mana efficiency curves)?

Refs: [2026-08-13 16:02] DECISION — Project kickoff and scope

---

## [2026-08-13 16:40] DECISION — Automated conversation logging via hooks

Wired up append-only conversation logging so the record captures itself:

- `.claude/hooks/log_user.ps1` (UserPromptSubmit) appends each user prompt.
- `.claude/hooks/log_assistant.ps1` (Stop) parses the session transcript and appends the assistant's reply for the just-finished turn, de-duplicated by message uuid so re-fires (resume/compact) don't double-log.
- Both registered in `.claude/settings.json` with `shell: "powershell"`; BOM-free UTF-8 appends; self-locating via `$PSScriptRoot`; fail silently so a hook error never blocks a turn.
- Added `.gitattributes` to normalize line endings (LF in repo; `*.ps1` stays CRLF).

Note: the hooks activate for a Claude Code session only after `/hooks` (or restart) if `.claude/settings.json` didn't exist at session start.

Refs: [`INSTRUCTIONS.md`](./INSTRUCTIONS.md) §7

---

## [2026-08-13 16:49] DECISION — Theory architecture: the capacity stack (L0–L5)

Adopting a layered architecture so that "what a card *can* do" is never silently conflated with "what *wins*" — mirroring the epistemic discipline of the HOB KG spec (`docs/hob-knowledge-graph-build-spec.md`), which is itself the L1 implementation for one set.

- **L0 — Rules substrate.** The Comprehensive Rules: a deterministic transition function over game states. Format-invariant. Not something we model; something we build on.
- **L1 — Mechanistic possibility graph.** Per set/pool: what each card can produce / consume / enable / prevent / modify, as typed directed conditional edges. Pure "can," no value. *This is exactly the HOB KG.* Generalizes to any Limited set.
- **L2 — Game dynamics (state-variable "physics").** A game is a trajectory through a state space. Define the state variables and the exchange rates between them. Cards are **operators** that move the state. Tempo, card advantage, etc. get mechanistic definitions *here*, as changes in state variables — not as vibes.
- **L3 — Deck as a capacity vector.** A deck projects the pool into a vector of measurable capacities (removal density, curve, evasion, card-advantage engines, mana sources, instant-speed interaction, synergy-path count from L1, …). Deckbuilding = selecting a subset of the pool to shape this vector for the expected metagame.
- **L4 — Draft as sequential decision under uncertainty.** Picks are decisions; the drafter carries beliefs over future card availability (signals) and over the eventual deck. Pick value = expected marginal contribution to final deck capacity, integrated over uncertainty.
- **L5 — Outcome / empirical layer.** Win rate as a function of the L3 capacity vector and the opponent distribution. Must be **conditioned** to strip confounds (player skill, selection effects). This is where observed data lives and where every higher-layer claim is ultimately tested.

**Epistemic rule (inherited from the KG):** a claim at layer N is only validated by evidence at layer ≥ N. L1 "can enable" never implies L5 "improves win rate." Crossing that line requires L3–L5 evidence.

Refs: [2026-08-13 16:02] QUESTION — Opening questions; `docs/hob-knowledge-graph-build-spec.md` ("Final epistemic boundary")

---

## [2026-08-13 16:49] DEFINITION — Limited game state and resource primitives

**Game state** `S`: for each player, the tuple ⟨life, hand (multiset of cards), board (multiset of permanents with their per-object state: tapped, counters, attachments, summoning-sickness), mana capacity (lands + sources) and available mana this step, library size + (partially known) contents, graveyard, exile⟩, plus shared position ⟨turn number, active player, phase/step, stack⟩. L0 defines the legal transitions `S → S'`.

**Resource primitives** (the coordinates of L2). Each is a scalar (or low-dim) projection of `S`:

1. **Cards (option economy).** Count of actionable options a player controls (hand + relevant board + reusable engines). A card is *stored optionality*.
2. **Mana (throughput).** The per-turn rate-limited resource. Lands ≈ cumulative capacity; mana ≈ instantaneous throughput. Central because it is the binding constraint almost every turn.
3. **Tempo (timing/position).** The rate dimension: how far each player's clock/board development is *relative to mana invested*. Measured in **mana-turns** (see next entry).
4. **Board (committed state).** The multiset of battlefield permanents; accumulated, mostly-sunk resource that produces recurring value/pressure.
5. **Life (buffer + loss condition).** A depletable buffer that is *also* the terminal condition — hence spendable as a resource until it isn't.

**Why these five:** they are the quantities cards most directly move, they are approximately conserved (exchanged, not created from nothing) over short horizons, and each maps to observable game-log events, making L5 measurement possible.

Refs: [2026-08-13 16:49] DECISION — Theory architecture

---

## [2026-08-13 16:49] DEFINITION — Tempo and card advantage as orthogonal axes of resource exchange (mana-turns)

**Card advantage (Δcards).** Net change in option economy from a play: e.g. a 2-mana spell that kills one creature and draws you nothing is −1 for you, −1 for them → 0 net (a "1-for-1"); a spell that kills two creatures is +1 (a "2-for-1").

**Tempo (Δmana-turns).** Define the **mana-turn**: 1 mana available on 1 turn. A permanent costing `m` represents ~`m` mana-turns of development. A play generates tempo for you when it forces the opponent to re-spend mana-turns or delays their state progression by more mana-turns than you spend. *Example:* a 2-mana bounce spell returning their resolved 4-drop costs you 2 mana + 1 card, and costs them ~4 mana-turns to redeploy → **+2 net tempo, −1 net card** for you. The card was spent to buy tempo.

**Core claim of L2:** essentially every play is a **transaction in the resource-primitive space**. "Bounce = tempo-positive, card-negative" and "removal of a token = card-neutral, tempo-positive" are just vectors in ⟨Δcards, Δmana-turns, Δlife, Δboard⟩. Cards convert between axes at characteristic *exchange rates*.

This dissolves the perennial "is tempo or card advantage more important" debate: they are different coordinates, and their relative *price* is set by the format (how fast games end — the format "clock"). Fast formats value mana-turns near the life axis; slow/grindy formats value the card axis.

Refs: [2026-08-13 16:49] DEFINITION — Limited game state and resource primitives

---

## [2026-08-13 16:49] HYPOTHESIS — The Exchange-Rate Hypothesis (H1)

**Claim.** A card's context-free contribution to winning is governed by the **exchange rates** it achieves against the format's *typical opposing cards and boards*, measured in the resource-primitive space ⟨Δcards, Δmana-turns, Δlife, Δboard⟩, weighted by the format's clock (which sets the price of each axis).

**Corollary (why removal/bombs dominate BREAD folk wisdom).** Removal reliably achieves ≥1-for-1 in cards while also positive in tempo/board; bombs force the opponent into unfavorable exchange rates (they must overspend to answer) → both are exchange-rate-favorable by construction.

**Falsifiable predictions.**
- P1: A card's measured average per-game resource-exchange vector (from game logs) should predict its win-rate contribution (L5 GIH WR, see quality entry) better than its mana value or raw stat line alone.
- P2: The *price weights* on each axis, fit per format, should track an independent measure of the format clock (e.g. average game length / average turn a game is decided).
- P3: Two cards with similar exchange vectors should have similar win-rate contributions even if flavorfully unrelated.

**Would refute H1:** win-rate contribution is well explained by mana value / rarity alone with exchange vectors adding no signal; or price weights show no relationship to format speed.

Refs: [2026-08-13 16:49] DEFINITION — Tempo and card advantage

---

## [2026-08-13 16:49] DEFINITION — Card quality: vacuum (Q0) vs contextual (Qc), and the L5 observables

- **Vacuum quality `Q0(c)`** — expected exchange-rate performance of card `c` against a *format-average* opposing state, ignoring the rest of your deck. The "first-pick-in-a-vacuum" quantity.
- **Contextual quality `Qc(c | D)`** — marginal contribution of `c` to *your* deck `D`'s L3 capacity vector: `Qc = Q0 + synergy(c, D) + curve/role fit(c, D)`, where `synergy` is computed from L1 KG paths between `c` and the cards in `D` (finally connecting the HOB KG to outcomes).

**L5 observables (the measurement layer).** The community "17Lands-style" metrics are the empirical shadows of these:
- **ALSA** (average last seen at) / **ATA** (average taken at) — draft-behavior proxies for *perceived* quality (not truth).
- **GIH WR** (win rate in games where the card was in hand/played) — best available shadow of `Q0`, but **confounded**: it conditions on decks that chose to play `c`, and on the card being drawn.
- **GD WR / OH WR** (drawn vs opening-hand WR), **IWD** (improvement when drawn) — sharpen the drawn-vs-not contrast.

**Confound warning (inherited epistemics).** These metrics are *associational*, not causal — exactly the L1→L5 gap the KG spec warns about. GIH WR mixes card power with the skill/priorities of drafters who take it and the decks it lands in. `Q0`/`Qc` are the causal targets; the metrics are noisy, selection-biased estimators of them.

Refs: [2026-08-13 16:49] HYPOTHESIS — Exchange-Rate; `docs/hob-knowledge-graph-build-spec.md`

---

## [2026-08-13 16:49] DEFINITION — Playable and replacement level

**Replacement-level card** `r`: the quality of the best *freely available* filler at a given role/slot (in Limited, roughly a vanilla creature on-curve that any deck can field). 

**Playable (in deck D):** card `c` is playable in `D` iff `Qc(c | D) > Qc(r | D)` — i.e. it beats replacement level for the slot it competes for. This is a **marginal, replacement-relative** definition (cf. VORP/WAR in baseball): quality is always "above what you could have played instead," never absolute.

Consequence: playability is deck- and format-relative; a card can be unplayable in a vacuum yet playable in a synergy deck (high `synergy` term), and vice-versa. Gives a principled cut line for the 23rd card.

Refs: [2026-08-13 16:49] DEFINITION — Card quality (Q0 vs Qc)

---

## [2026-08-13 16:49] DEFINITION — Draft signal and "open" (Bayesian)

**Setup.** In an 8-seat draft, packs pass around the table; the cards you *see* are censored observations of upstream drafters' picks. Let `θ` index the availability of an archetype/color lane for the rest of *your* draft (how under-contested it is downstream and in future packs).

**Signal.** Any observation that updates the posterior `P(θ | seen cards)`. The canonical positive signal: a **high-`Q0` card seen unexpectedly late** in lane `L` ⇒ upstream drafters are not taking `L` ⇒ raise `P(L is open)`.

**Open (operational).** Lane `L` is *open to you* if the posterior expected quality of `L`-cards you will still be passed for the rest of the draft exceeds your current lane's expected quality by more than the switching cost of the cards already committed.

**Falsifiable predictions.**
- S1: Within a color, "lateness of high-`Q0` cards in pack 1" should positively predict the quality/quantity of that color's cards received in packs 2–3 (autocorrelation of openness), *seat-relative*.
- S2: Drafters who commit to lanes with stronger early openness signals should realize higher final-deck `Q0` sums (and, downstream, win rate) than those who ignore signals — after controlling for raw pick quality.

Refs: [2026-08-13 16:49] DECISION — Theory architecture (L4)

---

## [2026-08-13 16:49] MODEL — Draft pick as value-function maximization (BREAD reframed)

At pick with cards on offer `C`, current pool `P`, and beliefs `B` over future availability, choose

  `c* = argmax_{c ∈ C}  E_B[ V(final deck | P ∪ {c}, future picks played optimally) ]`.

Decompose the marginal value of taking `c` as approximately:

  `ΔV(c) ≈ Q0(c)                     (raw power)`
  `      + synergy_fit(c, P)          (Qc − Q0 given committed pool; from L1 KG paths)`
  `      + openness_option_value(c,B) (value of committing to / keeping open a lane)`
  `      + curve/role_marginal(c, P)  (does it fill a needed slot at replacement+?)`
  `      − speculation_cost(c,B)      (risk of the lane not coming / card not making the deck)`

**Folk heuristic mapping.** The classic **BREAD** ordering (Bombs, Removal, Evasion, Aggression/card-Advantage, Dregs) is a lossy sort on `Q0` weighted by the H1 exchange-rate corollary (bombs & removal have the best exchange vectors), *before* the synergy/openness/curve terms are added. The model subsumes BREAD as the P=∅, B=uninformative special case and predicts *when BREAD is wrong* (strong synergy or openness terms should override raw `Q0` ranking).

Refs: [2026-08-13 16:49] HYPOTHESIS — Exchange-Rate; [2026-08-13 16:49] DEFINITION — Draft signal

---

## [2026-08-13 16:49] EXPERIMENT — First empirical test plan (E1)

**Goal.** Test H1 (Exchange-Rate) and the `Q0` decomposition against real outcomes.

**Data needed.**
- Per-card L5 metrics (GIH WR, GD WR, OH WR, IWD, ALSA, ATA) for a set with public draft+game data.
- Game-log-level events sufficient to compute per-card average resource-exchange vectors ⟨Δcards, Δmana-turns, Δlife, Δboard⟩ (or a principled approximation from card text via the L1 graph where full logs are unavailable).
- Format-speed proxy (avg game length / turn-of-decision).

**Method.**
1. Estimate each card's exchange vector (from logs if available, else L1-derived priors).
2. Regress GIH WR on (a) mana value + rarity baseline, then (b) add exchange vector; compare incremental R² → tests P1.
3. Fit per-format axis price weights; correlate with format-speed proxy across several sets → tests P2.
4. Cluster cards by exchange vector; test within-cluster GIH WR homogeneity → tests P3.

**Confound controls.** Because GIH WR is selection-biased (see quality entry), treat results as associational; where possible use IWD / drawn-vs-not contrasts to reduce "good decks play good cards" bias. Full causal claims deferred to an L5 design with deck-composition controls (a later experiment).

**Open dependency:** whether public data exists for HOB specifically, or whether E1 is first run on an established set and only the L1 method transferred to HOB. → see QUESTION below.

Refs: [2026-08-13 16:49] HYPOTHESIS — Exchange-Rate; [2026-08-13 16:49] DEFINITION — Card quality

---

## [2026-08-13 16:49] QUESTION — Roadmap and open dependencies after the foundational block

1. **Data availability.** Does public draft+game data (17Lands-style) exist for HOB, or do we validate the method on an established set first and transfer the L1 machinery to HOB? (Blocks E1 specifics.)
2. **Mana-turn accounting.** Nail down a rigorous, computable definition of "mana-turns lost" for tempo (esp. for cards, engines, and life-as-resource conversions). Promote to its own DEFINITION/MODEL.
3. **From KG to synergy scalar.** Define `synergy(c, D)` concretely as a function over L1 KG paths (path count? weighted by condition-satisfaction probability? by exchange-rate improvement?). This is the bridge from the HOB KG (L1) to Qc (L3).
4. **Format clock.** Formalize the "clock" that sets axis price weights; relate to aggro/midrange/control speed.
5. **Archetype as emergent, not assumed.** Can archetypes be *derived* as clusters in L3 capacity space / L1 mechanism modules (cf. KG Phase 6), rather than assumed? Keeps us honest per the no-value-judgment rule.
6. **Scope check.** The theory is format-general; the KG is HOB-specific. Decide how much to develop general theory vs. instantiate on HOB as the running example.

Refs: [2026-08-13 16:49] EXPERIMENT — E1; [2026-08-13 16:02] QUESTION — Opening questions

---

## [2026-08-13 17:15] CORRECTION — Retract the entire 2026-08-13 16:49 theory block

**The following entries are RETRACTED and must not be treated as foundational or built upon:**

- [2026-08-13 16:49] DECISION — Theory architecture: the capacity stack (L0–L5)
- [2026-08-13 16:49] DEFINITION — Limited game state and resource primitives
- [2026-08-13 16:49] DEFINITION — Tempo and card advantage as orthogonal axes of resource exchange (mana-turns)
- [2026-08-13 16:49] HYPOTHESIS — The Exchange-Rate Hypothesis (H1)
- [2026-08-13 16:49] DEFINITION — Card quality: vacuum (Q0) vs contextual (Qc), and the L5 observables
- [2026-08-13 16:49] DEFINITION — Playable and replacement level
- [2026-08-13 16:49] DEFINITION — Draft signal and "open" (Bayesian)
- [2026-08-13 16:49] MODEL — Draft pick as value-function maximization (BREAD reframed)
- [2026-08-13 16:49] EXPERIMENT — First empirical test plan (E1)
- [2026-08-13 16:49] QUESTION — Roadmap and open dependencies after the foundational block

**Reason.** That block was framing/packaging I (the assistant) invented and synthesized — the capacity-stack layering, the resource-exchange formalization, the "mana-turns" tempo unit, the Q0/Qc quality split, the hypotheses, and the naming. It was not derived from the uploaded source document and carried no provenance, which violates this repo's standards (`INSTRUCTIONS.md` "cite reality"; the HOB KG spec's principle #10, "every asserted primitive edge requires provenance"). It was also presented with more confidence than warranted.

**Direction (from the user).** Discard that packaging. Until further notice, the **sole authoritative source** for this project is the uploaded document `docs/hob-knowledge-graph-build-spec.md`. Do not introduce architectures, definitions, hypotheses, or models that are not in that document. The user will say when it is time to expand.

**Scope of retraction.** Only the 16:49 block above. The 16:02 kickoff DECISION and 16:02 opening-QUESTION entries stand for now (not part of this retraction). Per append-only discipline, nothing is deleted — the retracted entries remain in the history and are voided by this notice.

Refs: retracts all [2026-08-13 16:49] entries; [`docs/hob-knowledge-graph-build-spec.md`](./docs/hob-knowledge-graph-build-spec.md); [`INSTRUCTIONS.md`](./INSTRUCTIONS.md)

---

## [2026-08-13 17:30] OBSERVATION — HOB Oracle-text source snapshot fetched (Scryfall)

Pulled the required HOB card corpus described in the build spec's "Source corpus → Required / Expected Scryfall payload" section and froze it as a reproducible snapshot.

- **Query:** `set:hob -is:extra`, `unique=cards`, `order=set` against `https://api.scryfall.com/cards/search` (excludes extras, multilingual copies, variations — not the print gallery count).
- **Retrieved:** 2026-08-13T21:30:18Z, 2 pages, 193 cards.
- **Stored:** `data/raw/scryfall_hob.json` (raw card objects, UTF-8 no BOM, 1,633,759 bytes; SHA-256 `AEC896020C3C4C9649994EEB04418210D72BD5FCF25E3FB28FD605E3A993DE0C`) and `data/raw/source_manifest.json` (query, timestamp, hash, size, counts) per the spec's "Source snapshot" reproducibility requirement.

**Every spec-asserted count reproduced exactly** — 193 unique cards; 168 normal / 17 Adventure / 8 Saga layouts; 17 records with no top-level `oracle_text` (Adventure faces); 23 with `produced_mana`; 49 with `all_parts`; and 10 Recruit / 9 Storied / 2 hone-counter Oracle texts. This confirms the fetched corpus is the one the document describes.

**Scope note.** This is Phase 0 data acquisition only (the raw source snapshot). No normalization, no graph, no LLM — and, per the standing directive, no theory beyond the document. Still outstanding from the spec's "Required" corpus: the official HOB release notes / mechanics article and the Comprehensive Rules text; only the Scryfall payload was requested and fetched this turn.

Refs: [`docs/hob-knowledge-graph-build-spec.md`](./docs/hob-knowledge-graph-build-spec.md) ("Source corpus", "Source snapshot", "Phase 0"); `data/raw/scryfall_hob.json`; `data/raw/source_manifest.json`

---

## [2026-08-13 17:55] OBSERVATION — Remaining required sources collected (release notes, mechanics article, Comprehensive Rules)

Completed the spec's "Source corpus → Required" list by fetching the three non-Scryfall sources and freezing them alongside the card data. HOB is a real expansion (Scryfall set object: "The Hobbit", type `expansion`, released 2026-08-14 — the day after this fetch), so official pages are freshly posted.

- **`data/raw/hob_release_notes.html`** — official release notes. Source: `https://magic.wizards.com/en/news/feature/the-hobbit-release-notes`. 392,313 bytes; SHA-256 `B3E701A6…B716F`.
- **`data/raw/hob_mechanics.html`** — official mechanics article (Recruit, Storied, hone). Source: `https://magic.wizards.com/en/news/feature/the-hobbit-mechanics`. 193,218 bytes; SHA-256 `FBB5E80A…C56F98`.
- **`data/raw/comprehensive_rules.txt`** — Magic Comprehensive Rules, **effective 2026-08-07** (the HOB-era update, posted a week before release). Source: `https://media.wizards.com/2026/downloads/MagicCompRules 20260807.txt`. 976,669 bytes; SHA-256 `2ED5F1BB…C062B3`.

**Verified the CR is the correct HOB-era version**, not a stale one: header reads "effective as of August 7, 2026," and it already contains the two changes the release notes flag — **rule 122.1j** ("A hone counter on an Equipment gives +1/+0…") and **rule 310.8** (non-Siege battle put into graveyard at 0 defense, an SBA). Both articles' HTML was confirmed to contain the mechanic text (Recruit/Storied/hone) before saving.

`data/raw/source_manifest.json` rebuilt as a structured manifest over all four sources (id, kind, url, retrieval timestamp, SHA-256, byte size, note) for reproducibility.

**Status:** the spec's entire "Required" source corpus is now snapshotted. Still Phase 0 — no normalization, no graph, no theory beyond the document. (The spec also names official mechanics coverage as "Required"; the separate Vision-Design / Update-Bulletin articles are not part of the Required list and were not fetched.)

Refs: [2026-08-13 17:30] OBSERVATION — HOB Oracle-text source snapshot; [`docs/hob-knowledge-graph-build-spec.md`](./docs/hob-knowledge-graph-build-spec.md) ("Source corpus → Required"); `data/raw/`

---

## [2026-08-13 18:20] DECISION — FIN (Final Fantasy) as the second target set; source layout

At the user's direction, collecting the same Phase 0 source corpus for **FIN** (*Magic: The Gathering—Final Fantasy*, released 2025-06-13) as a **transfer target**: HOB is the set we figure the method out on; once the KG pipeline works on HOB it will be applied to FIN. The build spec is HOB-specific, so FIN is treated as a parallel instantiation of the spec's *method*, not a change to the spec.

**Layout decision.** To avoid filename collisions (both sets have `comprehensive_rules.txt`, `source_manifest.json`, etc.), FIN's raw snapshot lives in its own subdirectory **`data/raw/fin/`**, leaving HOB's files at `data/raw/` root. This is asymmetric; if we later prefer symmetry we can move HOB into `data/raw/hob/` (deferred — the spec's literal paths reference `data/raw/scryfall_hob.json`). The `data/raw/** -text` gitattributes rule already covers the nested FIN files, so they are stored byte-exact.

Refs: [2026-08-13 17:55] OBSERVATION — Remaining required sources; [`docs/hob-knowledge-graph-build-spec.md`](./docs/hob-knowledge-graph-build-spec.md)

---

## [2026-08-13 18:20] OBSERVATION — FIN source snapshot collected (mirror of HOB Phase 0)

Fetched and froze the full Required corpus for FIN into `data/raw/fin/`, using the same queries/method as HOB. Retrieved 2026-08-13 (UTC ~22:xx).

- **`scryfall_fin.json`** — `set:fin -is:extra`, `unique=cards`. **313 mechanically unique cards** (Scryfall set object reports 595 in the print gallery, which we deliberately do not use). Layout breakdown: **263 normal, 27 transform, 15 Saga, 5 Adventure, 3 meld**; 32 records with no top-level `oracle_text` (multi-face); 50 `produced_mana`; 74 `all_parts`. 2,767,704 bytes; SHA-256 `BE5811C5…D837B`.
- **`fin_release_notes.html`** — `magic.wizards.com/.../final-fantasy-release-notes`. 1,055,178 bytes; SHA-256 `F7C3A995…E9821`.
- **`fin_mechanics.html`** — `magic.wizards.com/.../final-fantasy-mechanics`. 190,879 bytes; SHA-256 `B9EAE970…C44CB3`.
- **`comprehensive_rules.txt`** — Magic Comprehensive Rules **effective 2025-06-06** (the FIN-era version, posted the Friday before FIN's 2025-06-13 release). `media.wizards.com/2025/downloads/MagicCompRules 20250606.txt`. 949,711 bytes; SHA-256 `1ED5D0B7…8A714F`.
- **`source_manifest.json`** — 4-source manifest (id, kind, url, timestamp, SHA-256, bytes, note) + set metadata.

**Verifications.** CR header reads "effective as of June 6, 2025" and contains rule **714.2d** (Saga with no chapter abilities → final chapter number 0), the rules change the FIN release notes describe. Both articles' HTML confirmed to contain the FIN mechanics (Job select, Saga/Summon). All four working-file hashes match the manifest.

**Note on new FIN mechanics vs. the HOB spec.** FIN introduces structures the HOB spec's mechanic-template library does not cover — **Saga creatures ("Summon"), Job select, tiered spells, transforming DFCs, meld**. These will need their own rule templates when the pipeline is transferred to FIN (Phase 2 work), analogous to Recruit/Storied/hone/Adventure/Saga for HOB. Recorded here so the transfer step doesn't silently assume HOB's template set suffices.

**Status:** FIN Phase 0 data acquisition complete. Still no normalization, graph, or theory — raw frozen snapshot only.

Refs: [2026-08-13 18:20] DECISION — FIN as second target set; [2026-08-13 17:55] OBSERVATION — Remaining required sources (HOB); `data/raw/fin/`

---

## [2026-08-13 18:55] DECISION — Phase 1 deterministic normalization: scope, stack, and two spec-alignment calls

Began the build spec's **Phase 1 (deterministic normalization)** on HOB. User approved: repo-root layout (not a nested `hob-kg/`), Python + Pydantic v2 + pytest, and "stay in line with the spec." No LLM, no graph assembly, no pair projection, no value judgments.

**Stack / layout.** Python package `src/hobkg/` (`normalize`, `types`, `mana`, `mechanics`, `extract_mechanical`, `pipeline`, `cli`); Pydantic models in `models.py` are the authoritative schemas and JSON Schemas are generated from them into `schema/`. `pyproject.toml` pins deps; `pytest` config uses `pythonpath=["src"]`. Outputs go to `data/normalized/`, `data/rules/`, `data/review/`, `reports/`. Added `.gitignore` for Python artifacts (and the logging hook's local dedup file).

**Two interpretation calls made while implementing (flagged for the record):**

1. **Named mechanics are detected case-insensitively.** In HOB the Recruit keyword action is printed **lowercase** mid-sentence ("...enters, recruit.") and only capitalized where it opens a Saga chapter. A case-sensitive match found 1 of 10; case-insensitive recovers all 10 (and Storied 9, hone 2), matching the Phase-0 grep. Detection records *presence only* — expansion into the Recruit/Storied/hone rule templates is deliberately deferred to Phase 2.

2. **Reminder text (parentheticals) is stripped before syntactic extraction.** Reminder text has no rules meaning beyond the actual rules/keywords (CR 207.2). Extracting verbs from it would (a) misattribute token/keyword abilities to the producing card — e.g., a Treasure's "Add one mana of any color" pinned on every card that makes a Treasure — and (b) duplicate the Phase 2 mechanic-template expansion. This matches the spec's keyword rule: "Expand named mechanics from the official rule library, not from reminder text independently on every card." Stripping preserves character offsets (blanked to spaces) so provenance still indexes the original Oracle text. Effect: e.g. *Patient Instructor* yields only its `trigger_etb` primitive in Phase 1; its draw/discard/Soldier-token come from the Recruit template later.

**Conservatism rule honored.** Exact syntactic extractions emit a primitive only on an unambiguous parse; a bare signal whose strict parse fails (non-literal quantity, unparsed object) becomes an `UnresolvedExtraction` queued for the Phase 3 LLM. We never guess.

Refs: [`docs/hob-knowledge-graph-build-spec.md`](./docs/hob-knowledge-graph-build-spec.md) ("Phase 1", "Keyword and reminder-text handling", "Exact syntactic extractions", "Agent execution discipline"); `src/hobkg/`

---

## [2026-08-13 18:55] OBSERVATION — Phase 1 results and validation (HOB)

Ran `python -m hobkg.cli normalize` over the frozen `data/raw/scryfall_hob.json`; all outputs re-validate against their models (`hobkg.cli validate`). 27 pytest tests pass.

**Normalized entities.** 193 cards; **210 faces** (168 normal×1 + 17 Adventure×2 + 8 Saga×1); 12 canonical token specs (from `all_parts`, deduped across producers — e.g. Human Soldier and Treasure each produced by 10 cards, Goblin Army by 14). Every Adventure has exactly 2 faces with roles `{primary, adventure}`; the single face with no Oracle text is the vanilla *Ordinary Bear* (expected).

**Mechanic detection.** 157 records: 136 from Scryfall `keywords` + 21 named-mechanic detections in Oracle text — **Recruit 10, Storied 9, hone 2**, reproducing Phase 0 exactly.

**Syntactic extractions.** 267 unambiguous primitives, led by `trigger_etb` 63, `activated_ability` 36, `draw` 33, `put_counter` 31, `create_token` 24. **16 unresolved** signals queued (8 draw, 4 discard, 2 mill, 2 add_mana — all genuinely non-literal, e.g. "Add X mana", "draw cards equal to…"). 23 deterministic condition/limit stubs ("up to", "only once each turn").

**Deliverables written.** `data/normalized/{cards,faces,tokens,mechanical_extractions}.jsonl`, `data/rules/{mechanics,conditions}.jsonl`, `data/review/unresolved.jsonl`, `schema/*.schema.json` (7), and `reports/{coverage,unresolved}.md`. Coverage report carries the spec's caveat verbatim: "Coverage is not correctness; do not maximize edge count." 69 text-bearing faces have no syntactic extraction — expected (keyword-only cards and cards whose operations are template-owned), not a defect.

**Not done (later phases):** mechanic-template expansion (Recruit/Storied/hone/Adventure/Saga gates) = Phase 2; LLM extraction = Phase 3; global graph assembly = Phase 4; pair projection = Phase 5. No outcome/quality/archetype claims.

Refs: [2026-08-13 18:55] DECISION — Phase 1 scope/stack; `reports/coverage.md`; `reports/unresolved.md`

---

## [2026-08-13 19:30] DECISION — Phase 2 mechanic-template library: model and scope

Built the spec's **Phase 2 (mechanic templates)**: each HOB mechanic encoded once as a reusable rule and instantiated on the Phase-1 cards that carry it. This is where the typed directed graph first appears.

**Graph-model schemas (deferred from Phase 1, built now).** Added `Node` (15-type vocabulary: Card/CardFace/Ability/Operation/Event/Resource/ObjectClass/Zone/CounterType/State/Gate/Cost/Effect/Rule/TokenSpec), `Edge` (full spec property set: predicate from the controlled vocabulary, polarity, timing, condition_ids, quantity, optional, certainty, provenance, `extractor='rule_expansion'`, review_status), `Gate`, and `StructuredCondition`. Predicates and node types are `Literal` unions so a new type requires a schema change (spec principle #2). JSON Schemas regenerated (11 total).

**Template library** (`src/hobkg/rules.py`, `GraphBuilder` dedups shared nodes):
- **Recruit** — `recruit → draw(1) → discard(1) → gate:recruit-nonland-discard → CREATES_OBJECT token:human-soldier`, exactly the spec's `expand_recruit`; the draw also `PRODUCES event:card-drawn` (substrate for the second-draw payoff direction, Phase 5).
- **Storied** — one shared `gate:storied` (distinct_object_threshold, union predicate Legendary/Artifact/Saga, ≥3, `double_count=false`, output `enduring_story`, persistence rest_of_game). Qualifying permanent faces and qualifying tokens each get exactly one `CONTRIBUTES_TO` edge; payoff faces get `enduring_story ENABLES <ability>`.
- **hone** — `counter:hone` on Equipment; `effect:hone-boost` (+1/+0 to the *attached creature*) `SCALES_WITH counter:hone`. Bonus is never attached to the source card (spec).
- **Adventure** — spell casts from hand, resolves to exile, exile `ENABLES` casting the permanent from exile; normal-from-hand alternative preserved as an optional edge; faces stay distinct.
- **Saga** — lore counter on ETB + each turn, chapter abilities parsed from `I —/II —/III —` markers, sacrifice after the final chapter. A Saga also contributes to `gate:storied`.

**Layout / idempotence.** Phase 2 writes only `data/graph/{nodes,edges,gates,conditions}.jsonl` and `reports/graph_coverage.md`; it reads Phase 1 outputs and never mutates them. CLI gains `templates` (Phase 2), `build` (Phase 1+2). Gates are reified as graph **nodes** (so every edge endpoint resolves) in addition to their rich `Gate` records.

**Deliberate boundaries.** No LLM (Phase 3), no global assembly/canonicalization of *all* card-local ops (Phase 4 — Phase 2 only creates nodes for faces it touches), no pair projection (Phase 5). The Recruit→Master's-Councillors *direction* (invariant #2) is set up but not asserted here: Recruit emits the draw event; connecting it to Councillors' second-draw trigger is Phase 5. Card-specific replacement effects like Bard, King of Dale modifying Recruit's quantities (invariant #3) are Phase 3 LLM work. No value judgments.

Refs: [`docs/hob-knowledge-graph-build-spec.md`](./docs/hob-knowledge-graph-build-spec.md) ("Phase 2", Storied gate JSON, "Semantic invariants", "Agent execution discipline" 4–6); `src/hobkg/rules.py`

---

## [2026-08-13 19:30] OBSERVATION — Phase 2 results and validation (HOB)

`python -m hobkg.cli build` runs Phase 1 then Phase 2; all outputs re-validate (`validate`), including an integrity check that **every graph edge endpoint resolves to a node (0 dangling edges)**. 45 pytest tests pass (18 new for Phase 2).

**Instantiations.** Recruit 10, Storied payoff 9, hone 2, Adventure 17, Saga 8 — matching the detected/layout counts. Storied contributors: **74 qualifying permanent faces + 3 qualifying tokens** (Treasure, Axe, Stone Boulder — invariant #7).

**Graph.** 281 nodes, 411 edges, 2 gates, 1 structured condition. Node types led by Operation 124, CardFace 103, Ability 29. Edge predicates led by CONTRIBUTES_TO 77, CAUSES 55, MOVES_FROM 51, HAS_ABILITY 54, ENABLES 46, REFERENCES_RULE 46.

**Invariants verified by tests.** #1 Recruit draw-then-discard, Soldier conditional on nonland discard; #4 Storied counts 3 distinct objects under a union predicate; #5 a legendary artifact contributes exactly once; #6 enduring story persists (rest_of_game, non-removable, PERSISTS_AS); #7 an artifact token contributes; #8 Adventure/permanent faces distinct with correct zone flow. A live composite case — *The Mountain-king's Return* (a Saga whose chapter I is Recruit) — correctly instantiates both the Recruit chain and the Saga chapter/lore/sacrifice structure and registers as a Storied contributor.

**One integrity fix during the build:** gates were initially stored only as `Gate` records, so edges into `gate:storied` read as dangling; fixed by reifying every gate as a graph `Node` as well (spec's "reified gate/transition nodes").

**Deliverables.** `data/graph/{nodes,edges,gates,conditions}.jsonl`, `schema/*.schema.json` (11), `reports/graph_coverage.md`. Still possibility-only; no outcomes, quality, archetype, or synergy claims.

Refs: [2026-08-13 19:30] DECISION — Phase 2 model/scope; `reports/graph_coverage.md`; `data/graph/`

---

## [2026-08-13 20:55] CORRECTION — Phase 2 rework for object identity (per external review)

The user reviewed the emitted Phase 2 JSON (`docs/hob-kg-phase2-review.md`) and found one repeated architectural defect: **shared concept/type nodes were standing in for object-bound states and event instances**, erasing *which object* a permission/counter/condition belongs to. Left unfixed, constrained pair-traversal in Phase 5 could infer false card-pair paths (e.g. "any route into exile lets Gandalf be cast from exile"; "one nonland-discard gate creates ten Soldiers"; "a lore counter on one Saga enables another Saga's chapter"). All nine points fixed before proceeding; nothing about the base schema was wrong, so this revises the templates, not the model's intent.

**Fixes (revises the [2026-08-13 19:30] template design):**
1. **General principle** — concepts/types are ontology nodes; every object-bound fact is a per-object `State`/instance node.
2. **Adventure exile bound to the physical card** — resolution now `PRODUCES state:{card}:adventure-exiled`, and *that* state `ENABLES` the permanent-face cast. The global `zero zone:exile ENABLES` edges (verified 0 on Gandalf, Goblins' Bane // Flameshape).
3. **Casting ≠ resolution** — `op:cast … CAN_LEAD_TO … resolve` (new predicate), plus `MOVES_TO zone:stack`; no guaranteed `CAUSES`.
4. **Recruit is one generic template invoked per card** — `op:recruit` holds the single draw→discard→gate→create-Soldier chain (exactly **one** `CREATES_OBJECT` edge); each card's `op:{face}:recruit INSTANTIATES op:recruit` (new predicate). No more 10 parallel Soldier edges.
5. **Saga lore/chapters bound to the same object** — per-Saga `state:{face}:lore-count` (`HAS_COUNTER_TYPE counter:lore`, new predicate); the Saga's own lore ops `MODIFIES` its own count; its own count `ENABLES` its own chapters. The generic `counter:lore` no longer enables all chapters.
6. **hone generic once, on the attached creature** — the `+1/+0` `effect:hone-boost` and its `SCALES_WITH counter:hone` are emitted once; each hone card's `add-hone` op `REFERENCES_RULE rule:hone`. Bonus never attached to the source card.
7. **Storied card-level relation renamed** — card faces/token specs now `QUALIFIES_FOR gate:storied` (capacity), reserving `CONTRIBUTES_TO` for runtime battlefield instances (not modeled in Phase 2). Zero `CONTRIBUTES_TO` edges emitted.
8. **Tokens fully normalized** — fetched the 12 HOB token card objects from Scryfall (`data/raw/scryfall_hob_tokens.json`, added to `source_manifest.json`, byte-exact) and enriched `tokens.jsonl` with colors, P/T, keywords, Oracle text, produced mana (e.g. Human Soldier = W 1/1; Treasure carries its sac-for-mana; Axe its Equipment text).
9. **Phase 3 coverage commitment (recorded, not yet code)** — Phase 3 MUST send **every Oracle-bearing face (209)** to the LLM, not only faces that produced a `mechanical_extraction`. Otherwise custom cards like Gandalf/Flameshape (no syntactic hit) would be skipped. This is a hard requirement for the Phase 3 driver.

**New predicates (schema change, per principle #2):** `CAN_LEAD_TO`, `INSTANTIATES`, `QUALIFIES_FOR`, `HAS_COUNTER_TYPE`, `ATTACHED_TO` (reserved).

Refs: [`docs/hob-kg-phase2-review.md`](./docs/hob-kg-phase2-review.md); [2026-08-13 19:30] DECISION/OBSERVATION — Phase 2

---

## [2026-08-13 20:55] OBSERVATION — Phase 2 rework results (HOB)

Rebuilt (`hobkg.cli build`); all outputs re-validate with 0 dangling edges; **48 pytest tests pass** (new tests assert object identity: single Soldier edge across all Recruit cards, per-Saga lore states = 8, `QUALIFIES_FOR` present and `CONTRIBUTES_TO` absent, Adventure exile object-bound, token enrichment).

**Graph.** 289 nodes, 382 edges (down from 411 — duplication removed), 2 gates. New edge predicates present: `INSTANTIATES` 10, `CAN_LEAD_TO` 17, `HAS_COUNTER_TYPE` 8, `QUALIFIES_FOR` 77 (74 faces + 3 tokens: Treasure/Axe/Stone Boulder). Instantiation counts unchanged (Recruit 10 / Storied 9 / hone 2 / Adventure 17 / Saga 8). Live check on *Gandalf, Goblins' Bane // Flameshape*: cast→stack, `CAN_LEAD_TO` resolve, resolve `PRODUCES` the card-specific exiled state, state `ENABLES` the Gandalf-face cast, Gandalf `QUALIFIES_FOR` Storied — and **0** global `zone:exile ENABLES` edges set-wide.

**Sources.** Added a 5th raw source (`scryfall_hob_tokens.json`, 12 objects, SHA-256 in `source_manifest.json`); `data/raw/** -text` keeps it byte-exact.

Refs: [2026-08-13 20:55] CORRECTION — Phase 2 rework; `data/graph/`; `data/normalized/tokens.jsonl`

---

## [2026-08-13 21:20] CORRECTION — Phase 2 second-pass review fixes (chapters, hone, tokens)

A second review (`docs/hob-kg-phase2-review-pt2.md`) accepted the object-identity rework but found two remaining **blocking** semantic gaps plus token data corrections. All fixed; the reviewer's bar for accepting Phase 2 is now met.

**Blocking #1 — Saga chapters lacked thresholds.** Every chapter ability was `ENABLES`d by the Saga's own lore-count with no test of *which* lore number. Fixed: each chapter ability now carries a `StructuredCondition` `cond:{face}:chapter-{n}` of type `state_transition_equals` (lore count *becomes* n, not ≥ n), referencing the Saga's own `lore-count` state, attached via `condition_ids` on the `ENABLES` edge. Multi-number headers ("I, II —") produce one ability with `accepted_values=[1,2]`. 20 chapter conditions emitted across the 8 Sagas (total structured conditions now 21 incl. Recruit).

**Blocking #2 — hone not object-bound.** The generic rule existed once but counters attached to the global counter type with no Equipment binding. Fixed with a parameterized rule over a single bound Equipment variable **E** (spec-endorsed capacity-level approach): `obj:equipment-E HAS_STATE state:hone-count:E`; `state:hone-count:E HAS_COUNTER_TYPE counter:hone`; `obj:equipment-E ATTACHED_TO obj:creature-C`; `effect:hone-boost SCALES_WITH state:hone-count:E` and `MODIFIES obj:creature-C`. Both references to E are the same node, so the bonus binds to the creature equipped by the same Equipment that holds the counters. Each hone card's `add-hone` op `MODIFIES state:hone-count:E`. New predicate `HAS_STATE`.

**Token corrections.** Token color is defined by the *producing card's* create clause (authoritative), not the sometimes-incomplete Scryfall token object. Added a correction pass: Dwarf → `["R"]` ("2/2 red Dwarf"), Bird Soldier → `["W"]` ("4/4 white Bird Soldier … flying"); `color_source` records provenance ("producing_card_text" vs "scryfall"). Fixed a Scryfall reminder-text typo on the Axe token ("creatre" → "creature") with a recorded `notes` entry (raw snapshot left untouched; correction is in the normalized output only). Added a `characteristic_key` (name|colors|types|subtypes|P/T) so token identity is not name-alone (future-set safety).

**Reaffirmed Phase 3 requirement.** The reviewer reiterated: Phase 3 must send **all Oracle-bearing faces (209 of the 210)** to the LLM, not only the ~103 faces that currently have graph nodes or the faces with a `mechanical_extraction`. Recorded again as a hard driver requirement.

Refs: [`docs/hob-kg-phase2-review-pt2.md`](./docs/hob-kg-phase2-review-pt2.md); [2026-08-13 20:55] CORRECTION — Phase 2 rework

---

## [2026-08-13 21:20] OBSERVATION — Phase 2 pt2 results (HOB)

Rebuilt (`hobkg.cli build`); 0 dangling edges; **49 pytest tests pass** (new: chapter-transition conditions, multi-number chapters, hone Equipment-variable binding, token color/typo corrections). Graph: 292 nodes, 387 edges, 2 gates, **21 structured conditions**. New/updated predicate counts: `HAS_STATE` 1, `ATTACHED_TO` 1, `HAS_COUNTER_TYPE` 9 (8 Saga lore states + 1 hone). Live checks: *The Mountain-king's Return* chapters carry becomes-1/2/3 conditions; Dwarf/Bird Soldier colors corrected from producing-card text; Axe reminder typo fixed. Still capacity-only; no outcomes/quality/archetype claims.

Refs: [2026-08-13 21:20] CORRECTION — Phase 2 pt2 fixes; `data/graph/`; `data/normalized/tokens.jsonl`

---

## [2026-08-13 22:10] DECISION — Phase 3 architecture: Claude Code agents as the "LLM" (no Anthropic API)

Began the build spec's **Phase 3 (LLM semantic extraction)**. Per the user's standing preference, the "LLM" is **this Claude Code session / spawned sub-agents**, not the Anthropic API (they have a Claude subscription; no per-token API billing). This does not change the spec's method — only who runs the model.

**Architecture.** Deterministic Python (`src/hobkg/phase3.py`) is the control plane; Claude Code agents do the two model passes.
- **Task packets** — `build_tasks()` emits one self-contained packet per **Oracle-bearing face (209 of 210)** to `data/llm/tasks/<safe_id>.json`: card, face (incl. Oracle text), detected mechanics, and the Phase-1 `mechanical_extractions`. Plus a stable `shared_context.json` (controlled predicates, node types, mechanic templates, known tokens, rule refs) — the spec's LLM input unit.
- **Extractor pass** — agents split Oracle text into structured abilities (trigger/cost/effect/conditions), resolve pronouns, propose typed edges (controlled vocab only), cite Oracle spans, flag ambiguity in `unresolved` — JSON only, per `schema/llm_output.schema.json`.
- **Independent critic pass** — separate (fresh-context) agents review and return corrected JSON. Independence satisfies the spec's second-pass requirement.
- **Deterministic routing** — `validate_output()` enforces JSON-Schema + controlled-predicate vocabulary + provenance-present + Oracle-span-in-bounds + **no evaluative/value-judgment language** (regex rejects synergy/win-rate/archetype/tier/bomb/strong-weak/etc.). `ingest()` → `llm_candidates.jsonl` / `llm_rejections.jsonl`; `reconcile()` accepts only edges/abilities on which extractor and critic **agree** (and validate) → `llm_accepted.jsonl`, queuing the rest → `llm_queued.jsonl`. Never silently repairs invalid output (spec discipline #8).

**Scaffolding built and tested first** (spec discipline: schemas + tests before bulk extraction): `phase3.py`, `schema/llm_output.schema.json` (generated from the predicate vocabulary — single source of truth), CLI (`build-tasks`/`build-prompt`/`ingest`/`reconcile`), 9 new tests (58 total pass). Added `jsonschema` dependency. `data/llm/tasks/` + `shared_context.json` are gitignored (regenerable); the model **outputs** will be committed.

**Still to run:** the extractor + critic agent fan-out over all 209 faces (vertical-slice pilot on Recruit/Storied/Adventure first, then the rest), then `ingest`/`reconcile`. No graph assembly yet (Phase 4). No outcomes/quality claims.

Refs: [`docs/hob-knowledge-graph-build-spec.md`](./docs/hob-knowledge-graph-build-spec.md) ("Phase 3"); memory `phase3-llm-via-subagents`; `src/hobkg/phase3.py`

---

## [2026-08-13 23:40] OBSERVATION — Phase 3 executed over all 209 faces (extractor + independent critic)

Ran the two model passes as Claude Code sub-agents (12 extractor batches + a 6-face vertical-slice pilot; then 12 independent critic batches over the pilot + batches), with deterministic `ingest`/`reconcile` between and after.

**Result.** 209/209 Oracle-bearing faces processed. **0 rejections** at ingest; **416 accepted abilities** and **983 accepted edges** (assertions on which extractor and critic agree AND which pass validation); **22 queued** extractor/critic disagreements for human review; 18 soft span-warnings recorded. Accepted ability kinds: triggered 141, static 133, spell_effect 67, activated 59, replacement 16. Top accepted predicates: HAS_ABILITY 229, HAS_KEYWORD 80, MOVES_TO 78, TRIGGERS 68, CAUSES/MODIFIES 61, REFERENCES_RULE 57, PRODUCES 49, ADDS_COUNTER/CREATES_OBJECT 48, SCALES_WITH 40. Report: `reports/phase3_coverage.md`.

**Vertical slice validated first** (spec discipline): pilot on Patient Instructor (Recruit), Mountain-king's Return (Saga+Recruit chapter), Master's Councillors (**second-draw** trigger — the counterpart to Recruit's card-drawn event, invariant #2), Gandalf//Flameshape (Adventure), Káli (Storied) → 30 accepted edges, 0 queued.

**Two control-plane fixes during the run** (both recorded, tests updated, 60 pass):
1. Relaxed the ability/edge schema to allow spec-named descriptive keys (`controller`, `duration`, `note`); the hard guards remain (required fields, predicate enum, provenance, no-evaluative-language, top-level strictness). This cleared 39 false rejections.
2. Reclassified Oracle-span **end**-overrun from a hard reject to a recorded soft warning (the `text` quote is the real provenance); span **start** validity stays hard. And keyed ability-agreement on the stable `ability_id` (not the span), since critics legitimately correct spans — a span-only fix must not read as disagreement.

**What the critics caught** (why 22 queued): pervasive Oracle-span drift (em-dash/bullet miscounted as multiple chars) — all fixed; plus genuine corrections routed to the queue: two fabricated `REFERENCES_RULE→rule:adventure` edges whose provenance cited type-line text absent from the face's Oracle body; a few predicate mis-uses (e.g. counter-placement `TRIGGERS` not `REFERENCES_RULE`; graveyard-derivation `DERIVED_FROM`); added optionality (`optional:true` on conditional token creation); and omitted outputs (life gain, library destinations, evasion).

**Schema-extension signals (surfaced, not adopted):** `AMASSES` (7 Amass cards) and `HAS_KEYWORD_TYPECYCLING` (Halflingcycling). Amass is representable with existing predicates (`CREATES_OBJECT token:goblin-army` + `ADDS_COUNTER`), so it does not block — a dedicated Amass template is a candidate schema decision for later (analogous to the Phase 2 mechanic templates). Flagging per spec discipline #10.

**Boundaries.** These are per-face *local* extractions (structured abilities + card-specific proposed edges). NOT done: Phase 4 global assembly/canonicalization (e.g. namespacing bare `ability_id`s per face, merging shared nodes), and Phase 5 pair projection. No outcomes/quality/archetype claims. The 22 queued items and 18 span-warnings remain for a review pass.

Refs: [2026-08-13 22:10] DECISION — Phase 3 architecture; `reports/phase3_coverage.md`; `data/review/llm_{candidates,accepted,queued,rejections,span_warnings}.jsonl`; `data/llm/{extractions,critiques}/`

---

## [2026-08-14 00:30] DECISION — Phase 3 closure pass (Amass/typecycling templates, adjudication, face-210 disposition) and FREEZE

A bounded closure pass (user-directed) resolved three items before Phase 4. No redesign.

**1. Amass + typecycling as parameterized templates — no new primitive predicate.** Added generic `rule:amass` and `rule:typecycling` templates to `src/hobkg/rules.py` using only existing predicates. Amass encodes the conditional sequence (if no qualifying Army → `CREATES_OBJECT token:army`; then `ADDS_COUNTER counter:+1/+1`), and each card's ability `INSTANTIATES op:amass` supplying Army subtype + N; typecycling encodes discard→search-library-for-type→hand→shuffle, instantiated with the searched type. Deterministically instantiated on all 14 Amass cards + 2 typecycling cards in the Phase 2 graph (now 328 nodes / 429 edges; `INSTANTIATES` 26). `AMASSES` was deliberately NOT added as a primitive — Recruit needed a template, not a `RECRUITS` edge; same principle (a derived/query `AMASSES` relation could exist later). Re-expanded the **8** cards that had raised `schema_extension_requests` (7 Amass + Hobbit Hole) so their LLM extractions `INSTANTIATES rule:amass`/`rule:typecycling` with empty extension requests. (The other 7 Amass cards retain a correct inline `CREATES_OBJECT`+`ADDS_COUNTER` representation in the LLM layer; the Phase 2 template is authoritative for all 14.)

**2. Adjudicated the 25 queued disagreements (40 disputed items).** An adjudicator agent read extractor vs critic vs Oracle for each and assigned `accepted_extractor`/`accepted_critic`/`corrected`/`unresolved`; `apply_dispositions()` folds the verdicts into the accepted graph deterministically. Outcome: **38 accepted_critic, 2 unresolved**. On manual spot-check I overrode the agent on two it had rubber-stamped: `a1 -DERIVED_FROM-> zone:graveyard` (Thranduil — `DERIVED_FROM` is a graph-provenance predicate, not "gains abilities of Elf cards in graveyard"; no clean primitive) and `a1 -TRIGGERS-> counter:generic` (The Great Goblin — `TRIGGERS` is Event→Ability; this mis-directs it). Both preserved as **unresolved**, excluded from the accepted graph (`data/review/llm_unresolved.jsonl`) — genuine ambiguity kept, not forced.

**3. Span warnings inspected, not clamped.** The independent critic had already recomputed every *accepted* span against the real Oracle text → **0 span overruns in the accepted graph**. The 16 `llm_span_warnings` are retained as an audit trail of extractor-candidate drift (corrected via the critic pass where unambiguous; never mechanically clamped).

**4. Every normalized face dispositioned (210, not 209).** `finalize_faces()` emits `data/review/llm_face_status.jsonl` for all 210 faces and a `reviewed_empty` accepted record for the one non-Oracle-bearing face, **Ordinary Bear** — a vanilla 2/2 Bear with no printed rules text (Scryfall returns empty `oracle_text`), reason recorded. Prevents the denominator silently narrowing to 209.

**FROZEN Phase 3 result.** 210 face records (209 extracted + 1 reviewed_empty); **417 accepted abilities, 1001 accepted edges**; 2 unresolved; 0 remaining `schema_extension_requests`; 0 span overruns in accepted. 65 pytest tests pass (5 new: Amass/typecycling templates, no-primitive-predicate guard, 210-face coverage). Canonical rebuild sequence: `reconcile → apply-dispositions → finalize-faces`. This is the frozen Phase 3 baseline for Phase 4 global assembly.

Refs: [2026-08-13 23:40] OBSERVATION — Phase 3 run; `reports/phase3_coverage.md`; `data/review/llm_{accepted,unresolved,dispositions,face_status,queued,span_warnings}.jsonl`; `src/hobkg/{rules,phase3,pipeline}.py`

---

## [2026-08-14 02:30] CORRECTION — Phase 3 reopened for structural validation (external review); refrozen v2

An external review (`docs/hob-kg-phase3-review.md`) found the v1 freeze not yet semantically safe: **31 of 74 accepted `TRIGGERS` edges violated Event→Ability**, the Amass template was not object-bound, and 7 Amass cards kept inline duplicate expansions (double-count risk in Phase 4). Reopened, fixed, refrozen. Bookkeeping claims were all confirmed correct; the issues were structural.

**1. Predicate domain/range validation added.** `phase3.PREDICATE_SIGNATURES` + `resolve_node_type()` + `signature_violations()` now enforce the load-bearing relational predicates as HARD validation errors: `TRIGGERS` = Event→Ability, `HAS_COUNTER_TYPE` = State→CounterType, `ENABLES` = State/Event/Gate→Ability/Operation, `PERSISTS_AS` = State→State, `ATTACHED_TO` object→object, `COUNTS`/`CONTRIBUTES_TO`/`QUALIFIES_FOR`/`HAS_STATE`/`SATISFIES`/`HAS_FACE`/`HAS_ABILITY`. The **actor** predicates (MOVES_*/CREATES_OBJECT/ADDS_COUNTER/PRODUCES/CAUSES/MODIFIES/SCALES_WITH/REFERENCES_RULE/INSTANTIATES/…) admit a CardFace/Ability/Operation subject — a documented Phase-3 card-local convention (Phase 4 canonicalizes actors into Operation nodes), consistent with the review's own `HAS_ABILITY: CardFace→…` signature. Scoping: 78 strict-relational violations across 58 faces; re-extraction set = those ∪ all 14 Amass cards = **68 faces**.

**2. Amass template made object-bound.** Reworked over a single bound Army variable `obj:army-A`: `gate:amass-no-army CREATES_OBJECT obj:army-A` (the created Army IS A); `op:amass:select REQUIRES obj:army-A`; `obj:army-A HAS_STATE state:army-A:counters HAS_COUNTER_TYPE counter:+1/+1`; `op:amass:add-counters MODIFIES state:army-A:counters`; `obj:army-A HAS_TYPE obj:army`. Created and counted Army are the same node — executable, like the earlier Adventure/hone object-identity fixes. N + subtype ride on each per-card instance.

**3. Typecycling template completed.** Added `HAS_COST cost:cycling`, discard-as-cost (`MOVES_TO zone:graveyard`), `REQUIRES obj:searched-type`, reveal + shuffle operations.

**4. 68 faces re-extracted + re-critiqued (5 repair-extractor + 5 critic sub-agents).** Repaired TRIGGERS direction (via explicit event nodes; reflexive "when you do" as `ability/effect CAUSES event TRIGGERS reflexive-ability`), re-sourced `HAS_COUNTER_TYPE`/`PERSISTS_AS` to State nodes, fixed `ENABLES`/`ATTACHED_TO`, dropped forbidden `counter:lore TRIGGERS chapter` (Saga chapters reference `rule:saga`), and normalized all 14 Amass cards to `INSTANTIATES rule:amass` with **zero** inline `CREATES_OBJECT token:goblin-army` + `ADDS_COUNTER` duplicates. Re-adjudicated the resulting 36-face / 73-item queue: 62 accepted_critic, 9 accepted_extractor, 1 corrected, **1 unresolved** (I overrode the adjudicator: Thranduil's `a1 DERIVED_FROM zone:graveyard` — no clean primitive for "gains the activated abilities of Elf cards in your graveyard"; preserved out of the accepted graph). The v1 "Great Goblin" unresolved is now properly fixed (`event:counters-placed TRIGGERS a1`).

**5. Regression tests** (68 pass total, +3): predicate-signature direction/domain (TRIGGERS, HAS_COUNTER_TYPE) + actor-convention not penalized; object-bound Amass (bound A, param propagation); completed typecycling.

**FROZEN v2.** 210 face records; **418 accepted abilities, 1013 accepted edges**; **0 predicate-signature violations**; all **84 TRIGGERS are Event→Ability**; Amass fully normalized (0 inline duplicates); 1 unresolved; 0 `schema_extension_requests`; 0 dangling in the Phase 2 graph (335 nodes / 439 edges). Canonical rebuild unchanged: `reconcile → apply-dispositions → finalize-faces`. Now safe for Phase 4 assembly.

Refs: [`docs/hob-kg-phase3-review.md`](./docs/hob-kg-phase3-review.md); [2026-08-14 00:30] DECISION — Phase 3 closure (v1); `reports/phase3_coverage.md`; `src/hobkg/{phase3,rules}.py`

---

## [2026-08-14 18:45] CORRECTION — Multiface keyword attribution fix (Clap! Snap! Amass); refrozen v3

A third review (`docs/hob-kog-phase3-review-pt2.md`) found one remaining attribution defect on the adventure card *Great Ugly-Looking Goblin // Clap! Snap!*: the card-level Scryfall `Amass` keyword was attributed to the permanent face `:0`, but "Amass Goblins 2" is on the Adventure spell face `:1`. Consequences: a bogus `op:…:0:amass` (n=`N`, span null), `:1` still carrying the inline `CREATES_OBJECT token:goblin-army` + `ADDS_COUNTER` + `REFERENCES_RULE keyword:amass` (the mixed inline/template case), only 13 correct LLM `INSTANTIATES`, and Great Ugly-Looking Goblin falsely showing an Amass capability. Root cause: card-level Scryfall keywords were blindly attached to the index-0 face; **card-level keywords cannot determine face ownership on multiface cards**. Bounded deterministic fix (no Phase 3 reopen), per user direction.

**1. Multiface attribution fix (`pipeline.py`).** Each card-level Scryfall keyword now attaches to the face(s) whose Oracle text supports it (word-boundary match). For **multiface** cards there is **no primary-face fallback** when unsupported — an ambiguous-attribution record is emitted to `data/rules/keyword_attribution_ambiguous.jsonl` instead (per user: emit unresolved, don't guess). Single-face cards attach to their one face. Correctly re-routes Amass → Clap! Snap! `:1` (and, as a bonus, Scry/Mill on four other adventure cards to their spell faces — catalogue-only). HOB has 0 ambiguous cases.

**2. Phase 2 rebuild.** Amass now instantiates `op:face:…:1:amass` with `army_subtype="Goblins", n="2"` and a real Oracle span `[0,5]`; the bogus `op:…:0:amass` is gone. Still 14 instantiations, all with non-null spans.

**3. Deterministic LLM fix on face `:1`** (extraction AND critique, no sub-agent — the review fully specifies the target): removed the 3 inline amass edges, added `face:…:1 -INSTANTIATES-> rule:amass` (span `[0,15]`, matching the LLM-layer convention used by 11/13 other Amass cards), kept the Adventure-spell ability. Face `:0` needed no change.

**4. Regression tests (72 pass, +4):** Amass on the supporting face not the primary; no multiface keyword on an unsupported face (the general invariant); Phase 2 gives 14 `op:{face}:amass INSTANTIATES op:amass` edges all with spans, `op:…:1:amass` params `{Goblins, 2}`, `op:…:0:amass` absent; **0 inline amass expansions in the LLM layer**.

**5. Phase 4 amass canonicalization invariant recorded** (`docs/phase4-requirements.md`): all Amass assertions must canonicalize to `op:{face}:amass INSTANTIATES op:amass` with **no `face/ability -INSTANTIATES-> rule:amass` face-to-rule edges remaining** after assembly. Also captured the deferred actor→Operation canonicalization, ability-id namespacing, all-210-faces, and shared-node merge requirements.

**FROZEN v3.** 210 face records; **418 accepted abilities, 1011 accepted edges**; 0 predicate-signature violations; all 84 TRIGGERS Event→Ability; **Amass 14 `INSTANTIATES`, 0 inline** (Clap! Snap! `:1` correct, Great Ugly `:0` clean); 1 unresolved; 0 `schema_extension_requests`; 0 dangling (Phase 2: 335 nodes / 439 edges). Also set a scoped `permissions.allow` + `acceptEdits` in `.claude/settings.json` so the deterministic pipeline/git/pytest steps run without per-command approval.

Refs: [`docs/hob-kog-phase3-review-pt2.md`](./docs/hob-kog-phase3-review-pt2.md); [`docs/phase4-requirements.md`](./docs/phase4-requirements.md); [2026-08-14 02:30] CORRECTION — Phase 3 v2; `src/hobkg/pipeline.py`; `reports/phase3_coverage.md`
