import subprocess
import sys
from pathlib import Path

SCRIPT = Path("tools/run_csv.py")
SAMPLE_CSV = Path("examples/sample_cnc.csv")

CONFIRMED_MESSAGES = ("CONFIRMED_CHANGE", "CONFIRMED_CHANGE_HELD")
NOT_FOUND_MESSAGE = "No confirmed structural change found."


def test_script_exists():
    assert SCRIPT.exists(), f"{SCRIPT} not found"


def test_sample_csv_exists():
    assert SAMPLE_CSV.exists(), f"{SAMPLE_CSV} not found"


def test_run_on_sample_csv_exits_successfully():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--csv", str(SAMPLE_CSV)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Script failed:\n{result.stderr}"


def test_output_contains_confirmed_or_not_found_message():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--csv", str(SAMPLE_CSV)],
        capture_output=True,
        text=True,
    )
    output = result.stdout
    found = any(msg in output for msg in CONFIRMED_MESSAGES) or NOT_FOUND_MESSAGE in output
    assert found, f"Expected confirmed or not-found message in output:\n{output}"


def test_confirmed_output_names_spindle_pair():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--csv", str(SAMPLE_CSV)],
        capture_output=True,
        text=True,
    )
    output = result.stdout
    if NOT_FOUND_MESSAGE in output:
        return  # nothing to assert
    assert "Spindle Vibration" in output
    assert "Spindle Motor Current" in output


def test_known_columns_resolve_subsystem_and_component():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--csv", str(SAMPLE_CSV)],
        capture_output=True,
        text=True,
    )
    output = result.stdout
    if NOT_FOUND_MESSAGE in output:
        return  # nothing to assert
    assert "Spindle assembly" in output
    assert "Spindle drive" in output
    assert "spindle_assembly" in output
    assert "spindle_motor" in output
    assert "unknown" not in output


def test_max_rows_limits_processing():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--csv", str(SAMPLE_CSV), "--max-rows", "10"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert NOT_FOUND_MESSAGE in result.stdout


def test_raw_engine_not_printed_by_default():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--csv", str(SAMPLE_CSV)],
        capture_output=True,
        text=True,
    )
    assert "raw_engine" not in result.stdout
