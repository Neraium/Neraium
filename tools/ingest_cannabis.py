"""
Cannabis grow-room CSV ingestion tool.

Accepts CSV exports from Aroya, TrolMaster, Growlink, Priva, Argus, Metrc,
Canix, GrowerIQ, Trym, or any generic timestamped sensor log.

Usage
-----
    python tools/ingest_cannabis.py --csv <file> [options]

Options
-------
    --csv         Path to CSV file (required)
    --max-rows N  Process only the first N data rows
    --show-watch  Also print rows where status is WATCH
    --all-alerts  Keep running after the first ALERT (print all)
    --json        Print full JSON output on each ALERT (default: summary only)
"""

import argparse
import json

import pandas as pd

from neraium.adapters.cannabis import (
    build_cannabis_context,
    detect_platform,
    normalise_dataframe,
)
from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.engineer import build_engineer_output
from neraium.operator import build_operator_output


def main():
    parser = argparse.ArgumentParser(
        description="Run Neraium structural detection on cannabis grow-room data."
    )
    parser.add_argument("--csv",        required=True, help="Path to CSV file")
    parser.add_argument("--max-rows",   type=int, default=None, dest="max_rows")
    parser.add_argument("--show-watch", action="store_true", dest="show_watch")
    parser.add_argument("--all-alerts", action="store_true", dest="all_alerts",
                        help="Continue after first alert (print all ALERT rows)")
    parser.add_argument("--json",       action="store_true",
                        help="Print full JSON output on each alert")
    args = parser.parse_args()

    raw_df = pd.read_csv(args.csv)
    platform = detect_platform(raw_df)
    print(f"Platform detected: {platform}")

    df = normalise_dataframe(raw_df)
    if df.empty:
        print("No numeric signals found after normalisation. Check column names.")
        return

    if args.max_rows:
        df = df.iloc[: args.max_rows]

    signal_names = df.columns.tolist()
    context      = build_cannabis_context(df)
    engine       = NeraiumEngine(NeraiumConfig(), signal_names=signal_names)

    print(f"Signals ({len(signal_names)}): {', '.join(signal_names)}")
    print(f"Rows to process: {len(df)}\n")

    alert_count = 0

    for row_idx, (_, row) in enumerate(df.iterrows()):
        packet      = row.to_numpy(dtype=float)
        engine_out  = engine.update(packet)
        status      = engine_out.get("status")

        if args.show_watch and status == "WATCH":
            print(f"  row {row_idx:>4}  [WATCH]  drift={engine_out.get('drift_score', 0):.3f}")
            continue

        if status not in ("ALERT", "ALERT_HELD"):
            continue

        alert_count += 1
        operator = build_operator_output(engine_out, sensor_context=context)
        engineer = build_engineer_output(engine_out)

        print(f"{'='*60}")
        print(f"ALERT at row {row_idx}  (status={status})")
        print(f"  drift_score : {engine_out.get('drift_score', 0):.4f}")
        print(f"  pattern     : {engineer.get('pattern', {}).get('type', 'n/a')}")
        print(f"  direction   : {operator.get('trajectory', {}).get('direction', 'n/a')}")
        print(f"  urgency     : {operator.get('trajectory', {}).get('urgency', 'n/a')}")
        print(f"  summary     : {operator.get('plain_english', {}).get('what_this_means', '')}")

        top_sigs = operator.get("where", {}).get("top_signals", [])
        if top_sigs:
            print("  top signals :")
            for s in top_sigs[:3]:
                # operator already returns human-readable signal names
                print(f"    • {s}")

        pair = operator.get("where", {}).get("top_relationship_pair", [])
        if len(pair) == 2:
            print(f"  key relationship: {pair[0]}  ↔  {pair[1]}")

        if args.json:
            print("\noperator output:")
            print(json.dumps(operator, indent=2))
            print("\nengineer output:")
            print(json.dumps(engineer, indent=2))

        if not args.all_alerts:
            return

    if alert_count == 0:
        print("No confirmed structural change detected.")
    else:
        print(f"\n{alert_count} alert(s) found.")


if __name__ == "__main__":
    main()
