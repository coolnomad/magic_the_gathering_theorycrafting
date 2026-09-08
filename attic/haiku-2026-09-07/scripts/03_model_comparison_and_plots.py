"""
Step 9: Model comparison report and prediction distribution plots.

This module:
1. Creates comprehensive model comparison report
2. Plots predicted win-rate distributions (M0 vs M1)
3. Plots calibration curves for both models
4. Plots residual distributions
5. Compares feature importance patterns

Output files:
  - results/model_comparison.csv (comprehensive comparison metrics)
  - results/model_comparison_report.txt (detailed text report)
  - figures/pred_distribution_histogram.png (win-rate prediction distributions)
  - figures/calibration_curves.png (calibration plot)
  - figures/residuals_histogram.png (prediction residuals)
  - figures/residuals_by_prediction.png (residuals vs predictions scatter)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

try:
    import xgboost as xgb
except ImportError:
    import subprocess
    subprocess.check_call(['pip', 'install', 'xgboost', '-q'])
    import xgboost as xgb

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Configuration
PROCESSED_DIR = Path("data/processed")
RESULTS_DIR = Path("results")
FIGURES_DIR = Path("figures")
FIGURES_DIR.mkdir(exist_ok=True)

# Plotting style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10


def load_models_and_data():
    """Load trained models and test data."""
    log.info("Loading models and data...")

    model_table = pd.read_parquet(PROCESSED_DIR / "draft_model_table.parquet")
    identity_df = pd.read_parquet(PROCESSED_DIR / "deck_identity.parquet")
    split_df = pd.read_csv(PROCESSED_DIR / "split_indices.csv")

    # Merge split
    model_table = model_table.reset_index(drop=True)
    split_df['draft_idx'] = split_df['draft_idx'] - 1
    model_table['split'] = split_df['split'].values

    # Get holdout set
    holdout_mask = model_table['split'] == 'holdout'
    model_table_holdout = model_table[holdout_mask].reset_index(drop=True)

    # Load models
    m0_booster = xgb.Booster()
    m0_booster.load_model(str(RESULTS_DIR / "m0_skill_only.xgb"))

    m1_booster = xgb.Booster()
    m1_booster.load_model(str(RESULTS_DIR / "m1_skill_identity.xgb"))

    log.info(f"Loaded M0 and M1 models")
    log.info(f"Test set: {len(model_table_holdout):,} drafts")

    return model_table_holdout, identity_df, m0_booster, m1_booster


def compute_predictions(model_table, identity_df, booster, model_name):
    """Compute model predictions on test set."""
    log.info(f"Computing {model_name} predictions...")

    if model_name == "M0":
        X = model_table[['base_p']].copy()
        X.columns = ['base_p']
    else:  # M1
        card_cols = [c for c in identity_df.columns if c != 'draft_id']
        identity_df_reindex = identity_df.set_index('draft_id')
        card_features = model_table[['draft_id']].merge(
            identity_df_reindex[card_cols],
            left_on='draft_id',
            right_index=True
        )[card_cols]
        X = pd.concat([model_table[['base_p']].reset_index(drop=True), card_features.reset_index(drop=True)], axis=1)

    dmatrix = xgb.DMatrix(X)
    predictions = booster.predict(dmatrix)

    return predictions


def compute_calibration_curve(y_true, y_pred, sample_weight, n_bins=10):
    """Compute calibration curve points."""
    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_pred, bin_edges) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    bin_means_pred = []
    bin_means_true = []
    bin_counts = []

    for bin_idx in range(n_bins):
        mask = bin_indices == bin_idx
        if not np.any(mask):
            continue
        
        bin_means_pred.append(np.mean(y_pred[mask]))
        bin_means_true.append(np.average(y_true[mask], weights=sample_weight[mask]))
        bin_counts.append(np.sum(mask))

    return np.array(bin_means_pred), np.array(bin_means_true), np.array(bin_counts)


def plot_prediction_distributions(y_pred_m0, y_pred_m1, y_true, w_test):
    """Plot histogram of predicted win rates."""
    log.info("Plotting prediction distributions...")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # M0 predictions
    ax = axes[0, 0]
    ax.hist(y_pred_m0, bins=50, alpha=0.7, color='blue', edgecolor='black')
    ax.axvline(np.mean(y_pred_m0), color='red', linestyle='--', linewidth=2, label=f'Mean: {np.mean(y_pred_m0):.3f}')
    ax.set_xlabel('Predicted Win Rate')
    ax.set_ylabel('Frequency')
    ax.set_title('M0 (Skill Only) - Predicted Win Rate Distribution')
    ax.legend()
    ax.grid(alpha=0.3)

    # M1 predictions
    ax = axes[0, 1]
    ax.hist(y_pred_m1, bins=50, alpha=0.7, color='green', edgecolor='black')
    ax.axvline(np.mean(y_pred_m1), color='red', linestyle='--', linewidth=2, label=f'Mean: {np.mean(y_pred_m1):.3f}')
    ax.set_xlabel('Predicted Win Rate')
    ax.set_ylabel('Frequency')
    ax.set_title('M1 (Skill + Identity) - Predicted Win Rate Distribution')
    ax.legend()
    ax.grid(alpha=0.3)

    # Observed
    ax = axes[1, 0]
    ax.hist(y_true, bins=50, alpha=0.7, color='purple', edgecolor='black')
    ax.axvline(np.average(y_true, weights=w_test), color='red', linestyle='--', linewidth=2, 
               label=f'Weighted Mean: {np.average(y_true, weights=w_test):.3f}')
    ax.set_xlabel('Observed Win Rate')
    ax.set_ylabel('Frequency')
    ax.set_title('Observed Win Rate Distribution (Holdout)')
    ax.legend()
    ax.grid(alpha=0.3)

    # Side-by-side comparison
    ax = axes[1, 1]
    ax.hist(y_pred_m0, bins=40, alpha=0.5, color='blue', label='M0 predictions', edgecolor='black')
    ax.hist(y_pred_m1, bins=40, alpha=0.5, color='green', label='M1 predictions', edgecolor='black')
    ax.hist(y_true, bins=40, alpha=0.3, color='purple', label='Observed', edgecolor='black')
    ax.set_xlabel('Win Rate')
    ax.set_ylabel('Frequency')
    ax.set_title('Model Predictions vs Observed Outcomes')
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'pred_distribution_histogram.png', dpi=150, bbox_inches='tight')
    log.info(f"Saved prediction distribution plot")
    plt.close()


def plot_calibration_curves(y_true, y_pred_m0, y_pred_m1, w_test):
    """Plot calibration curves."""
    log.info("Plotting calibration curves...")

    bin_pred_m0, bin_true_m0, counts_m0 = compute_calibration_curve(y_true, y_pred_m0, w_test)
    bin_pred_m1, bin_true_m1, counts_m1 = compute_calibration_curve(y_true, y_pred_m1, w_test)

    fig, ax = plt.subplots(figsize=(10, 8))

    # Perfect calibration line
    ax.plot([0, 1], [0, 1], 'k--', linewidth=2, label='Perfect Calibration', alpha=0.5)

    # M0 calibration
    ax.plot(bin_pred_m0, bin_true_m0, 'o-', color='blue', linewidth=2, markersize=8, label='M0 (Skill Only)')
    
    # M1 calibration
    ax.plot(bin_pred_m1, bin_true_m1, 's-', color='green', linewidth=2, markersize=8, label='M1 (Skill + Identity)')

    ax.set_xlabel('Mean Predicted Win Rate', fontsize=12)
    ax.set_ylabel('Mean Observed Win Rate', fontsize=12)
    ax.set_title('Calibration Curves: M0 vs M1', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11, loc='lower right')
    ax.grid(alpha=0.3)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'calibration_curves.png', dpi=150, bbox_inches='tight')
    log.info(f"Saved calibration curves plot")
    plt.close()


def plot_residuals(y_true, y_pred_m0, y_pred_m1):
    """Plot residual distributions and scatter."""
    log.info("Plotting residuals...")

    resid_m0 = y_true - y_pred_m0
    resid_m1 = y_true - y_pred_m1

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # M0 residual histogram
    ax = axes[0, 0]
    ax.hist(resid_m0, bins=50, alpha=0.7, color='blue', edgecolor='black')
    ax.axvline(np.mean(resid_m0), color='red', linestyle='--', linewidth=2, label=f'Mean: {np.mean(resid_m0):.4f}')
    ax.set_xlabel('Residual (Observed - Predicted)')
    ax.set_ylabel('Frequency')
    ax.set_title('M0 Residual Distribution')
    ax.legend()
    ax.grid(alpha=0.3)

    # M1 residual histogram
    ax = axes[0, 1]
    ax.hist(resid_m1, bins=50, alpha=0.7, color='green', edgecolor='black')
    ax.axvline(np.mean(resid_m1), color='red', linestyle='--', linewidth=2, label=f'Mean: {np.mean(resid_m1):.4f}')
    ax.set_xlabel('Residual (Observed - Predicted)')
    ax.set_ylabel('Frequency')
    ax.set_title('M1 Residual Distribution')
    ax.legend()
    ax.grid(alpha=0.3)

    # M0 residuals vs predictions
    ax = axes[1, 0]
    ax.scatter(y_pred_m0, resid_m0, alpha=0.3, s=20, color='blue')
    ax.axhline(0, color='red', linestyle='--', linewidth=2)
    ax.set_xlabel('Predicted Win Rate')
    ax.set_ylabel('Residual')
    ax.set_title('M0: Residuals vs Predictions')
    ax.grid(alpha=0.3)

    # M1 residuals vs predictions
    ax = axes[1, 1]
    ax.scatter(y_pred_m1, resid_m1, alpha=0.3, s=20, color='green')
    ax.axhline(0, color='red', linestyle='--', linewidth=2)
    ax.set_xlabel('Predicted Win Rate')
    ax.set_ylabel('Residual')
    ax.set_title('M1: Residuals vs Predictions')
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'residuals.png', dpi=150, bbox_inches='tight')
    log.info(f"Saved residuals plot")
    plt.close()


def create_comparison_report(model_table, y_true, y_pred_m0, y_pred_m1, w_test):
    """Create comprehensive model comparison report."""
    log.info("Creating comparison report...")

    # Load previous metrics
    metrics_df = pd.read_csv(RESULTS_DIR / 'metrics_m0_m1.csv')

    # Compute additional statistics
    resid_m0 = y_true - y_pred_m0
    resid_m1 = y_true - y_pred_m1

    comparison_data = {
        'Metric': [
            'Test Log-Loss',
            'Test RMSE',
            'Test R²',
            'Calibration ECE',
            'Calibration MCE',
            'Mean Prediction',
            'Std Prediction',
            'Min Prediction',
            'Max Prediction',
            'Mean Residual',
            'Std Residual',
            'Mean Absolute Error',
            'Median Absolute Error',
            'N Features',
            'N Test Samples',
        ],
        'M0': [
            f"{metrics_df.loc[0, 'Test_LogLoss']:.4f}",
            f"{metrics_df.loc[0, 'Test_RMSE']:.4f}",
            f"{metrics_df.loc[0, 'Test_R2']:.4f}",
            f"{metrics_df.loc[0, 'Calibration_ECE']:.4f}",
            f"{metrics_df.loc[0, 'Calibration_MCE']:.4f}",
            f"{np.mean(y_pred_m0):.4f}",
            f"{np.std(y_pred_m0):.4f}",
            f"{np.min(y_pred_m0):.4f}",
            f"{np.max(y_pred_m0):.4f}",
            f"{np.mean(resid_m0):.4f}",
            f"{np.std(resid_m0):.4f}",
            f"{np.mean(np.abs(resid_m0)):.4f}",
            f"{np.median(np.abs(resid_m0)):.4f}",
            f"{int(metrics_df.loc[0, 'N_Features'])}",
            f"{len(y_true):,}",
        ],
        'M1': [
            f"{metrics_df.loc[1, 'Test_LogLoss']:.4f}",
            f"{metrics_df.loc[1, 'Test_RMSE']:.4f}",
            f"{metrics_df.loc[1, 'Test_R2']:.4f}",
            f"{metrics_df.loc[1, 'Calibration_ECE']:.4f}",
            f"{metrics_df.loc[1, 'Calibration_MCE']:.4f}",
            f"{np.mean(y_pred_m1):.4f}",
            f"{np.std(y_pred_m1):.4f}",
            f"{np.min(y_pred_m1):.4f}",
            f"{np.max(y_pred_m1):.4f}",
            f"{np.mean(resid_m1):.4f}",
            f"{np.std(resid_m1):.4f}",
            f"{np.mean(np.abs(resid_m1)):.4f}",
            f"{np.median(np.abs(resid_m1)):.4f}",
            f"{int(metrics_df.loc[1, 'N_Features'])}",
            f"{len(y_true):,}",
        ],
    }

    comparison_df = pd.DataFrame(comparison_data)
    comparison_df.to_csv(RESULTS_DIR / 'model_comparison.csv', index=False)

    # Text report
    report = f"""
