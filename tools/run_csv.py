import argparse
import json

import pandas as pd

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.engineer import build_engineer_output
from neraium.operator import build_operator_output


def _sensor_context(columns):
    return {
        f"sensor_{i}": {"name": col, "subsystem": "unknown", "component": col}
        for i, col in enumerate(columns)
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run Neraium structural detection on a CSV file."
    )
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    parser.add_argument("--max-rows", type=int, default=None, dest="max_rows")
    parser.add_argument(
        "--show-transient",
        action="store_true",
        dest="show_transient",
        help="Print row index for each transient cycle",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    df = df[numeric_cols].dropna()

    if args.max_rows is not None:
        df = df.iloc[: args.max_rows]

    context = _sensor_context(numeric_cols)
    engine = NeraiumEngine(NeraiumConfig())

    for row_idx, row in df.iterrows():
        packet = row.to_numpy(dtype=float)
        engine_output = engine.update(packet)
        status = engine_output.get("status")

        if args.show_transient and status == "TRANSIENT":
            print(f"row: {row_idx} [TRANSIENT]")
            continue

        if status not in ("CONFIRMED_CHANGE", "CONFIRMED_CHANGE_HELD"):
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
