# Phase 3 exploration: deck representations beyond card identity

**Status: exploratory. Development rows only. No holdout read was spent** — `cycle/holdout_ledger.jsonl` still records exactly one line, by card 017. Nothing here is a benchmark result, no card was run, and every number below is contaminated by the folds that selected the models' hyperparameters. The purpose was to decide *what phase 3 should card*, before carding anything.

The headline is a negative, and it is the useful part.

> **On this dataset, card identity already extracts essentially everything the knowledge graph can name. Two mechanics chosen to span the structural extremes were captured at 82.7% and 89.6%, with the residual at the noise floor in both cases. The simplest game script does not beat the skill proxy alone. Phase 3 should not be carded as an aggregate-prediction bet.**

---

## 1. The two arms connect cleanly

The first question was whether the modelling arm's 193 card-identity features can be joined to the frozen HOB knowledge graph at all.

**193 of 193 match**, via `card_ports.jsonl` face names to `card:<oracle_id>`. The join is total. R2 is buildable.

---

## 2. What the graph offers, and what survives contact

Three candidate families were examined against benchmark §R2's requirement that features *"describe functional/mechanistic structure rather than merely relabel card identities."*

| family | source | verdict |
| --- | --- | --- |
| **ports** — typed `produces` / `consumes` / `costs` / keywords | `card_ports.jsonl` | usable; set-independent vocabulary |
| **module liveness** | `mechanism_modules.jsonl` | **design failed** — module `consumers` are mostly edges with `card: None`, so "consumers ∩ deck" is empty by construction and every module reads dead |
| **pair relation density** | `pair_index.jsonl` | **heavily contaminated** — dominated by near-universal relations |

### The anti-relabeling guard is concrete

A port type carried by **one** card *is* that card's indicator. Of 151 port types, **61 appear on exactly one card**. Requiring support on ≥5 cards leaves **54** features. With synergy-pair counts and liveness flags the prototype φ_KG was **70 dimensions** against R1's 193.

### Why raw pair density fails

Inspecting one real deck's relations showed the problem immediately:

```
Bilbo's Deadly Slice --CAN_DESTROY--> Little Bear
Bilbo's Deadly Slice --CAN_DESTROY--> ...all 8 of my own creatures
mechanical: INFRASTRUCTURE_CASTING(62)   ← lands → spells
```

A removal spell pointed at one's own board, and "you have lands." Of 35 relation types, the high-count ones fire for *any* (spell, creature) or (land, spell) pair, making the density largely a proxy for creature and land counts — which R1 already encodes. Only a filtered allowlist (`ENABLES_TRIGGER`, the sacrifice family, `CONTRIBUTES_TO_GATE`, the equip triad) is defensible, and that discards most of the volume.

---

## 3. R3, the game script — built, and null

### What it is

A Monte Carlo mana/casting simulator. Cards reduce to (cost pips, generic, land/produces); what they *do* is ignored. **It uses no graph at all** — which makes it the correct *control* for phase 3 rather than a candidate: it measures what a curve-aware encoding buys before any mechanism is involved.

Settled policy, after four iterations:

- **on the play**, no turn-1 draw; no mulligans (every hand kept)
- **tapped lands modelled** — every dual in this set enters tapped, the basics do not. A land played turn *t* that enters tapped first taps on *t+1*
- **casting is exact within the turn**, not greedy: the best *subset* by (spell count, then mana spent). Several spells in one turn only need the *combined* cost payable, so it is a subset search, not a sequence
- land drop chosen by lookahead on spells cast, tie-broken by colour coverage of the hand's pips
- turns 1–10, 400 sims per deck for the full sweep

Output is **10 turns × 9 statistics = 90 dimensions**.

### It is 7 dimensions, not 90

PCA across decks: 3 components explain 71.1%, 5 explain 84.4%, 10 explain 95.0%. **Participation ratio 7.3.** The per-turn statistics are autocorrelated by construction.

### Identity recovers about two-thirds of it

Fitting R1's 193 fractions → each script statistic, out of sample:

| statistic | ceiling | observed R² | share of recoverable |
| --- | --- | --- | --- |
| T3 p_cast | 0.760 | 0.526 | 69.2% |
| T4 spent | 0.855 | 0.572 | 66.9% |
| T5 util | 0.915 | 0.614 | 67.1% |
| T3 p_screw | 0.926 | 0.659 | 71.1% |
| T7 wasted | 0.854 | 0.503 | 58.9% |
| T10 cast | 0.514 | 0.291 | 56.6% |