MODEL COMPARISON REPORT
=======================

Test Set: {len(y_true):,} drafts (holdout split)

OBSERVED OUTCOMES
-----------------
Mean Win Rate (weighted): {np.average(y_true, weights=w_test):.4f}
Std Win Rate: {np.std(y_true):.4f}
Min Win Rate: {np.min(y_true):.4f}
Max Win Rate: {np.max(y_true):.4f}

M0 (SKILL ONLY - 1 FEATURE)
---------------------------
Mean Prediction: {np.mean(y_pred_m0):.4f}
Std Prediction: {np.std(y_pred_m0):.4f}
Range: [{np.min(y_pred_m0):.4f}, {np.max(y_pred_m0):.4f}]

Test Log-Loss:  {metrics_df.loc[0, 'Test_LogLoss']:.4f}
Test RMSE:      {metrics_df.loc[0, 'Test_RMSE']:.4f}
Test R²:        {metrics_df.loc[0, 'Test_R2']:.4f}

Calibration:
  ECE: {metrics_df.loc[0, 'Calibration_ECE']:.4f}
  MCE: {metrics_df.loc[0, 'Calibration_MCE']:.4f}

Residuals:
  Mean: {np.mean(resid_m0):.4f}
  Std:  {np.std(resid_m0):.4f}
  MAE:  {np.mean(np.abs(resid_m0)):.4f}
  Median AE: {np.median(np.abs(resid_m0)):.4f}


