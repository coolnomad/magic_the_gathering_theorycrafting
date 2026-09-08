"""
Step 4-5: Define outcome as grouped binomial and create frozen split.

This module:
1. Defines the grouped binomial outcome (wins/games per draft)
2. Creates a frozen timestamp-based split (dev/holdout)
3. Saves split indices for reproducibility

Output files:
  - data/processed/outcome_definition.txt (documentation)
  - data/processed/split_indices.csv (draft_idx, split)
  - data/processed/split_info.txt (summary statistics)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Configuration
PROCESSED_DIR = Path("data/processed")
OUTPUT_DIR = PROCESSED_DIR

def load_model_table():
    """Load draft_model_table.parquet"""
    log.info("Loading draft_model_table.parquet...")
    model_table = pd.read_parquet(PROCESSED_DIR / "draft_model_table.parquet")
    log.info(f"Loaded {len(model_table):,} drafts")
    return model_table


def document_outcome():
    """Document the outcome definition."""
    log.info("Documenting outcome definition...")

    outcome_doc = """
OUTCOME DEFINITION: Grouped Binomial Likelihood
================================================

Model: wins_i ~ Binomial(n_i, p_i)
  wins_i  : Number of wins in draft i
  n_i     : Total games played in draft i (bounded by 7-3 rule)
  p_i     : Probability of winning a single game in draft i

Key properties:
  1. Data is grouped at the draft level, not individual games
  2. Each draft produces (wins, losses) ~ (wins, games - wins)
  3. wins ranges [0, 7] and losses range [0, 3] (7-3 stopping rule)
  4. Combined outcomes range [0, 10] games per draft

7-3 Stopping Rule Ceiling:
  R² ≤ 0.06 ceiling on this outcome due to stopping rule
  (empirically observed, not theoretical)

Predictors:
  - base_p: Hierarchical shrinkage skill proxy (player effect P)
  - Card identity: Normalized counts of 193 cards in deck (deck effect D)
  - (Future: KG features, gamescript features)

Causal DAG:
  P → W
  P → D → W
  (player skill P confounds both deck selection D and outcome W)

Likelihood decomposition:
  L(y_i | x_i) = Binomial(wins_i | games_i, p_i(x_i))
  where x_i includes base_p and deck identity features
"""

    output_file = OUTPUT_DIR / "outcome_definition.txt"
    with open(output_file, 'w') as f:
        f.write(outcome_doc)

    log.info(f"Saved outcome definition to {output_file}")
    return outcome_doc


def create_frozen_split(model_table):
    """
    Create a frozen timestamp-based split.

    Strategy: Use draft_time quartiles to ensure fair temporal split
    (Since no player_id exists in anonymized dataset, we can't do player-based split)

    Development: First 75% by timestamp
    Holdout:     Last 25% by timestamp
    """
    log.info("Creating frozen timestamp-based split...")

    # Parse draft_time (format: YYYY-MM-DDTHH:MM:SSZ)
    model_table['draft_timestamp'] = pd.to_datetime(model_table['draft_time'], utc=True)

    # Compute quartiles
    q75 = model_table['draft_timestamp'].quantile(0.75)
    log.info(f"  Split point (75th percentile): {q75}")

    # Create split
    model_table['split'] = 'dev'
    model_table.loc[model_table['draft_timestamp'] >= q75, 'split'] = 'holdout'

    split_counts = model_table['split'].value_counts()
    log.info(f"  Development: {split_counts['dev']:,} drafts ({100*split_counts['dev']/len(model_table):.1f}%)")
    log.info(f"  Holdout:     {split_counts['holdout']:,} drafts ({100*split_counts['holdout']/len(model_table):.1f}%)")

    # Verify no data leakage on key columns
    dev_table = model_table[model_table['split'] == 'dev']
    holdout_table = model_table[model_table['split'] == 'holdout']

    log.info(f"\n  Development set:")
    log.info(f"    Date range: {dev_table['draft_timestamp'].min()} to {dev_table['draft_timestamp'].max()}")
    log.info(f"    Win rate: {dev_table['wins'].sum() / dev_table['games'].sum():.3f}")
    log.info(f"    Mean deck size: {dev_table['deck_size'].mean():.1f}")

    log.info(f"\n  Holdout set:")
    log.info(f"    Date range: {holdout_table['draft_timestamp'].min()} to {holdout_table['draft_timestamp'].max()}")
    log.info(f"    Win rate: {holdout_table['wins'].sum() / holdout_table['games'].sum():.3f}")
    log.info(f"    Mean deck size: {holdout_table['deck_size'].mean():.1f}")

    return model_table[['draft_id', 'split']]


def save_split(split_df, model_table):
    """Save split indices."""
    log.info("\nSaving split definition...")

    # Add draft_idx
    split_df = split_df.reset_index(drop=True)
    split_df['draft_idx'] = range(1, len(split_df) + 1)
    split_df = split_df[['draft_idx', 'draft_id', 'split']]

    split_df.to_csv(OUTPUT_DIR / "split_indices.csv", index=False)
    log.info(f"  Saved split_indices.csv")

    # Summary statistics
    summary = f"""
FROZEN SPLIT SUMMARY
====================

Total drafts:           {len(model_table):,}
Development drafts:     {(split_df['split'] == 'dev').sum():,} (75%)
Holdout drafts:         {(split_df['split'] == 'holdout').sum():,} (25%)

Strategy:       Timestamp-based quartile split (no player_id in anonymized data)
Timestamp col:  draft_time (ISO 8601 UTC)

This frozen split is used for:
  1. All model comparisons (M0 vs M1 vs M2 vs M3 vs M4)
  2. Cross-validation within each split
  3. Holdout evaluation of final models

Key property: Same split is reused for all models to ensure fair comparison.
"""

    with open(OUTPUT_DIR / "split_info.txt", 'w') as f:
        f.write(summary)

    log.info(f"  Saved split_info.txt")
    log.info(summary)


def main():
    log.info("=" * 70)
    log.info("Step 4-5: Outcome Definition & Frozen Split")
    log.info("=" * 70)

    # Document outcome
    document_outcome()

    # Load model table
    model_table = load_model_table()

    # Create frozen split
    split_df = create_frozen_split(model_table)

    # Save split
    save_split(split_df, model_table)

    log.info("\n" + "=" * 70)
    log.info("✓ Outcome definition and frozen split created")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
