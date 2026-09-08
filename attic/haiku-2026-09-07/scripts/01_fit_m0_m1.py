"""
Step 6-7: Fit M0 (skill only) and M1 (skill + card identity) models.

This module:
1. Loads preprocessed data and frozen split
2. Fits M0 model: base_p only (player skill baseline)
3. Fits M1 model: base_p + 193 normalized card fractions
4. Saves both models for later evaluation

Models use XGBoost with:
  - Objective: binary:logistic (for binomial grouped outcome)
  - Target: win_rate (normalized, 0-1)
  - Weights: games_per_draft (for grouped binomial)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging

try:
    import xgboost as xgb
except ImportError:
    print("Installing xgboost...")
    import subprocess
    subprocess.check_call(['pip', 'install', 'xgboost', '-q'])
    import xgboost as xgb

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Configuration
PROCESSED_DIR = Path("data/processed")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

def load_data():
    """Load model table, identity matrix, and split."""
    log.info("Loading data...")

    model_table = pd.read_parquet(PROCESSED_DIR / "draft_model_table.parquet")
    identity_df = pd.read_parquet(PROCESSED_DIR / "deck_identity.parquet")
    split_df = pd.read_csv(PROCESSED_DIR / "split_indices.csv")

    # Merge split into model_table
    model_table = model_table.reset_index(drop=True)
    split_df = split_df[['draft_idx', 'split']]
    split_df['draft_idx'] = split_df['draft_idx'] - 1  # 0-indexed for merging

    model_table['split'] = split_df['split'].values

    log.info(f"Loaded {len(model_table):,} drafts")
    log.info(f"Development: {(model_table['split'] == 'dev').sum():,}")
    log.info(f"Holdout: {(model_table['split'] == 'holdout').sum():,}")

    # Get card columns
    card_cols = [c for c in identity_df.columns if c != 'draft_id']
    log.info(f"Card features: {len(card_cols)}")

    return model_table, identity_df, card_cols


def prepare_features(model_table, identity_df, card_cols, use_identity=False):
    """Prepare feature matrix, outcome, and weights."""
    log.info(f"\nPreparing features (identity={use_identity})...")

    X = model_table[['base_p']].copy()

    if use_identity:
        identity_df_reindex = identity_df.set_index('draft_id')
        card_features = model_table[['draft_id']].merge(
            identity_df_reindex[card_cols],
            left_on='draft_id',
            right_index=True
        )[card_cols]
        X = pd.concat([X, card_features], axis=1)

    # Outcome: win_rate (normalized to 0-1)
    y = (model_table['wins'] / model_table['games']).values.astype(float)

    # Sample weights: number of games (for grouped binomial)
    sample_weight = model_table['games'].values.astype(float)

    log.info(f"Features: {X.shape[1]} columns")
    log.info(f"Samples: {len(y):,}")
    log.info(f"Target range: [{y.min():.3f}, {y.max():.3f}]")
    log.info(f"Sample weights (games): min={sample_weight.min():.0f}, max={sample_weight.max():.0f}, mean={sample_weight.mean():.1f}")

    return X, y, sample_weight


def fit_model(X_train, y_train, w_train, model_name, max_depth=3, n_rounds=100):
    """Fit XGBoost model."""
    log.info(f"\nFitting {model_name}...")
    log.info(f"  Training samples: {len(X_train):,}")
    log.info(f"  Features: {X_train.shape[1]}")

    # Create DMatrix
    dtrain = xgb.DMatrix(X_train, label=y_train, weight=w_train)

    # XGBoost parameters for grouped binomial (logistic)
    params = {
        'objective': 'binary:logistic',
        'max_depth': max_depth,
        'eta': 0.1,
        'gamma': 0,
        'min_child_weight': 1,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'seed': 42,
    }

    # Train
    evals_result = {}
    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=n_rounds,
        evals=[(dtrain, 'train')],
        evals_result=evals_result,
        verbose_eval=False
    )

    final_loss = evals_result['train']['logloss'][-1]
    log.info(f"  Final train loss: {final_loss:.4f}")

    return booster, evals_result


def evaluate_model(booster, X_test, y_test, w_test, model_name):
    """Evaluate model on test set."""
    log.info(f"\nEvaluating {model_name} on test set...")

    dtest = xgb.DMatrix(X_test, label=y_test, weight=w_test)
    predictions = booster.predict(dtest)

    # Compute weighted log loss (binary logistic)
    # L = -sum(w * (y*log(p) + (1-y)*log(1-p))) / sum(w)
    eps = 1e-7
    pred_clipped = np.clip(predictions, eps, 1 - eps)
    binary_loss = -(y_test * np.log(pred_clipped) + (1 - y_test) * np.log(1 - pred_clipped))
    test_loss = np.average(binary_loss, weights=w_test)

    # Compute other metrics
    residuals = y_test - predictions
    weighted_rmse = np.sqrt(np.average(residuals**2, weights=w_test))
    weighted_mae = np.average(np.abs(residuals), weights=w_test)

    log.info(f"  Test log-loss: {test_loss:.4f}")
    log.info(f"  Test weighted RMSE: {weighted_rmse:.4f}")
    log.info(f"  Test weighted MAE: {weighted_mae:.4f}")

    return {
        'model': model_name,
        'test_loss': test_loss,
        'test_weighted_rmse': weighted_rmse,
        'test_weighted_mae': weighted_mae,
        'n_features': X_test.shape[1],
    }


def save_model(booster, model_name):
    """Save model to file."""
    model_path = RESULTS_DIR / f"{model_name}.xgb"
    booster.save_model(str(model_path))
    log.info(f"  Saved to {model_path}")
    return model_path


def main():
    log.info("=" * 70)
    log.info("Step 6-7: Fit M0 (Skill Only) & M1 (Skill + Identity)")
    log.info("=" * 70)

    # Load data
    model_table, identity_df, card_cols = load_data()

    # Get dev/holdout split
    dev_mask = model_table['split'] == 'dev'
    holdout_mask = model_table['split'] == 'holdout'

    results = []

    # ===================================================================
    # M0: SKILL ONLY (base_p)
    # ===================================================================
    log.info("\n" + "=" * 70)
    log.info("M0: Skill Only (base_p feature)")
    log.info("=" * 70)

    X_train, y_train, w_train = prepare_features(
        model_table[dev_mask], identity_df, card_cols, use_identity=False
    )
    X_test, y_test, w_test = prepare_features(
        model_table[holdout_mask], identity_df, card_cols, use_identity=False
    )

    m0_booster, m0_evals = fit_model(X_train, y_train, w_train, "M0", max_depth=2, n_rounds=50)
    m0_results = evaluate_model(m0_booster, X_test, y_test, w_test, "M0")
    results.append(m0_results)
    save_model(m0_booster, "m0_skill_only")

    # ===================================================================
    # M1: SKILL + CARD IDENTITY
    # ===================================================================
    log.info("\n" + "=" * 70)
    log.info("M1: Skill + Card Identity (base_p + 193 cards)")
    log.info("=" * 70)

    X_train, y_train, w_train = prepare_features(
        model_table[dev_mask], identity_df, card_cols, use_identity=True
    )
    X_test, y_test, w_test = prepare_features(
        model_table[holdout_mask], identity_df, card_cols, use_identity=True
    )

    m1_booster, m1_evals = fit_model(X_train, y_train, w_train, "M1", max_depth=3, n_rounds=100)
    m1_results = evaluate_model(m1_booster, X_test, y_test, w_test, "M1")
    results.append(m1_results)
    save_model(m1_booster, "m1_skill_identity")

    # ===================================================================
    # COMPARISON
    # ===================================================================
    log.info("\n" + "=" * 70)
    log.info("Model Comparison Summary")
    log.info("=" * 70)

    comparison_df = pd.DataFrame(results)
    log.info("\n" + str(comparison_df.to_string(index=False)))

    # Compute improvement
    m0_loss = m0_results['test_loss']
    m1_loss = m1_results['test_loss']
    improvement = ((m0_loss - m1_loss) / m0_loss) * 100

    log.info(f"\nM1 improvement over M0:")
    log.info(f"  Log-loss: {m0_loss:.4f} → {m1_loss:.4f} ({improvement:+.2f}%)")
    log.info(f"  Features: {m0_results['n_features']} → {m1_results['n_features']}")

    # Save comparison
    comparison_df.to_csv(RESULTS_DIR / "m0_m1_comparison.csv", index=False)
    log.info(f"\nSaved comparison to m0_m1_comparison.csv")

    log.info("\n" + "=" * 70)
    log.info("✓ M0 and M1 models fitted and saved")
    log.info("=" * 70)

    return m0_booster, m1_booster, comparison_df


if __name__ == "__main__":
    main()
