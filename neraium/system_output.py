from neraium.engineer import build_engineer_output
from neraium.operator import build_operator_output


def build_system_output(engine_output: dict) -> dict:
    return {
        "operator": build_operator_output(engine_output),
        "engineer": build_engineer_output(engine_output),
        "raw_engine": engine_output,
    }
