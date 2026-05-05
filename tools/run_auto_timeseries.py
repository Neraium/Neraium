import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def detect_timestamp_column(df):
    for col in df.columns:
        try:
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().mean() > 0.8:
                return col
        except Exception:
            continue
    return None


def detect_numeric(df):
    numeric = []
    for col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().mean() > 0.7 and s.nunique() > 1:
            numeric.append(col)
    return numeric


def detect_asset_column(df):
    for col in df.columns:
        if df[col].nunique() < len(df) * 0.2 and df[col].dtype == object:
            return col
    return None


def robust_center_scale(arr):
    arr = np.asarray(arr)
    arr = arr[np.isfinite(arr)]

    if len(arr) == 0:
        return 0.0, 1.0

    med = np.median(arr)
    mad = np.median(np.abs(arr - med))

    scale = 1.4826 * mad
    if scale < 0.05:
        scale = np.std(arr)
    if scale < 0.05:
        scale = 0.05

    return med, scale


def run_engine(df, numeric_cols, baseline_window=288, min_baseline=72):
    rows = []
    prev_drift = 0.0
    persistence = 0

    for i in range(len(df)):
        row = df.iloc[i]

        if i < min_baseline:
            rows.append({"state": "INITIALIZING"})
            continue

        base = df.iloc[max(0, i - baseline_window):i]

        z_scores = []

        for col in numeric_cols:
            c, s = robust_center_scale(base[col].values)
            z = (row[col] - c) / s
            z = max(min(z, 10), -10)
            z_scores.append(abs(z))

        drift = float(np.median(z_scores))
        velocity = drift - prev_drift

        if drift >= 2.8:
            persistence += 1
        else:
            persistence = 0

        if drift >= 6.5 and velocity > 1:
            state = "ALERT"
        elif persistence >= 12 and drift >= 5:
            state = "ALERT"
        elif persistence >= 12 and drift >= 2.8:
            state = "WATCH"
        else:
            state = "STABLE"

        rows.append({
            "state": state,
            "drift": drift,
            "persistence": persistence
        })

        prev_drift = drift

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    df = pd.read_csv(args.input, low_memory=False)

    ts_col = detect_timestamp_column(df)
    asset_col = detect_asset_column(df)
    numeric_cols = detect_numeric(df)

    print("\nAUTO DETECTION")
    print("Timestamp:", ts_col)
    print("Asset column:", asset_col)
    print("Numeric signals:", len(numeric_cols))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if asset_col:
        groups = df.groupby(asset_col)
    else:
        groups = [("default_asset", df)]

    summaries = []

    for asset, g in groups:
        g = g.copy()

        if ts_col:
            g = g.sort_values(ts_col)

        result = run_engine(g, numeric_cols)

        summary = {
            "asset": str(asset),
            "samples": len(result),
            "state_counts": result["state"].value_counts().to_dict(),
            "watch_or_worse": float(
                result["state"].isin(["WATCH", "ALERT"]).mean() * 100
            )
        }

        summaries.append(summary)

        result.to_csv(out_dir / f"{asset}_results.csv", index=False)

    with open(out_dir / "summary.json", "w") as f:
        json.dump(summaries, f, indent=2)

    print("\nDONE")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