The **ceiling** matters: simulation noise is unpredictable by construction and caps R². It was measured directly by running each deck twice under different seeds (`var(noise) = var(A−B)/2`). A first version of this analysis reported the raw R² with a "R1 CANNOT extract this" label attached; that reading was wrong, and wrong in the direction that flattered the idea being tested.

### And the third it cannot reach does not predict winning

All 53,116 distinct decks were simulated and fitted on development with the frozen folds, one fixed hyperparameter point for every representation:

| representation | features | Brier skill | increment over R0 |
| --- | --- | --- | --- |
| R0 skill only | 1 | 0.037551 | — |
| R1 skill + identity | 194 | 0.041720 | **+0.004169** |
| R3 skill + script | 91 | 0.036017 | **−0.001534** |
| R1+R3 everything | 284 | 0.040860 | +0.003309 |

**R3 is worse than skill alone, and adding the script to identity makes identity worse.** Retuning R3 four ways (depth 2–5, 60–268 rounds) lifted it off the noise-fitting floor to a best of 0.036841 — still below R0's 0.037551.

Two handicaps are on the record: 400 sims leaves feature noise, and the fixed hyperparameters were chosen for a 194-feature identity matrix. Both bias against R3. Neither closes a gap of this size.

**Reading:** "R1 can't compute this" and "this is worth computing" are different claims. The detectability test bounded the opportunity; it said nothing about whether the opportunity was worth taking.

---

## 4. The mechanic grids — a real interaction, already learned

### Second-draw

