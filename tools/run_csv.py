"""
Generic CSV runner for the Neraium structural detection engine.

Works with any CSV file — no dataset-specific column mappings.
Column names from the CSV are used as sensor display names.

Usage:
    python tools/run_csv.py --csv <file> [--max-rows N] [--show-watch]
"""

import argparse
import json

import pandas as pd

from neraium.config import NeraiumConfig
from neraium.context import build_context_from_columns
from neraium.engine import NeraiumEngine
from neraium.engineer import build_engineer_output
from neraium.operator import build_operator_output


def main():
    parser = argparse.ArgumentParser(
        description="Run Neraium structural detection on any CSV file."
    )
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    parser.add_argument("--max-rows", type=int, default=None, dest="max_rows")
    parser.add_argument(
        "--show-transient",
        "--show-watch",
        action="store_true",
        dest="show_watch",
        help="Print row index for each WATCH cycle",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    df = df[numeric_cols].dropna()

    if args.max_rows is not None:
        df = df.iloc[: args.max_rows]

    # Build generic sensor context from column names — no hardcoded mappings
    context = build_context_from_columns(numeric_cols)
    engine = NeraiumEngine(NeraiumConfig(), signal_names=numeric_cols)

    for row_idx, row in df.iterrows():
        packet = row.to_numpy(dtype=float)
        engine_output = engine.update(packet)
        status = engine_output.get("status")

        if args.show_watch and status == "WATCH":
            print(f"row: {row_idx} [WATCH]")
            continue

        if status not in ("ALERT", "ALERT_HELD"):
            continue

        operator = build_operator_output(engine_output, sensor_context=context)
        engineer = build_engineer_output(engine_output)

        print(f"row: {row_idx}")
        print("operator:")
        print(json.dumps(operator, indent=2))
        print("engineer:")
        print(json.dumps(engineer, indent=2))
        return

    print("No confirmed structural change found.")


if __name__ == "__main__":
    main()
