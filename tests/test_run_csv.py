import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("tools/run_csv.py")
SAMPLE_CSV = Path("examples/sample_cnc.csv")

# Ensure the project root is on PYTHONPATH so subprocess can import neraium
_PROJECT_ROOT = str(Path(__file__).parent.parent)
_SUBPROCESS_ENV = {**os.environ, "PYTHONPATH": _PROJECT_ROOT}

CONFIRMED_MESSAGES = ("ALERT", "ALERT_HELD")
NOT_FOUND_MESSAGE = "No confirmed structural change found."


def _run(*extra_args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--csv", str(SAMPLE_CSV), *extra_args],
        capture_output=True,
        text=True,
        env=_SUBPROCESS_ENV,
    )


def test_script_exists():
    assert SCRIPT.exists(), f"{SCRIPT} not found"


def test_sample_csv_exists():
    assert SAMPLE_CSV.exists(), f"{SAMPLE_CSV} not found"


def test_run_on_sample_csv_exits_successfully():
    result = _run()
    assert result.returncode == 0, f"Script failed:\n{result.stderr}"


def test_output_contains_confirmed_or_not_found_message():
    output = _run().stdout
    found = any(msg in output for msg in CONFIRMED_MESSAGES) or NOT_FOUND_MESSAGE in output
    assert found, f"Expected confirmed or not-found message in output:\n{output}"


def test_confirmed_output_names_spindle_pair():
    output = _run().stdout
    if NOT_FOUND_MESSAGE in output:
        return
    assert "Spindle Vibration" in output
    assert "Spindle Motor Current" in output


def test_known_columns_resolve_subsystem_and_component():
    output = _run().stdout
    if NOT_FOUND_MESSAGE in output:
        return
    # Generic context: subsystem and component are the raw column names
    assert "spindle_vibration" in output
    assert "spindle_motor_current" in output
    assert "unknown" not in output


def test_max_rows_limits_processing():
    result = _run("--max-rows", "10")
    assert result.returncode == 0
    assert NOT_FOUND_MESSAGE in result.stdout


def test_raw_engine_not_printed_by_default():
    output = _run().stdout
    assert "raw_engine" not in output
