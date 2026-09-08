# MTG Deck-Strength Modeling Benchmark

## 1. Objective

Build a controlled benchmark for estimating the contribution of **deck construction to win probability after accounting for player skill**.

The experiment has two independent dimensions:

1. **Target formulation** — what quantity the model is asked to predict.
2. **Deck representation** — how information about the deck is presented to the model.

The central experimental design is therefore:

$$
\boxed{\text{Target formulation} \times \text{Deck representation}}
$$

All model variants must use identical train/validation/test partitions and be evaluated using the same metrics.

The purpose is to distinguish:

* whether skill adjustment exposes deck-level signal;
* whether raw card identity contains recoverable deck-strength information;
* whether structured representations such as the mechanistic knowledge graph or game-script features recover additional signal;
* whether structured representations add information beyond raw card identity.

This is initially a **predictive representation benchmark**. Causal intervention estimation will be layered on after the predictive architecture is characterized.

---

# 2. Fundamental decomposition

Conceptually, assume win probability contains at least:

$$
P(Y=1) = F(S,D)
$$

where:

* \(S\) = player skill/context;
* \(D\) = deck;
* \(Y\) = game win/loss or corresponding observed win-rate outcome.

A useful conceptual approximation is:

$$
p_i \approx p_{\text{skill},i}+\Delta_{\text{deck},i}.
$$

Player skill may generate substantially more between-observation variation than deck quality. For example, player baselines may span approximately 45–65% WR while deck effects may operate on the order of approximately \(\pm5\) percentage points.

Consequently, direct prediction of \(Y\) may be dominated by skill even when deck quality has a real and practically important effect.

The benchmark will explicitly test whether residualizing skill improves recovery of deck-level signal.

---

# 3. Experimental axis A: target formulation

## T0 — Raw outcome

Predict the observed outcome directly:

$$
Y_i.
$$

For game-level modeling:

$$
Y_{ig}\in\{0,1\}.
$$

The model estimates:

$$
\hat p_{ig}=f(S_i,D_{ig}).
$$

This is the conventional prediction problem.

### Purpose

Establish how much deck information improves prediction of actual outcomes beyond skill.

---

## T1 — Original bump

Reproduce the original deck-bump formulation as closely as possible.

Define:

$$
B_i^{original}
=
Y_i-p_{\text{base},i},
$$

where \(p_{\text{base}}\) is the existing constructed historical skill proxy.

The deck model predicts:

$$
\widehat B_i^{original}
=
f(D_i,S_i).
$$

Reconstructed win probability is:

$$
\hat p_i
=
p_{\text{base},i}
+
\widehat B_i^{original}.
$$

### Purpose

Reproduce the original approach and determine whether directly subtracting the historical skill proxy exposes deck signal better than raw-outcome prediction.

---

## T2 — Learned-skill bump

Replace the fixed skill baseline with a learned expected-win model.

First estimate:

$$
m(S)=E[Y\mid S].
$$

For every training observation, obtain a **cross-fitted** prediction:

$$
\hat m_{-i}(S_i).
$$

Define:

$$
B_i^{learned}
=
Y_i-\hat m_{-i}(S_i).
$$

Then model:

$$
\widehat B_i^{learned}
=
f(D_i,S_i).
$$

Final prediction is:

$$
\hat p_i
=
\hat m(S_i)
+
\widehat B_i^{learned}.
$$

### Critical requirement

Residuals used to train the deck model must be generated out-of-fold.

An observation must never be used to train the skill model that generates its own baseline prediction.

The external test set must remain completely untouched during this procedure.

### Purpose

Test whether a learned estimate of expected performance given skill provides a cleaner baseline than directly using the historical WR proxy.

---

# 4. Experimental axis B: deck representation

The same deck representations should be tested across the target formulations wherever technically appropriate.

## R0 — Skill only

$$
S
$$

No deck information.

This is the baseline model.

