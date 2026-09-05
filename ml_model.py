"""
§13 — Machine-Learning layer, added only on top of the statistical
foundation in pattern_db.py, exactly as the doc recommends ("add machine
learning only after establishing the statistical foundation").

Baseline model: logistic regression on the same features already computed
by the other engines (no separate feature pipeline to keep in sync).
Falls back to GradientBoostingClassifier if there's enough data, mirroring
the doc's "XGBoost is often a strong starting point" without adding a hard
dependency — scikit-learn's GradientBoostingClassifier plays the same role
here with zero extra install for most environments.

If scikit-learn isn't installed, or there isn't enough labeled history yet,
predict() returns a neutral score with an explanatory note instead of
raising — the rest of the pipeline (signal_fusion) treats ML as one vote
among many, not a hard dependency.
"""
import os
import pickle

import numpy as np
import pandas as pd

import config
import pattern_db

FEATURE_COLUMNS = [
    "trend_score", "momentum_score", "mean_reversion_score",
    "volume_score", "structure_score", "relative_strength_score", "rvol",
]


def _label(fwd_ret: pd.Series, threshold: float = 0.0) -> pd.Series:
    return (fwd_ret > threshold).astype(int)


def train(horizon: int = 10) -> dict:
    df = pattern_db.load_labeled()
    col = f"fwd_ret_{horizon}"
    if df.empty or col not in df.columns:
        return {"trained": False, "reason": "no labeled observations yet — run scans, then "
                                             "`python pattern_db.py backfill` after enough time has passed"}

    sub = df.dropna(subset=FEATURE_COLUMNS + [col])
    if len(sub) < config.ML_MIN_TRAINING_ROWS:
        return {"trained": False, "reason": f"only {len(sub)} labeled rows, need "
                                             f"{config.ML_MIN_TRAINING_ROWS}+"}

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import train_test_split
    except ImportError:
        return {"trained": False, "reason": "scikit-learn not installed (pip install scikit-learn)"}

    X = sub[FEATURE_COLUMNS].values
    y = _label(sub[col]).values

    if len(np.unique(y)) < 2:
        return {"trained": False, "reason": "labeled data is all one class so far — need more variety"}

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)

    if len(sub) >= config.ML_MIN_TRAINING_ROWS * 2:
        model = GradientBoostingClassifier(random_state=42)
        model_name = "GradientBoostingClassifier"
    else:
        model = LogisticRegression(max_iter=1000)
        model_name = "LogisticRegression"

    model.fit(X_train, y_train)
    test_acc = float(model.score(X_test, y_test))

    with open(config.ML_MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "model_name": model_name, "horizon": horizon,
                     "features": FEATURE_COLUMNS, "trained_on_rows": len(sub)}, f)

    return {"trained": True, "model_name": model_name, "test_accuracy": round(test_acc, 3),
            "trained_on_rows": len(sub), "horizon": horizon}


def _load_model():
    if not os.path.exists(config.ML_MODEL_PATH):
        return None
    try:
        with open(config.ML_MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def predict(feature_row: dict) -> dict:
    bundle = _load_model()
    if bundle is None:
        return {"ml_score": 0.0, "ml_available": False,
                "note": "no trained model yet — run `python ml_model.py train`"}

    x = np.array([[feature_row.get(c, 0.0) or 0.0 for c in bundle["features"]]])
    try:
        proba_up = float(bundle["model"].predict_proba(x)[0][1])
    except Exception as e:
        return {"ml_score": 0.0, "ml_available": False, "note": f"prediction failed: {e}"}

    # map P(up) in [0,1] to a score in [-1, 1]
    ml_score = round((proba_up - 0.5) * 2, 3)
    return {"ml_score": ml_score, "ml_available": True, "ml_proba_up": round(proba_up, 3),
            "ml_model_name": bundle.get("model_name")}


if __name__ == "__main__":
    print(train())
