"""
Apply the trained model to all snapshots (or the recent window) and
persist scores to `ml_scores` plus `signals.ml_prob`/`ml_direction`.

Runs in two modes:

- full:     re-score every snapshot (used after training)
- recent:   only score snapshots newer than `since_ts` (default: 24h)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

import joblib

from ml.features import build_matrix
from ml.train import METRICS_PATH, MODEL_PATH

DEFAULT_RECENT_HOURS = 24
MODEL_HMAC_KEY = os.environ.get("MODEL_HMAC_KEY", "").encode()


def load_model_safely(model_path: Path):
    if not MODEL_HMAC_KEY:
        raise RuntimeError("MODEL_HMAC_KEY env var not set; refuse to load untrusted model")
    sig_path = model_path.with_suffix(model_path.suffix + ".sig")
    if not sig_path.exists():
        raise RuntimeError(f"Missing signature file: {sig_path}")
    expected = sig_path.read_text().strip()
    actual = hmac.new(MODEL_HMAC_KEY, model_path.read_bytes(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, actual):
        raise RuntimeError("Model signature mismatch — refusing to load")
    return joblib.load(model_path)


def score(db_path: Path | str, mode: str = "recent", hours: int = DEFAULT_RECENT_HOURS) -> Dict[str, int]:
    metrics = None
    if METRICS_PATH.exists():
        try:
            metrics = json.loads(METRICS_PATH.read_text())
        except json.JSONDecodeError:
            metrics = None
    if metrics and metrics.get("status") != "ok":
        return {"status": f"model_{metrics.get('status')}", "scored": 0}
    if not MODEL_PATH.exists():
        return {"status": "no_model", "scored": 0}

    bundle = load_model_safely(MODEL_PATH)
    model = bundle["model"]
    feature_names = bundle["feature_names"]
    model_version = bundle.get("trained_ts", "unknown")
    if metrics and metrics.get("trained_ts") and metrics.get("trained_ts") != model_version:
        return {"status": "stale_model_artifact", "scored": 0}

    df, _y, snapshot_ids, built_names = build_matrix(
        db_path,
        labeled_only=False,
        include_patterns=False,
    )
    if df.empty:
        return {"status": "empty", "scored": 0}

    for col in feature_names:
        if col not in df.columns:
            df[col] = 0.0
    df = df[feature_names]

    probs = model.predict_proba(df)[:, 1]

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cutoff_ts = None
        if mode == "recent":
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        snap_meta = {
            row["id"]: (row["ts"], row["chain"], row["address"], row["symbol"])
            for row in conn.execute(
                "SELECT id, ts, chain, address, symbol FROM token_snapshots"
            ).fetchall()
        }

        now = datetime.now(timezone.utc).isoformat()
        written = 0
        for snap_id, prob in zip(snapshot_ids, probs):
            meta = snap_meta.get(snap_id)
            if not meta:
                continue
            ts, chain, address, symbol = meta
            if cutoff_ts and ts < cutoff_ts:
                continue
            direction = "up" if prob >= 0.55 else ("down" if prob <= 0.45 else "flat")
            conn.execute(
                """
                INSERT INTO ml_scores(
                    snapshot_id, ts, chain, address, symbol,
                    ml_prob, ml_direction, model_version, feature_snapshot_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    ml_prob = excluded.ml_prob,
                    ml_direction = excluded.ml_direction,
                    model_version = excluded.model_version
                """,
                (snap_id, ts, chain, address, symbol,
                 float(prob), direction, model_version, None),
            )
            conn.execute(
                "UPDATE signals SET ml_prob = ?, ml_direction = ? WHERE snapshot_id = ?",
                (float(prob), direction, snap_id),
            )
            written += 1
        conn.commit()
        return {"status": "ok", "scored": written, "total_snapshots": len(snapshot_ids)}
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "recent"
    db = sys.argv[2] if len(sys.argv) > 2 else "data/birdeye_quant.db"
    print(json.dumps(score(db, mode=mode), indent=2))
