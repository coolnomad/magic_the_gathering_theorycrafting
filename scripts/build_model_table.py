"""
Build the draft-level model table and deck-identity matrix.
Optimized for memory-constrained environments.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
import gc

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Configuration
RAW_DATA = Path("data/raw/game_data_public.HOB.PremierDraft.csv.gz")
OUTPUT_DIR = Path("data/processed")
OUTPUT_DIR.mkdir(exist_ok=True)

# Required columns
REQUIRED_COLS = ['draft_id', 'rank', 'won', 'draft_time', 'user_game_win_rate_bucket', 'user_n_games_bucket']


def get_columns_safely():
    """Get column list without loading full data."""
    log.info("Reading column names from CSV header...")
    try:
        df_header = pd.read_csv(RAW_DATA, nrows=0, compression='gzip')
        deck_cols = sorted([c for c in df_header.columns if c.startswith('deck_')])
        log.info(f"Found {len(deck_cols)} deck columns")
        return deck_cols
    except Exception as e:
        log.warning(f"Could not auto-detect columns: {e}")
        log.info("Using fallback column list...")
        return [f'deck_card_{i:03d}' for i in range(193)]


def load_and_aggregate():
    """Load data in minimal chunks and aggregate."""
    log.info("Loading and aggregating game-level data to draft level...")

    deck_cols = get_columns_safely()
    cols_to_load = REQUIRED_COLS + deck_cols

    # Minimal dtypes
    dtype_map = {col: 'int8' for col in deck_cols}
    dtype_map.update({
        'draft_id': str,
        'rank': str,
        'won': bool,
        'draft_time': str,
        'user_game_win_rate_bucket': 'float32',
        'user_n_games_bucket': 'float32',
    })

    draft_dict = {}
    game_count_by_draft = {}
    total_games = 0

    # Read in small chunks
    chunk_size = 5000
    for i, chunk in enumerate(pd.read_csv(
        RAW_DATA,
        usecols=cols_to_load,
        dtype=dtype_map,
        chunksize=chunk_size,
        compression='gzip',
        low_memory=False
    )):
        if i % 20 == 0:
            log.info(f"  Processed {i * chunk_size:,} games...")

        for _, row in chunk.iterrows():
            draft_id = row['draft_id']
            total_games += 1

            if draft_id not in draft_dict:
                # Use fillna to handle missing values
                base_p_raw = float(row['user_game_win_rate_bucket'])
                if np.isnan(base_p_raw):
                    base_p_raw = 0.5  # Default to 50% if missing

                n_games_bucket = float(row['user_n_games_bucket'])
                if np.isnan(n_games_bucket):
                    n_games_bucket = 10.0  # Default to bucket 10 if missing

                draft_dict[draft_id] = {
                    'rank': row['rank'],
                    'draft_time': row['draft_time'],
                    'base_p_raw': base_p_raw,
                    'n_games_bucket': n_games_bucket,
                    'wins': 0,
                    'deck_sums': np.zeros(len(deck_cols), dtype='int32')
                }
                game_count_by_draft[draft_id] = 0

            draft_dict[draft_id]['wins'] += int(row['won'])
            game_count_by_draft[draft_id] += 1

            # Accumulate deck counts
            for j, col in enumerate(deck_cols):
                draft_dict[draft_id]['deck_sums'][j] += int(row[col])

        del chunk
        gc.collect()

    log.info(f"Aggregated {len(draft_dict):,} unique drafts from {total_games:,} games")
    return draft_dict, game_count_by_draft, deck_cols


def compute_skill_proxy(draft_dict):
    """Compute hierarchical shrinkage skill proxy."""
    log.info("Computing skill proxy...")

    games_bucket_to_weight = {
        1.0: 1, 5.0: 2, 10.0: 3, 50.0: 6, 100.0: 8, 500.0: 12, 1000.0: 14
    }

    base_p_raw_values = np.array([d['base_p_raw'] for d in draft_dict.values()], dtype='float32')
    mu = np.mean(base_p_raw_values)
    lambda_ = 5.0

    def logit(p):
        p = np.clip(p, 1e-7, 1 - 1e-7)
        return np.log(p / (1 - p))

    def invlogit(z):
        return 1.0 / (1.0 + np.exp(-z))

    for draft_id, data in draft_dict.items():
        base_p_raw = data['base_p_raw']
        n_games_bucket = data['n_games_bucket']

        # Find closest bucket
        hist_w = float(games_bucket_to_weight.get(n_games_bucket, 10))

        logit_base_p_raw = logit(base_p_raw)
        logit_mu = logit(mu)

        numerator = hist_w * logit_base_p_raw + lambda_ * logit_mu
        denominator = hist_w + lambda_

        base_p = invlogit(numerator / denominator)
        data['base_p'] = float(np.clip(base_p, 1e-7, 1 - 1e-7))

    mean_base_p = np.mean([d['base_p'] for d in draft_dict.values()])
    log.info(f"Skill proxy computed: mean base_p = {mean_base_p:.3f}")


def build_dataframes(draft_dict, game_count_by_draft, deck_cols):
    """Convert to DataFrames efficiently."""
    log.info("Building output DataFrames...")

    draft_ids = []
    ranks = []
    wins_list = []
    losses_list = []
    games_list = []
    win_rates = []
    deck_sizes = []
    draft_times = []
    base_p_raws = []
    base_ps = []
    deck_array = []

    for draft_id in sorted(draft_dict.keys()):
        data = draft_dict[draft_id]
        wins = data['wins']
        games = game_count_by_draft[draft_id]
        losses = games - wins
        deck_size = int(np.sum(data['deck_sums']))

        draft_ids.append(draft_id)
        ranks.append(data['rank'])
        wins_list.append(wins)
        losses_list.append(losses)
        games_list.append(games)
        win_rates.append(wins / games if games > 0 else 0)
        deck_sizes.append(deck_size)
        draft_times.append(data['draft_time'])
        base_p_raws.append(data['base_p_raw'])
        base_ps.append(data['base_p'])
        deck_array.append(data['deck_sums'])

    # Build model table
    model_table = pd.DataFrame({
        'draft_id': draft_ids,
        'rank': ranks,
        'wins': wins_list,
        'losses': losses_list,
        'games': games_list,
        'win_rate': win_rates,
        'deck_size': deck_sizes,
        'draft_time': draft_times,
        'base_p_raw': base_p_raws,
        'base_p': base_ps,
    })

    # Add deck columns
    deck_array_2d = np.array(deck_array, dtype='int32')
    for j, col in enumerate(deck_cols):
        model_table[col] = deck_array_2d[:, j]

    log.info(f"Built model_table: {len(model_table):,} rows × {len(model_table.columns)} cols")

    # Build identity matrix
    identity_data = {'draft_id': draft_ids}
    for j, col in enumerate(deck_cols):
        card_name = col.replace('deck_', '')
        fractions = []
        for k, deck_size in enumerate(deck_sizes):
            frac = deck_array_2d[k, j] / deck_size if deck_size > 0 else 0
            fractions.append(frac)
        identity_data[card_name] = fractions

    identity_df = pd.DataFrame(identity_data)
    log.info(f"Built identity_df: {len(identity_df):,} rows × {len(identity_df.columns)} cols")

    return model_table, identity_df, deck_array_2d


def card_manifest(deck_cols, deck_array_2d, model_table):
    """Create card manifest."""
    log.info("Creating card manifest...")

    manifest = []
    for j, col in enumerate(deck_cols):
        card_name = col.replace('deck_', '')
        total_count = int(np.sum(deck_array_2d[:, j]))
        n_drafts_with_card = int(np.sum(deck_array_2d[:, j] > 0))
        fraction_with_card = n_drafts_with_card / len(model_table)

        manifest.append({
            'source_column': col,
            'card_name': card_name,
            'total_count': total_count,
            'n_drafts_with_card': n_drafts_with_card,
            'fraction_with_card': fraction_with_card
        })

    manifest_df = pd.DataFrame(manifest)
    manifest_df = manifest_df.sort_values('total_count', ascending=False).reset_index(drop=True)

    log.info(f"Created manifest for {len(manifest_df)} cards")
    log.info(f"  Cards in >50% of drafts: {(manifest_df['fraction_with_card'] > 0.5).sum()}")

    return manifest_df


def main():
    log.info("=" * 70)
    log.info("Building Model Data (Memory-Optimized)")
    log.info("=" * 70)

    draft_dict, game_count_by_draft, deck_cols = load_and_aggregate()
    compute_skill_proxy(draft_dict)
    model_table, identity_df, deck_array = build_dataframes(draft_dict, game_count_by_draft, deck_cols)
    manifest_df = card_manifest(deck_cols, deck_array, model_table)

    log.info("\nSaving outputs...")
    model_table.to_parquet(OUTPUT_DIR / "draft_model_table.parquet", index=False)
    log.info(f"  Saved draft_model_table.parquet ({len(model_table):,} rows)")

    identity_df.to_parquet(OUTPUT_DIR / "deck_identity.parquet", index=False)
    log.info(f"  Saved deck_identity.parquet ({len(identity_df):,} rows)")

    manifest_df.to_csv(OUTPUT_DIR / "card_identity_manifest.csv", index=False)
    log.info(f"  Saved card_identity_manifest.csv ({len(manifest_df)} rows)")

    log.info("\n" + "=" * 70)
    log.info("Validation")
    log.info("=" * 70)

    assert len(model_table) == len(identity_df), "Row counts mismatch"
    assert (model_table['deck_size'] > 0).all(), "Zero-size decks found"

    log.info("✓ All validation checks passed")
    log.info(f"\nFinal sample size: {len(model_table):,} drafts")
    log.info(f"Card identity features: {len(identity_df.columns) - 1}")

    return model_table, identity_df, manifest_df


if __name__ == "__main__":
    main()