For residual targets, the exact role of \(S\) should be documented carefully because skill has already been used in construction of the target.

---

## R1 — Card identity

$$
D_{\text{identity}}
$$

Deck represented by individual card composition.

Preferred representation:

$$
D_{ij}
=
\frac{\text{count of card }j}
{\text{deck size}}.
$$

If modeling individual games, this representation must correspond to the deck actually recorded for that game.

Do not aggregate multiple different deck configurations into a synthetic average deck without explicitly testing and documenting that choice.

---

## R2 — Knowledge-graph representation

$$
Z_{\text{KG}}=\phi_{\text{KG}}(D,G).
$$

Project the deck into the existing mechanistic MTG knowledge graph.

Features should describe functional/mechanistic structure rather than merely relabel card identities.

Exact KG feature engineering will be specified separately.

---

## R3 — Game-script representation

$$
Z_{\text{script}}=\phi_{\text{script}}(D,G).
$$

Represent the probability distribution over meaningful early/mid-game capabilities generated by the deck.

Candidate features include:

* probability of meaningful T1–T10 plays;
* probability of T2/T3 curve-out;
* probability of using available mana;
* expected wasted mana;
* probability of color screw;
* probability of developing a creature by a given turn;
* probability of having interaction available;
* castable spell count by turn;
* probability of no meaningful action;
* probability of reaching important KG-defined synergies or motifs by a useful turn.

The important conceptual distinction is:

$$
\boxed{\text{Mechanism exists} \neq \text{mechanism is reliably reachable}}
$$

---

## R4 — Identity + KG

$$
D_{\text{identity}}+Z_{\text{KG}}.
$$

Tests whether the KG contributes information beyond raw card identity.

---

## R5 — Identity + KG + game script

$$
D_{\text{identity}}
+
Z_{\text{KG}}
+
Z_{\text{script}}.
$$

This is the richest planned representation.

Additional ablations such as KG + script without identity may be added later.

---

# 5. Core experimental matrix

The intended benchmark is:

| Target                | Skill only | Identity | KG | Script | Identity + KG | Identity + KG + Script |
| --------------------- | ---------: | -------: | -: | -----: | ------------: | ---------------------: |
| T0 Raw outcome        |          ✓ |        ✓ |  ✓ |      ✓ |             ✓ |                      ✓ |
| T1 Original bump      |          ✓ |        ✓ |  ✓ |      ✓ |             ✓ |                      ✓ |
| T2 Learned-skill bump |          ✓ |        ✓ |  ✓ |      ✓ |             ✓ |                      ✓ |

Not every cell must necessarily use an identical feature list. For example, skill may appear both in target construction and as a predictor in bump models.

Any deviation must be documented rather than silently changed.

---

# 6. Data unit

The primary new analysis should preferentially operate at the **game level** if the raw dataset provides the deck used for each individual game.

Each observation should then correspond to:

$$
(S_i,D_{ig},Y_{ig}).
$$

This avoids averaging together decks when players modify their deck between games.

Before modeling, audit:

* number of games;
* number of drafts;
* number of unique deck configurations per draft;
* fraction of drafts with more than one deck configuration;
* fraction of games occurring after a deck change;
* deck-size distribution;
* card-count consistency;
* skill-variable consistency within draft.

The original draft/run-level formulation may be retained as a secondary benchmark and direct replication of previous work.

---

# 7. Data splitting

All models must use the **same frozen splits**.

At minimum:

* training;
* internal validation/cross-fitting;
* external test set.

Games from the same draft must never cross partitions.

Therefore:

$$
\boxed{\text{split by draft ID, not game row}}
$$

If a genuine player identifier exists, prefer player-level separation where appropriate so the same player cannot appear across train and test.

Do not treat rank as player identity.

A time-based external holdout should be considered if genuine player IDs are unavailable.

Save the split assignments to disk and reuse them for every subsequent model.

---

# 8. Common learner

Initially hold the learner family constant so representation changes are not confounded with algorithm changes.

