"""
Train a supervised classifier on the feature matrix.

Default: LightGBM (fast, small artifact). Falls back to
sklearn GradientBoostingClassifier if LightGBM isn't installed.

Refuses to train on fewer than `MIN_SAMPLES` labeled rows; the cold-start
is expected for the first few days and should not fail the workflow.
"""
from __future__ import annotations

import hashlib
import hmac
import joblib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ml.features import build_matrix

MIN_SAMPLES = 50
MIN_CLASS_SAMPLES = 8
MIN_VALIDATION_ROWS = 10
VALIDATION_FRACTION = 0.2
MODEL_PATH = Path("ml/model.pkl")
METRICS_PATH = Path("ml/metrics.json")
MODEL_HMAC_KEY = os.environ.get("MODEL_HMAC_KEY", "").encode()


def train(db_path: Path | str) -> Dict[str, Any]:
    import numpy as np

    df, y, _ids, feature_names = build_matrix(
        db_path,
        labeled_only=True,
        include_patterns=False,
    )
    labeled = (y != -1)
    df = df[labeled]
    y = y[labeled]

    pos_count = int((y == 1).sum())
    neg_count = int((y == 0).sum())
    if len(df) < MIN_SAMPLES:
        return _write_metrics({
            "status": "insufficient_data",
            "labeled_rows": int(len(df)),
            "required": MIN_SAMPLES,
            "class_counts": {"positive": pos_count, "negative": neg_count},
            "trained_ts": datetime.now(timezone.utc).isoformat(),
            "validation_mode": "time_holdout",
            "pattern_features_used": False,
        })

    if min(pos_count, neg_count) < MIN_CLASS_SAMPLES:
        return _write_metrics({
            "status": "insufficient_class_balance",
            "labeled_rows": int(len(df)),
            "required_per_class": MIN_CLASS_SAMPLES,
            "class_counts": {"positive": pos_count, "negative": neg_count},
            "trained_ts": datetime.now(timezone.utc).isoformat(),
            "validation_mode": "time_holdout",
            "pattern_features_used": False,
        })

    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    val_rows = max(MIN_VALIDATION_ROWS, int(np.ceil(len(df) * VALIDATION_FRACTION)))
    val_rows = min(val_rows, max(1, len(df) - MIN_CLASS_SAMPLES * 2))
    split_at = len(df) - val_rows
    if split_at <= 0:
        split_at = max(1, len(df) - 1)

    X_train = df.iloc[:split_at]
    X_val = df.iloc[split_at:]
    y_train = y[:split_at]
    y_val = y[split_at:]

    if len(set(y_train)) < 2 or len(set(y_val)) < 2:
        return _write_metrics({
            "status": "insufficient_validation_balance",
            "labeled_rows": int(len(df)),
            "train_rows": int(len(y_train)),
            "validation_rows": int(len(y_val)),
            "class_counts": {
                "train_positive": int((y_train == 1).sum()),
                "train_negative": int((y_train == 0).sum()),
                "validation_positive": int((y_val == 1).sum()),
                "validation_negative": int((y_val == 0).sum()),
            },
            "trained_ts": datetime.now(timezone.utc).isoformat(),
            "validation_mode": "time_holdout",
            "pattern_features_used": False,
        })

    model, model_kind = _build_model(y_train)
    model.fit(X_train, y_train)

    y_prob = model.predict_proba(X_val)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)
    majority_label = 1 if float((y_train == 1).mean()) >= 0.5 else 0
    baseline_pred = np.full_like(y_val, majority_label)
    pos_rate = float((y == 1).mean())

    final_model, final_model_kind = _build_model(y)
    final_model.fit(df, y)

    metrics = {
        "status": "ok",
        "model": final_model_kind,
        "trained_ts": datetime.now(timezone.utc).isoformat(),
        "labeled_rows": int(len(df)),
        "train_rows": int(len(y_train)),
        "validation_rows": int(len(y_val)),
        "positive_rate": pos_rate,
        "train_positive_rate": float((y_train == 1).mean()),
        "validation_positive_rate": float((y_val == 1).mean()),
        "accuracy": float(accuracy_score(y_val, y_pred)),
        "majority_baseline_accuracy": float(accuracy_score(y_val, baseline_pred)),
        "roc_auc": _safe_auc(y_val, y_prob),
        "precision": float(precision_score(y_val, y_pred, zero_division=0)),
        "recall": float(recall_score(y_val, y_pred, zero_division=0)),
        "f1": float(f1_score(y_val, y_pred, zero_division=0)),
        "feature_count": len(feature_names),
        "top_features": _top_features(final_model, feature_names, k=20),
        "validation_mode": "time_holdout",
        "pattern_features_used": False,
        "class_counts": {"positive": pos_count, "negative": neg_count},
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": final_model,
        "feature_names": feature_names,
        "model_kind": final_model_kind,
        "trained_ts": metrics["trained_ts"]
    }
    joblib.dump(bundle, MODEL_PATH)

    # Sign the model
    if MODEL_HMAC_KEY:
        sig = hmac.new(MODEL_HMAC_KEY, MODEL_PATH.read_bytes(), hashlib.sha256).hexdigest()
        MODEL_PATH.with_suffix(MODEL_PATH.suffix + ".sig").write_text(sig)
    
    _write_metrics(metrics)
    return metrics
    _write_metrics(metrics)
    return metrics


def _write_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


def _build_model(y_train):
    try:
        import lightgbm as lgb
        return lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=-1,
            num_leaves=31,
            min_child_samples=5,
            reg_lambda=1.0,
            class_weight="balanced",
            verbosity=-1,
        ), "lightgbm"
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3), "sklearn_gbt"


def _safe_auc(y_true, y_prob) -> float:
    from sklearn.metrics import roc_auc_score
    try:
        if len(set(y_true)) < 2:
            return 0.0
        return float(roc_auc_score(y_true, y_prob))
    except Exception:
        return 0.0


def _top_features(model, names, k: int):
    try:
        if hasattr(model, "feature_importances_"):
            imps = model.feature_importances_
        else:
            return []
        pairs = sorted(zip(names, imps), key=lambda p: -float(p[1]))[:k]
        return [{"name": n, "importance": float(v)} for n, v in pairs]
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    m = train(sys.argv[1] if len(sys.argv) > 1 else "data/birdeye_quant.db")
    print(json.dumps(m, indent=2))
