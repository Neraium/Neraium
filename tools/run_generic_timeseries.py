import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


Z_CLAMP = 10.0


def robust_center_scale(window):
    arr = np.asarray(window, dtype=float)
    arr = arr[np.isfinite(arr)]

    if len(arr) == 0:
        return 0.0, 1.0

    center = float(np.median(arr))
    mad = float(np.median(np.abs(arr - center)))
    scale = 1.4826 * mad

    if not np.isfinite(scale) or scale < 0.05:
        scale = float(np.std(arr))

    if not np.isfinite(scale) or scale < 0.05:
        scale = 0.05

    return center, scale


def clean_numeric_frame(df, min_valid_ratio=0.70):
    numeric = pd.DataFrame(index=df.index)

    for col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")

        if s.notna().mean() < min_valid_ratio:
            continue

        if s.nunique(dropna=True) <= 1:
            continue

        numeric[col] = s

    numeric = numeric.replace([np.inf, -np.inf], np.nan)
    numeric = numeric.interpolate(limit_direction="both")
    numeric = numeric.dropna(axis=1, how="any")

    return numeric


def clamp_z(z):
    if not np.isfinite(z):
        return 0.0
    return max(min(float(z), Z_CLAMP), -Z_CLAMP)


def classify_state(drift, velocity, persistence):
    # Shock or hard discontinuity
    if drift >= 6.5 and velocity >= 1.0:
        return "ALERT", "STRUCTURAL_BREAK"

    # Persistent confirmed instability
    if persistence >= 12 and drift >= 5.0:
        return "ALERT", "PERSISTENT_STRUCTURAL_DRIFT"

    # Pre-instability tension
    if persistence >= 12 and drift >= 2.8:
        return "WATCH", "PRE_INSTABILITY_TENSION"

    # Sustained deviation
    if persistence >= 6 and drift >= 3.5:
        return "WATCH", "SUSTAINED_DEVIATION"

    return "STABLE", "ADAPTIVE_BASELINE"