Recommended initial learner:

**XGBoost**

Use appropriate objectives:

* binary/logistic objective for raw game outcomes;
* regression objective for continuous bump/residual targets.

Hyperparameter tuning procedures should be identical across comparable models.

Do not introduce GNNs or specialized graph learners in the first benchmark.

The immediate question is whether the representation contains useful information, not whether a specialized architecture can exploit it.

---

# 9. Evaluation framework

Every final model should produce predictions on the same untouched external test observations.

Report a common evaluation panel.

## Core metrics

### R²

For continuous bump/residual targets:

$$
R^2
=
1-\frac{\sum_i(y_i-\hat y_i)^2}
{\sum_i(y_i-\bar y)^2}.
$$

For Bernoulli/raw-outcome models, do not silently report ordinary regression \(R^2\). Use a clearly defined probability-prediction analogue such as Brier Skill Score or explicitly labeled pseudo-\(R^2\).

---

### RMSE

$$
RMSE
=
\sqrt{
\frac{1}{N}
\sum_i(y_i-\hat y_i)^2
}.
$$

---

### MAE

$$
MAE
=
\frac{1}{N}
\sum_i|y_i-\hat y_i|.
$$

Provides an error measure less sensitive to large misses than RMSE.

---

### Brier score

For final win probabilities:

$$
BS
=
\frac{1}{N}
\sum_i(\hat p_i-y_i)^2.
$$

This should be a primary metric for game-level probability predictions.

---

### Log loss

$$
-\frac{1}{N}
\sum_i
[
y_i\log(\hat p_i)
+
(1-y_i)\log(1-\hat p_i)
].
$$

Useful because it penalizes confident incorrect predictions strongly.

---

### AUC

Report as a secondary discrimination metric.

AUC is not sufficient by itself because the primary scientific interest concerns accurate win probabilities, not merely ranking winners above losers.

---

# 10. Calibration evaluation

Every model producing final win probabilities should undergo identical calibration analysis.

## Calibration intercept

Ideal:

$$
0.
$$

Tests systematic overprediction/underprediction.

---

## Calibration slope

Ideal:

$$
1.
$$

A slope below 1 generally indicates predictions are too extreme.

A slope above 1 generally indicates predictions are too conservative.

---

## Binned calibration

Create identical probability bins for all models.

For each bin compare:

$$
\text{mean predicted probability}
$$

against

$$
\text{observed win frequency}.
$$

Use the same binning strategy across models.

Produce a calibration plot with the 45-degree identity line.

---

## Smooth calibration

In addition to bins, fit a smooth calibration function so results do not depend entirely on arbitrary bin boundaries.

The exact implementation can be selected after inspecting the prediction distribution.

GAMLSS should not currently be treated as a required evaluation metric. If a distributional/smooth calibration method based on GAMLSS is considered later, add it as a separate diagnostic rather than conflating it with the core metrics.

---

# 11. Incremental-value analysis

Absolute model performance is not sufficient.

The primary scientific question is:

> How much additional information does a deck representation contribute beyond skill?

Therefore calculate paired differences such as:

$$
\Delta R^2
=
R^2(M_k)-R^2(M_0),
$$

$$
\Delta RMSE
=
RMSE(M_k)-RMSE(M_0),
$$

$$
\Delta BS
=
BS(M_k)-BS(M_0),
$$

and

$$
\Delta LL
=
LL(M_k)-LL(M_0).
$$

The same principle should be used to compare representations directly, e.g.:

$$
M_{\text{KG}}-M_{\text{identity}}
$$

and

$$
M_{\text{script}}-M_{\text{identity}}.
$$

---

# 12. Uncertainty

Use a **paired cluster bootstrap** for model comparisons.

Cluster at the draft level so games from a draft are resampled together.

For each bootstrap replicate:

1. sample draft IDs;
2. include all corresponding games;
3. evaluate every model on exactly that bootstrap sample;
4. calculate metric differences.

