"""Simulate and visualize the MODEL-003 regime structure.

This is deliberately database-free. It uses the same feature names, scaling,
feature weights, HMM seed, and semantic mapping as ``hmm_regime`` so the plot
shows what the regime taxonomy is asking the model to separate.

Run from the repository root:
    python -m src.regime.simulate_scatter --output results/regime_simulation.png
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.decomposition import PCA
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)
from sklearn.preprocessing import StandardScaler

from src.regime import hmm_regime as H
from src.regime import mapping as M

TRUE_LABELS = np.array(M.SEMANTIC_ORDER)

# Approximate feature-space anchors in the raw feature units. The values are
# intentionally separated enough to make overlap visible rather than hiding it.
REGIME_MEANS = np.array(
    [
        [0.004, 25.0, 0.003, 0.0008, 0.0015],  # Trending-Up
        [0.004, 25.0, 0.003, -0.0008, -0.0015],  # Trending-Down
        [0.003, 12.0, 0.0015, 0.0, 0.0],  # Ranging
        [0.012, 35.0, 0.012, 0.0, 0.0],  # High-Vol
    ]
)
FEATURE_STD = np.array([0.0008, 4.0, 0.0008, 0.00045, 0.0008])


def simulate_features(
    bars_per_regime: int = 300, seed: int = H.SEED
) -> Tuple[pd.DataFrame, np.ndarray]:
    """Create a Markov-switching feature sequence and its known true labels."""
    if bars_per_regime < 10:
        raise ValueError("bars_per_regime must be at least 10")

    rng = np.random.default_rng(seed)
    n = bars_per_regime * len(TRUE_LABELS)
    states = np.empty(n, dtype=int)
    states[0] = 0
    transition = np.full((4, 4), 0.025)
    np.fill_diagonal(transition, 0.925)
    for i in range(1, n):
        states[i] = rng.choice(4, p=transition[states[i - 1]])

    values = REGIME_MEANS[states] + rng.normal(0.0, FEATURE_STD, size=(n, 5))
    features = pd.DataFrame(values, columns=H.FEATURE_NAMES)
    return features, states


def classify_simulation(
    features: pd.DataFrame,
) -> Tuple[np.ndarray, Dict[int, str], np.ndarray, np.ndarray]:
    """Fit the production-style HMM and return labels, mapping, X, and PCA."""
    scaler = StandardScaler()
    weights = np.array([H.FEATURE_WEIGHTS[name] for name in H.FEATURE_NAMES])
    X = scaler.fit_transform(features[H.FEATURE_NAMES]) * weights
    model = H.fit_hmm(X, [len(X)])
    mapping = M.map_states_to_labels(
        model.means_,
        H.FEATURE_NAMES,
        H.DIRECTION_FEATURE,
        tau=M.DEFAULT_TAU,
        order=H.LABEL_ORDER,
    )
    posterior_labels = np.array(
        [
            M.SEMANTIC_ORDER[i]
            for i in np.argmax(
                M.order_probabilities(model.predict_proba(X), mapping), axis=1
            )
        ]
    )
    coordinates = PCA(n_components=2, random_state=H.SEED).fit_transform(X)
    return posterior_labels, mapping, X, coordinates


def plot_simulation(
    features: pd.DataFrame,
    true_states: np.ndarray,
    predicted_labels: np.ndarray,
    coordinates: np.ndarray,
    output: Path,
) -> None:
    """Write paired feature-space and PCA scatter plots."""
    output.parent.mkdir(parents=True, exist_ok=True)
    colors = {
        "Trending-Up": "#168aad",
        "Trending-Down": "#d1495b",
        "Ranging": "#f0a202",
        "High-Vol": "#6a4c93",
    }
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)

    for label in TRUE_LABELS:
        mask = TRUE_LABELS[true_states] == label
        axes[0].scatter(
            features.loc[mask, H.DIRECTION_FEATURE],
            features.loc[mask, "volatility_20"],
            s=9,
            alpha=0.42,
            color=colors[label],
            label=label,
        )
    axes[0].set_title("Known simulated regimes")
    axes[0].set_xlabel("trend_20 (raw feature)")
    axes[0].set_ylabel("volatility_20 (raw feature)")

    for label in TRUE_LABELS:
        mask = predicted_labels == label
        axes[1].scatter(
            coordinates[mask, 0],
            coordinates[mask, 1],
            s=9,
            alpha=0.42,
            color=colors[label],
            label=label,
        )
    axes[1].set_title("HMM labels in weighted feature space")
    axes[1].set_xlabel("PCA 1")
    axes[1].set_ylabel("PCA 2")
    axes[1].legend(frameon=False, loc="best")

    fig.suptitle("MODEL-003 simulated regime structure", fontsize=15)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def evaluate_predictions(true_states: np.ndarray, predicted_labels: np.ndarray) -> None:
    """Print correctness, error severity, and per-regime error directions."""
    actual = TRUE_LABELS[true_states]
    matrix = confusion_matrix(actual, predicted_labels, labels=TRUE_LABELS)
    row_totals = matrix.sum(axis=1, keepdims=True)
    rates = matrix / np.maximum(row_totals, 1)

    print(f"overall accuracy: {accuracy_score(actual, predicted_labels):.3f}")
    print("\ncounts: rows=actual, columns=HMM prediction")
    print(pd.DataFrame(matrix, index=TRUE_LABELS, columns=TRUE_LABELS).to_string())
    print("\nrow percentages: each row sums to 100%; diagonal = correct")
    print(
        pd.DataFrame(
            rates * 100,
            index=TRUE_LABELS,
            columns=TRUE_LABELS,
        )
        .round(1)
        .to_string()
    )
    print("\nper-regime metrics:")
    print(
        classification_report(
            actual, predicted_labels, labels=TRUE_LABELS, zero_division=0
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars-per-regime", type=int, default=300)
    parser.add_argument("--seed", type=int, default=H.SEED)
    parser.add_argument(
        "--output", type=Path, default=Path("results/regime_simulation.png")
    )
    args = parser.parse_args()

    features, true_states = simulate_features(args.bars_per_regime, args.seed)
    predicted, mapping, _, coordinates = classify_simulation(features)
    plot_simulation(features, true_states, predicted, coordinates, args.output)
    print(f"saved {args.output}")
    print(f"HMM state mapping: {mapping}")
    print("predicted labels:", pd.Series(predicted).value_counts().to_dict())
    evaluate_predictions(true_states, predicted)


if __name__ == "__main__":
    main()