The KG names three payoffs (Lakeshore Apothecary, Bard the Bowman, Master's Councillors) sharing an **identical 25-card enabler set**, none of which is itself a payoff. **24.5% of development games play at least one payoff.**

Win rate over (total payoff copies × enabler copies) shows a clean interaction surface:

- **row 0 is flat** — card draw alone does nothing, in fact mildly negative
- every payoff row climbs steeply; 2 payoffs runs 46.0% → 64.9%
- **the crossover is ~7 enablers** for all three payoffs independently
- the dose–response *reverses sign*: at 3 enablers more copies is worse, at 12 enablers more copies is better

Difference-in-differences per extra enabler: Apothecary **+1.271%**, Bard **+1.091%**, Councillors **+0.852%**.

**The gradient survives skill stratification.** Pooled 5.38pp; within `base_p_raw` quintiles 5.46 / 6.50 / 4.41 / 4.01 / 5.44. Conditioning on measured skill removes essentially none of it.

### Bothersome Noisemaker — the diffuse counter-case

`{1}{R}` 2/2: *"Whenever you cast a noncreature spell, amass Goblins 1."* Its 81 KG enablers are essentially every noncreature spell, making the enabler axis a basic deckbuilding quantity rather than a niche synergy. 18.5% of games.

Opposite risk profile from second-draw:

- **row 0 is dead flat** across 158,000 games — a cleaner control than second-draw had
- it is an **upside** mechanic: 2 copies at 14–15 spells reaches **+6.3pp** bump, where second-draw's best cell was +1.0pp
- milder downside (−2.2pp vs −5.2pp) — a 2-mana 2/2 is playable even when the trigger rarely fires, whereas Apothecary without drawers is blank text
- gradient survives stratification again: pooled 3.18pp, strata 2.30 / 4.55 / 3.47 / 2.91

### But identity already has both

Partition variance, and what survives after subtracting `T0_R1`'s out-of-fold predictions:

| mechanic | enablers | raw partition | identity captured | excess over noise |
| --- | --- | --- | --- | --- |
| second-draw | 25 | BSS 0.002034 | **82.7%** | **0.000000** |
| Noisemaker | 81 | BSS 0.001013 | **89.6%** | **0.000000** |

The second-draw partition alone is worth ~51% of the total measured deck effect — but **four-fifths of it is already in R1's predictions, and the remainder is indistinguishable from cell-estimation noise.**

The diffuse mechanic was predicted to be *harder* for identity. It was captured **better**.

---

## 5. Netting out skill properly

`base_p` is shrunk toward μ = 0.533, so strong players carry a `base_p` below their true rate and overperform it *by construction*. Across the mechanic grid's cells, `corr(skill, won − base_p) = +0.716`.

`m̂` — T2's cross-fitted baseline, i.e. `T0_R0`'s out-of-fold prediction — is calibrated (`T2_R0` found r² = −0.0001 left in it). Substituting it:

| | span across cells | bump range |
| --- | --- | --- |
| `base_p` | 5.9 pp | −9.9 → **+10.1** |
| `m̂` | 10.6 pp | −12.1 → **+5.8** |

**The upside roughly halved and the downside deepened.** Most of the apparent reward for building second-draw well was good players being under-rated by the shrunk proxy. With a calibrated baseline the mechanic is **mainly a downside risk** — assembling it correctly is worth +0.32pp over simply not playing it, while stranding the payoff costs −5.22pp.

`corr(skill, bump)` fell from +0.716 to +0.586 but not to zero, and cannot: `m̂` is calibrated against `base_p`, not against true skill, and **this dataset has no player identifier** (`rank` is a bucket, not a person). That is a hard floor on attribution.

---

## 6. What the graph has that identity cannot

`ENABLES_TRIGGER` is **directed**, and overwhelmingly so: 441 edges, **2 reciprocated (0.5%)**. `Plunder the Trollshaws → Lakeshore Apothecary` exists; the reverse does not.

The outcomes respect the arrow:

```
payoff without enablers   −5.22 pp
enablers without payoff   −2.43 pp
asymmetry                  2.1×
```

A symmetric feature (`payoff × enablers`) treats those corners identically; the data says they differ 2.1×. The DAG says which term is the condition and which the consequence — a constraint on functional form that counts cannot supply.

**Four things the graph uniquely provides, none of which the current benchmark measures:**

1. **Direction** — asymmetric interaction structure
2. **Role labels that transfer** — payoff vs enabler is invisible in a new set's card counts; identity's 193 columns cannot transfer at all
3. **The feasible-space map** — which configurations are structurally dead, derivable with no data
4. **Causal structure for phase 4** — "add an enabler" and "add a payoff" are different interventions

---

## 7. The feasible-space observation

The empty cells of the mechanic grids are not missing data. **Nobody builds 4 payoffs with 0 enablers**, because the community recognises it as non-viable. That is a positivity violation, and the absence is itself information.

It also bounds card 017's headline. The measured ~13% deck contribution was estimated on **decks that passed a human viability filter**. Drafters pre-emptively exclude the configurations where deck quality would be catastrophic, so the observed variance in deck quality is range-restricted and the effect attenuated. The honest statement is *"among decks people actually choose to build, decks contribute 13%"* — a sharper caveat than any listed in benchmark §13.

---

## 8. Recommendation

**Do not card R2 as an aggregate-prediction bet.** Two mechanics spanning the structural extremes were both fully captured by card identity, with zero excess over noise. The simplest game script is worse than skill alone. The accumulated evidence says a representation card judged on incremental Brier will lose.

If phase 3 proceeds, it should be against a metric that measures what the graph actually supplies — **stratified evaluation** (does the KG identify *where* deck composition matters?), **transfer** (does a mechanism-based representation carry to another set, where identity provably cannot?), or **causal structure** (phase 4). Benchmark §11 frames everything as incremental aggregate performance, and that instrument is measuring the wrong thing for this arm.

Two items placed on the docket, not pursued:

- **Dead-zone subpopulation.** Where the graph says a mechanism is dead and people built it anyway, the deck effect should be far larger than 13%. That would be direct evidence the aggregate is attenuated by human filtering rather than by decks not mattering.
- **Reachability script** — `φ_script(D, G)` as the spec actually defines it, joining the simulator's per-turn board state to the graph's live-mechanism conditions. *Mechanism exists ≠ mechanism is reliably reachable.* The only representation examined here that R1 could not approximate in principle.

---

## 9. Three predictions of mine that measurement falsified

Recorded because the reasoning was plausible each time, and a future session will be tempted by the same reasoning.

1. **"The model is distracted by skill"** (H2's premise) — trees learn a smooth 1-D curve nearly for free, so there was no capacity to liberate. H2's null was predictable in advance and nobody checked.
2. **"Identity recovers only ⅔ of the script, so the missing third is R3's opportunity"** — the missing third does not predict winning. Bounding an opportunity is not establishing its value.
3. **"Diffuse mechanics will defeat identity"** — the diffuse mechanic was captured *better* (89.6% vs 82.7%).

The consistent error is **underestimating what a 268-tree ensemble extracts from 194,000 games**. Reasoning about what trees *represent well structurally* neglects that with this much data they approximate a great deal badly-but-adequately.

---

## Reproduction

Development rows only; nothing here touches `load_holdout`.

- `tools/game_script.py` — the R3 simulator, settled policy, with a CLI
- Model predictions consumed are the committed out-of-fold artifacts of cards 011 / 015 / 016 under `data/runs/`
- Graph inputs: `data/graph_global/{card_ports,pair_index,mechanism_modules}.jsonl`
- `matplotlib` is used for figures only; it is not in `deckbench.environment.PINNED_VERSIONS` because it touches no fitted artifact