Report confidence intervals for:

$$
\Delta R^2,\quad
\Delta RMSE,\quad
\Delta Brier,\quad
\Delta LogLoss
$$

and other important pairwise comparisons.

The paired design is important because all models predict the same observations.

---

# 13. Interpretation rules

Do not equate lack of incremental predictive performance with absence of a causal deck effect.

For example:

$$
R^2(S+D)\approx R^2(S)
$$

supports:

> Card identity provides little detectable incremental predictive information beyond skill under this representation, learner and dataset.

It does **not** establish:

> Deck composition does not affect win probability.

Possible explanations include:

* deck effects are small relative to skill;
* deck effects are interaction-dependent;
* card identity is an inefficient representation;
* outcome noise overwhelms small effects;
* skill partially proxies expected deck quality because stronger players draft better decks.

This distinction should be maintained throughout the analysis.

---

# 14. Primary hypotheses

### H1 — Skill dominance

Skill alone explains substantially more predictable variation in raw outcomes than deck identity.

---

### H2 — Residualization

Deck signal is easier to recover when the dominant skill component is removed.

Expected ordering, if this hypothesis is correct:

$$
\text{deck signal under T2}
>
\text{deck signal under T1}
>
\text{deck signal under T0}.
$$

This is a hypothesis, not an assumed result.

---

### H3 — Structured representation

Functional deck representations outperform raw identity:

$$
Z_{\text{KG}}
\text{ and/or }
Z_{\text{script}}
>
D_{\text{identity}}.
$$

---

### H4 — Reachability

Game-script features add information beyond static mechanistic structure:

$$
D+Z_{\text{KG}}+Z_{\text{script}}
>
D+Z_{\text{KG}}.
$$

This would support the idea that knowing a mechanism exists is insufficient; its probability of being realized during actual games matters.

---

# 15. Required outputs

For every completed model, save:

* model identifier;
* target formulation;
* representation;
* feature list/version;
* split version;
* hyperparameters;
* test predictions;
* reconstructed final win probability where applicable;
* all evaluation metrics;
* calibration data;
* bootstrap comparisons;
* model artifact;
* random seed;
* code/git commit.

Create a master results table with one row per model.

At minimum include:

| Model | Target | Representation | R² | RMSE | MAE | Brier | Log Loss | AUC | Cal. Intercept | Cal. Slope |
| ----- | ------ | -------------- | -: | ---: | --: | ----: | -------: | --: | -------------: | ---------: |

Also create pairwise/incremental tables relative to the appropriate skill-only and identity baselines.

---

# 16. Implementation order

Do not attempt the full matrix immediately.

### Phase 1 — Data audit

Establish the correct observational unit, audit deck changes within drafts, validate skill fields, freeze splits.

### Phase 2 — Target benchmark

Using skill and card identity only, implement:

$$
T0=\text{raw outcome}
$$

$$
T1=\text{original bump}
$$

$$
T2=\text{learned-skill bump}.
$$

This determines whether target construction materially affects recovery of deck signal.

### Phase 3 — Representation benchmark

Once the target architecture is understood, add:

$$
D_{\text{identity}}
\rightarrow
Z_{\text{KG}}
\rightarrow
Z_{\text{script}}
\rightarrow
\text{combined representations}.
$$

### Phase 4 — Causal estimation

Only after the predictive benchmark is characterized should the project move to explicit deck/card interventions, g-computation, orthogonalization/DML, substitution effects, or draft-pick policy estimation.

---

# 17. Immediate task

Do **not** start training the complete model matrix yet.

First:

1. audit the raw HOB game-level dataset;
2. determine whether deck configurations change within drafts and quantify how often;
3. construct the correct game-level modeling table;
4. verify the skill variables and reproduce the existing skill proxy;
5. define and save frozen train/validation/test splits;
6. produce an audit report;
7. stop for review before model fitting.

The benchmark architecture above should then be implemented against that frozen dataset.
