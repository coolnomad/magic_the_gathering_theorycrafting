#!/usr/bin/env python3
"""
Build the Identity Representation Matrix for Causal Inference
"""

import gzip
import pandas as pd
import numpy as np
from scipy.sparse import csr_matrix, coo_matrix
from pathlib import Path

# Configuration
RAW_DATA = Path("data/raw/game_data_public.HOB.PremierDraft.csv.gz")
OUTPUT_DIR = Path("data/processed")
OUTPUT_DIR.mkdir(exist_ok=True)

print("=" * 70)
print("Building Identity Representation Matrix")
print("=" * 70)

print("\nLoading raw draft data...")
usecols = ['draft_id', 'rank', 'won']
df_raw = pd.read_csv(RAW_DATA, usecols=usecols)
print(f"Loaded {len(df_raw):,} game records")

print("\nAggregating to draft level...")
draft_data = df_raw.groupby('draft_id').agg(
    player_id=('rank', 'first'),
    n_games=('won', 'size'),
    n_wins=('won', 'sum'),
).reset_index()

draft_data['n_losses'] = draft_data['n_games'] - draft_data['n_wins']
draft_data['win_rate'] = draft_data['n_wins'] / draft_data['n_games']

n_drafts = len(draft_data)
n_player_ranks = draft_data['player_id'].nunique()

print(f"  {n_drafts:,} unique drafts")
print(f"  {n_player_ranks} unique player ranks")
print(f"  Win rate range: [{draft_data['win_rate'].min():.3f}, {draft_data['win_rate'].max():.3f}]")

print("\nBuilding player index...")
player_index = draft_data.groupby('player_id').agg(
    n_drafts=('draft_id', 'size'),
    total_wins=('n_wins', 'sum'),
    total_games=('n_games', 'sum'),
).reset_index()

player_index['baseline_win_rate'] = player_index['total_wins'] / player_index['total_games']
player_index = player_index.sort_values('n_drafts', ascending=False).reset_index(drop=True)
player_index['player_idx'] = player_index.index + 1

player_index = player_index[['player_idx', 'player_id', 'n_drafts', 'total_wins', 'total_games', 'baseline_win_rate']]
player_index.to_csv(OUTPUT_DIR / "player_index.csv", index=False)
print(f"  Saved {len(player_index)} players to player_index.csv")

print("\nBuilding draft metadata...")
draft_data['draft_idx'] = range(1, len(draft_data) + 1)
draft_data = draft_data.merge(player_index[['player_id', 'player_idx']], on='player_id', how='left')
draft_metadata = draft_data[['draft_idx', 'draft_id', 'player_idx', 'n_games', 'n_wins', 'n_losses', 'win_rate']]
draft_metadata.to_csv(OUTPUT_DIR / "draft_metadata.csv", index=False)
print(f"  Saved {len(draft_metadata):,} draft records to draft_metadata.csv")

print("\nBuilding identity representation matrix...")
P_data = np.ones(len(draft_metadata), dtype=np.int8)
P_row = draft_metadata['draft_idx'].values - 1
P_col = draft_metadata['player_idx'].values - 1

P_sparse = csr_matrix((P_data, (P_row, P_col)), shape=(n_drafts, len(player_index)))
print(f"  Identity matrix dimensions: {P_sparse.shape[0]:,} drafts × {P_sparse.shape[1]} players")
sparsity = 100 * (1 - P_sparse.nnz / (P_sparse.shape[0] * P_sparse.shape[1]))
print(f"  Sparsity: {sparsity:.1f}% ({P_sparse.nnz:,} non-zero entries)")

row_sums = np.array(P_sparse.sum(axis=1)).flatten()
all_one = np.all(row_sums == 1)
print(f"  Verification: all drafts assigned to exactly 1 player? {'✓ YES' if all_one else '✗ NO'}")

print("\nSaving matrices...")
P_coo = P_sparse.tocoo()
identity_sparse_df = pd.DataFrame({
    'draft_idx': P_coo.row + 1,
    'player_idx': P_coo.col + 1,
    'value': P_coo.data
})
identity_sparse_df.to_csv(OUTPUT_DIR / "identity_matrix_sparse.csv", index=False)
print(f"  Saved sparse matrix to identity_matrix_sparse.csv")

P_dense = P_sparse.toarray()
np.save(OUTPUT_DIR / "identity_matrix_dense.npy", P_dense)
print(f"  Saved dense matrix to identity_matrix_dense.npy")

print("\n" + "=" * 70)
print("IDENTITY MATRIX SUMMARY")
print("=" * 70)
print(f"Dimensions:          {P_sparse.shape[0]:,} drafts × {P_sparse.shape[1]} players")
print(f"Total games:         {draft_metadata['n_games'].sum():,}")
print(f"Total wins:          {draft_metadata['n_wins'].sum():,}")
print(f"Overall win rate:    {draft_metadata['n_wins'].sum() / draft_metadata['n_games'].sum():.3f}")
print(f"\nPlayer statistics:")
print(f"  Mean drafts/player: {player_index['n_drafts'].mean():.1f}")
print(f"  Median drafts/player: {player_index['n_drafts'].median():.0f}")
print(f"  Max drafts by player: {player_index['n_drafts'].max()}")
print(f"\nRank distribution:")
for _, row in player_index.iterrows():
    pct = 100 * row['n_drafts'] / draft_data.shape[0]
    print(f"  {row['player_id']}: {row['n_drafts']:,} drafts ({pct:.1f}%)")

print("\n✓ Identity matrix construction complete.")
print("✓ Ready for hierarchical baseline skill estimation.\n")