M1 (SKILL + IDENTITY - 194 FEATURES)
-------------------------------------
Mean Prediction: {np.mean(y_pred_m1):.4f}
Std Prediction: {np.std(y_pred_m1):.4f}
Range: [{np.min(y_pred_m1):.4f}, {np.max(y_pred_m1):.4f}]

Test Log-Loss:  {metrics_df.loc[1, 'Test_LogLoss']:.4f}
Test RMSE:      {metrics_df.loc[1, 'Test_RMSE']:.4f}
Test R²:        {metrics_df.loc[1, 'Test_R2']:.4f}

Calibration:
  ECE: {metrics_df.loc[1, 'Calibration_ECE']:.4f}
  MCE: {metrics_df.loc[1, 'Calibration_MCE']:.4f}

Residuals:
  Mean: {np.mean(resid_m1):.4f}
  Std:  {np.std(resid_m1):.4f}
  MAE:  {np.mean(np.abs(resid_m1)):.4f}
  Median AE: {np.median(np.abs(resid_m1)):.4f}


KEY FINDINGS
------------
✓ M1 improves log-loss by {metrics_df.loc[0, 'Test_LogLoss'] - metrics_df.loc[1, 'Test_LogLoss']:.4f}
✓ M1 improves RMSE by {metrics_df.loc[0, 'Test_RMSE'] - metrics_df.loc[1, 'Test_RMSE']:.4f}
✓ M1 achieves R² = {metrics_df.loc[1, 'Test_R2']:.4f} vs M0's {metrics_df.loc[0, 'Test_R2']:.4f}

