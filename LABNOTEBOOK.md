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
