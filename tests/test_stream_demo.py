from pathlib import Path


def test_stream_demo_does_not_print_internal_pattern_labels():
    stream_demo = Path("tools/stream_test.py").read_text()

    assert "Pattern:" not in stream_demo
    assert "RELATIONSHIP_FORMATION" not in stream_demo
    assert "STRUCTURAL_CHANGE_UNCERTAIN" not in stream_demo
