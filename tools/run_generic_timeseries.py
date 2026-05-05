import argparse
import json
import os
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from backend.services.sii_core.engine import SIIEngine
from backend.services.sii_core.schema import SIIPacket


def infer_timestamp_column(df: pd.DataFrame) -> str | None:
    candidates = ["timestamp", "time", "datetime", "date", "created_at"]

    lower_map = {c.lower(): c for c in df.columns}

    for c in candidates:
        if c in lower_map:
            return lower_map[c]

    return None


def infer_numeric_columns(df: pd.DataFrame, exclude: set[str]) -> list[str]:
    numeric_cols = []

    for col in df.columns:
        if col in exclude:
            continue

        converted = pd.to_numeric(df[col], errors="coerce")
        valid_ratio = converted.notna().mean()

        if valid_ratio >= 0.70:
            numeric_cols.append(col)

    return numeric_cols


def packet_from_row(
    row: pd.Series,
    asset_id: str,
    timestamp_col: str | None,
    numeric_cols: list[str],
    row_index: int,
    source_file: str,
) -> SIIPacket:
    if timestamp_col:
        timestamp = str(row.get(timestamp_col))
    else:
        timestamp = str(row_index)

    signals: Dict[str, float] = {}

    for col in numeric_cols:
        try:
            value = float(row.get(col))
            signals[col] = value
        except Exception:
            continue

    return SIIPacket(
        asset_id=asset_id,
        timestamp=timestamp,
        signals=signals,
        metadata={
            "source_file": source_file,
            "row_index": row_index,
        },
    )


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)

    state_counts = {}

    for r in results:
        state = r["state"]
        state_counts[state] = state_counts.get(state, 0) + 1

    event_counts = {}

    for r in results:
        for event in r.get("events", []):
            event_type = event["event_type"]
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

    unstable_count = sum(
        1
        for r in results
        if r["state"] in ["WATCH", "TRANSITION", "UNSTABLE", "LOCK_IN"]
    )

    first_events = {}

    for r in results:
        for event in r.get("events", []):
            event_type = event["event_type"]
            if event_type not in first_events:
                first_events[event_type] = event

    return {
        "total_samples": total,
        "state_counts": state_counts,
        "event_counts": event_counts,
        "percent_time_watch_or_worse": round(100 * unstable_count / total, 2) if total else 0.0,
        "first_events": first_events,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="CSV file path")
    parser.add_argument("--output-dir", default="results/generic_timeseries")
    parser.add_argument("--asset-id", default="asset_1")
    parser.add_argument("--baseline-window", type=int, default=30)
    parser.add_argument("--min-baseline", type=int, default=20)
    parser.add_argument("--timestamp-col", default=None)
    parser.add_argument("--drop-cols", default="", help="Comma-separated columns to exclude")

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    df = pd.read_csv(input_path)

    timestamp_col = args.timestamp_col or infer_timestamp_column(df)

    drop_cols = set([c.strip() for c in args.drop_cols.split(",") if c.strip()])

    exclude = set(drop_cols)
    if timestamp_col:
        exclude.add(timestamp_col)

    numeric_cols = infer_numeric_columns(df, exclude=exclude)

    if not numeric_cols:
        raise RuntimeError("No numeric columns found for SII signals.")

    engine = SIIEngine(
        baseline_window=args.baseline_window,
        min_baseline=args.min_baseline,
    )

    results = []

    for i, row in df.iterrows():
        packet = packet_from_row(
            row=row,
            asset_id=args.asset_id,
            timestamp_col=timestamp_col,
            numeric_cols=numeric_cols,
            row_index=i,
            source_file=str(input_path),
        )

        result = engine.update(packet)
        results.append(result.to_dict())

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results_df = pd.json_normalize(results)
    results_df.to_csv(out_dir / "sample_results.csv", index=False)

    summary = summarize(results)

    summary["input"] = str(input_path)
    summary["asset_id"] = args.asset_id
    summary["numeric_signal_columns"] = numeric_cols
    summary["timestamp_column"] = timestamp_col
    summary["baseline_window"] = args.baseline_window
    summary["min_baseline"] = args.min_baseline

    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\nNERAIUM GENERIC TIMESERIES RUN")
    print("==============================")
    print(f"Input: {input_path}")
    print(f"Asset: {args.asset_id}")
    print(f"Samples: {summary['total_samples']}")
    print(f"Numeric signals: {len(numeric_cols)}")
    print(f"Timestamp column: {timestamp_col}")
    print(f"Watch or worse: {summary['percent_time_watch_or_worse']}%")
    print(f"Events: {summary['event_counts']}")
    print(f"\nSaved: {out_dir / 'sample_results.csv'}")
    print(f"Saved: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