def event_reason(event_type, state, regime):
    if event_type == "PRE_INSTABILITY":
        return "Sustained multi-signal tension emerged before confirmed break."
    if event_type == "INITIAL_INSTABILITY":
        return "First persistent deviation from adaptive rolling baseline."
    if event_type == "ESCALATION":
        return "Deviation escalated into confirmed structural break or persistent drift."
    return f"{state}/{regime}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--baseline-window", type=int, default=288)
    parser.add_argument("--min-baseline", type=int, default=72)
    parser.add_argument("--max-rows", type=int, default=0)

    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, low_memory=False)

    if args.max_rows and args.max_rows > 0:
        df = df.head(args.max_rows)

    numeric = clean_numeric_frame(df)

    if numeric.empty:
        raise RuntimeError("No usable numeric telemetry columns after cleaning.")

    rows = []
    prev_drift = 0.0
    deviation_persistence = 0

    for i in range(len(numeric)):
        row = numeric.iloc[i]

        if i < args.min_baseline:
            state = "INITIALIZING"
            regime = "BASELINE_FORMING"
            drift = 0.0
            velocity = 0.0
            pressure = 0.0
            drivers = ""
        else:
            start = max(0, i - args.baseline_window)
            baseline = numeric.iloc[start:i]

            z_scores = []

            for col in numeric.columns:
                center, scale = robust_center_scale(baseline[col].values)
                raw_z = (float(row[col]) - center) / scale
                z = clamp_z(raw_z)
                z_scores.append((col, z))

            abs_z = np.array([abs(z) for _, z in z_scores], dtype=float)

            drift = float(np.median(abs_z))
            velocity = drift - prev_drift
            pressure = float((0.75 * drift) + (0.25 * max(0.0, velocity)))

            if drift >= 2.8:
                deviation_persistence += 1
            else:
                deviation_persistence = 0

            state, regime = classify_state(drift, velocity, deviation_persistence)

            top = sorted(z_scores, key=lambda x: abs(x[1]), reverse=True)[:5]
            drivers = "; ".join([f"{name}:{z:.2f}z" for name, z in top])

            prev_drift = drift

        rows.append(
            {
                "asset_id": args.asset_id,
                "sample_index": i,
                "state": state,
                "regime": regime,
                "structural_drift_score": round(drift, 6),
                "drift_velocity": round(velocity, 6),
                "trajectory_pressure": round(pressure, 6),
                "deviation_persistence": deviation_persistence,
                "drift_drivers": drivers,
            }
        )

    results = pd.DataFrame(rows)

    events = []
    prior_state = None
    prior_regime = None

    for _, r in results.iterrows():
        state = r["state"]
        regime = r["regime"]

        if (
            regime == "PRE_INSTABILITY_TENSION"
            and prior_regime != "PRE_INSTABILITY_TENSION"
        ):
            events.append(
                {
                    "event_type": "PRE_INSTABILITY",
                    "sample_index": int(r["sample_index"]),
                    "state": state,
                    "regime": regime,
                    "drift_score": float(r["structural_drift_score"]),
                    "reason": event_reason("PRE_INSTABILITY", state, regime),
                }
            )

        if state in ["WATCH", "ALERT"] and prior_state not in ["WATCH", "ALERT"]:
            events.append(
                {
                    "event_type": "INITIAL_INSTABILITY",
                    "sample_index": int(r["sample_index"]),
                    "state": state,
                    "regime": regime,
                    "drift_score": float(r["structural_drift_score"]),
                    "reason": event_reason("INITIAL_INSTABILITY", state, regime),
                }
            )

        if state == "ALERT" and prior_state != "ALERT":
            events.append(
                {
                    "event_type": "ESCALATION",
                    "sample_index": int(r["sample_index"]),
                    "state": state,
                    "regime": regime,
                    "drift_score": float(r["structural_drift_score"]),
                    "reason": event_reason("ESCALATION", state, regime),
                }
            )

        prior_state = state
        prior_regime = regime

    state_counts = results["state"].value_counts().to_dict()
    watch_or_worse = results["state"].isin(["WATCH", "ALERT"]).mean() * 100

    summary = {
        "input": str(input_path),
        "asset_id": args.asset_id,
        "total_samples": int(len(results)),
        "numeric_signal_count": int(len(numeric.columns)),
        "numeric_signal_columns": list(numeric.columns),
        "baseline_mode": "adaptive_rolling_robust",
        "z_score_clamp": Z_CLAMP,
        "baseline_window": args.baseline_window,
        "min_baseline": args.min_baseline,
        "state_counts": state_counts,
        "percent_time_watch_or_worse": round(float(watch_or_worse), 2),
        "event_counts": {
            "total_events": len(events),
            "pre_instability": sum(1 for e in events if e["event_type"] == "PRE_INSTABILITY"),
            "initial_instability": sum(1 for e in events if e["event_type"] == "INITIAL_INSTABILITY"),
            "escalation": sum(1 for e in events if e["event_type"] == "ESCALATION"),
        },
        "events": events,
    }

    results.to_csv(out_dir / "sample_results.csv", index=False)

    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\nNERAIUM GENERIC TIMESERIES RUN")
    print("==============================")
    print(f"Input: {input_path}")
    print(f"Asset: {args.asset_id}")
    print(f"Samples: {summary['total_samples']}")
    print(f"Numeric signals: {summary['numeric_signal_count']}")
    print(f"Baseline mode: {summary['baseline_mode']}")
    print(f"Z clamp: {summary['z_score_clamp']}")
    print(f"Watch or worse: {summary['percent_time_watch_or_worse']}%")
    print(f"Events: {summary['event_counts']}")
    print(f"\nSaved: {out_dir / 'sample_results.csv'}")
    print(f"Saved: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
