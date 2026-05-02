"""
Sensor context helpers.

The engine itself is fully dataset-agnostic. Context (human-readable signal
names, subsystems, component labels) is optional and provided by callers.

build_context_from_columns() converts raw CSV column names into a sensor
context dict that operator.py and engineer.py can consume.
"""


def build_context_from_columns(columns: list[str]) -> dict[str, dict]:
    """
    Auto-generate a sensor context dict from a list of column names.

    Each sensor_N key maps to a dict with:
        name      — the original column name (used as display name)
        subsystem — defaults to the column name (caller may override)
        component — defaults to the column name (caller may override)

    This produces fully generic context with no dataset-specific assumptions.
    """
    return {
        col: {
            "name": col.replace("_", " ").title(),
            "subsystem": col,
            "component": col,
        }
        for col in columns
    }