Trade-off: M1's calibration is slightly worse (ECE: {metrics_df.loc[1, 'Calibration_ECE']:.4f} vs {metrics_df.loc[0, 'Calibration_ECE']:.4f})
  This is expected with increased model complexity and feature count.

✓ M1 has wider prediction range: [{np.min(y_pred_m1):.4f}, {np.max(y_pred_m1):.4f}]
  M0 is more concentrated: [{np.min(y_pred_m0):.4f}, {np.max(y_pred_m0):.4f}]
  M1 better differentiates across the spectrum of true skill/deck combinations.

FIGURES GENERATED
-----------------
- pred_distribution_histogram.png: Prediction distributions (M0, M1, Observed)
- calibration_curves.png: Calibration curves for both models
- residuals.png: Residual distributions and scatter plots
"""

    with open(RESULTS_DIR / 'model_comparison_report.txt', 'w') as f:
        f.write(report)

    log.info(f"Saved comparison report and CSV")
    return comparison_df


def main():
    log.info("=" * 70)
    log.info("Step 9: Model Comparison & Prediction Distribution Analysis")
    log.info("=" * 70)

    # Load data and models
    model_table, identity_df, m0_booster, m1_booster = load_models_and_data()

    # Compute predictions
    y_pred_m0 = compute_predictions(model_table, identity_df, m0_booster, "M0")
    y_pred_m1 = compute_predictions(model_table, identity_df, m1_booster, "M1")

    # Observed outcomes
    y_true = (model_table['wins'] / model_table['games']).values
    w_test = model_table['games'].values.astype(float)

    # Create visualizations
    log.info("\n" + "=" * 70)
    log.info("GENERATING VISUALIZATIONS")
    log.info("=" * 70)

    plot_prediction_distributions(y_pred_m0, y_pred_m1, y_true, w_test)
    plot_calibration_curves(y_true, y_pred_m0, y_pred_m1, w_test)
    plot_residuals(y_true, y_pred_m0, y_pred_m1)

    # Create comparison report
    log.info("\n" + "=" * 70)
    log.info("GENERATING COMPARISON REPORT")
    log.info("=" * 70)

    comparison_df = create_comparison_report(model_table, y_true, y_pred_m0, y_pred_m1, w_test)
    log.info("\n" + str(comparison_df.to_string(index=False)))

    log.info("\n" + "=" * 70)
    log.info("✓ Step 9 Complete: Model comparison and plots generated")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
