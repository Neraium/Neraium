"""
Generic Neraium engine runner.

Loads any CSV, runs the engine step-by-step, and prints the first ALERT cycle
if detected.  No dataset-specific parameters or column mappings.

Usage:
    python tools/run_engine.py --csv <file>
    python tools/run_engine.py --csv data.csv --max-rows 500
    python tools/run_engine.py --csv data.csv --baseline 100 --verbose
"""

import argparse
import json
import sys

import pandas as pd

from neraium.config import NeraiumConfig
from neraium.context import build_context_from_columns
from neraium.engine import NeraiumEngine
from neraium.engineer import build_engineer_output
from neraium.operator import build_operator_output


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Neraium structural-change engine on any multivariate "
            "time-series CSV.  Prints the first ALERT cycle, if found."
        )
    )
    parser.add_argument("--csv", required=True, help="Path to CSV file (columns = sensors, rows = timesteps)")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        dest="max_rows",
        help="Limit processing to the first N rows",
    )
    parser.add_argument(
        "--baseline",
        type=int,
        default=None,
        dest="baseline_window",
        help="Override the baseline window size (default: 50)",
    )
    parser.add_argument(
        "--watch-multiplier",
        type=float,
        default=None,
        dest="watch_multiplier",
        help="Override WATCH threshold multiplier (default: 3.0)",
    )
    parser.add_argument(
        "--alert-multiplier",
        type=float,
        default=None,
        dest="alert_multiplier",
        help="Override ALERT threshold multiplier (default: 5.0)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print state and drift score for every row",
    )
    args = parser.parse_args()

    # ── Load CSV ──────────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(args.csv)
    except Exception as exc:
        print(f"ERROR: cannot read {args.csv!r}: {exc}", file=sys.stderr)
        return 1

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        print("ERROR: no numeric columns found in CSV.", file=sys.stderr)
        return 1

    df = df[numeric_cols].dropna()
    if args.max_rows is not None:
        df = df.iloc[: args.max_rows]

    print(
        f"Loaded {len(df)} rows × {len(numeric_cols)} signals: "
        f"{', '.join(numeric_cols)}"
    )

    # ── Build config (override only what was specified) ───────────────────────
    cfg_kwargs: dict = {}
    if args.baseline_window is not None:
        cfg_kwargs["baseline_window"] = args.baseline_window
    if args.watch_multiplier is not None:
        cfg_kwargs["watch_mad_multiplier"] = args.watch_multiplier
    if args.alert_multiplier is not None:
        cfg_kwargs["alert_mad_multiplier"] = args.alert_multiplier

    config = NeraiumConfig(**cfg_kwargs)
    engine = NeraiumEngine(config)

    # Generic context: column names become sensor display names
    context = build_context_from_columns(numeric_cols)

    # ── Run engine step-by-step ───────────────────────────────────────────────
    first_alert_row: int | None = None
    first_alert_output: dict | None = None

    for row_idx, row in df.iterrows():
        packet = row.to_numpy(dtype=float)
        out = engine.update(packet)
        state = out.get("state", out.get("status", ""))

        if args.verbose:
            drift = out.get("structural_drift_score", 0.0)
            ev = out.get("evidence_count", 0)
            watch_t = out.get("watch_threshold", 0.0)
            alert_t = out.get("alert_threshold", 0.0)
            print(
                f"row={row_idx:>5}  state={state:<12}  "
                f"drift={drift:>7.3f}  evidence={ev}  "
                f"watch_thr={watch_t:.3f}  alert_thr={alert_t:.3f}"
            )

        if state == "ALERT" and first_alert_row is None:
            first_alert_row = int(row_idx)
            first_alert_output = out
            if not args.verbose:
                # In non-verbose mode stop at first ALERT
                break

    # ── Print result ──────────────────────────────────────────────────────────
    if first_alert_row is None:
        print("\nNo confirmed structural change found.")
        return 0

    print(f"\n{'─'*60}")
    print(f"FIRST ALERT at row {first_alert_row}")
    print(f"{'─'*60}")

    operator_out = build_operator_output(first_alert_output, sensor_context=context)
    engineer_out = build_engineer_output(first_alert_output)

    print("\nOperator summary:")
    print(json.dumps(operator_out, indent=2))
    print("\nEngineer evidence:")
    print(json.dumps(engineer_out, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
