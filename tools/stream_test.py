import random
import time
import requests

url = "http://127.0.0.1:8000/update"
random.seed(42)

for i in range(160):
    if i < 70:
        spindle_vibration = 0.2 + random.uniform(-0.02, 0.02)
        spindle_motor_current = 5.0 + random.uniform(-0.1, 0.1)
    else:
        shared = random.uniform(-1.0, 1.0)
        drift = 0.02 * (i - 70)
        spindle_vibration = 0.2 + shared + drift
        spindle_motor_current = 5.0 + shared + drift + random.uniform(-0.02, 0.02)

    payload = {
        "asset_id": "cnc_01",
        "signals": {
            "spindle_vibration": spindle_vibration,
            "spindle_motor_current": spindle_motor_current,
            "coolant_flow_rate": 10.0 + random.uniform(-0.5, 0.5),
            "axis_servo_load": 0.4 + random.uniform(-0.05, 0.05),
            "cutting_zone_temperature": 70.0 + random.uniform(-1.0, 1.0)
        }
    }

    response = requests.post(url, json=payload).json()
    operator = response["operator"]

    status = operator["status"]
    summary = operator.get("what_is_happening", {}).get("summary")
    signals = operator.get("where", {}).get("top_signals", [])
    trajectory = operator.get("trajectory", {})
    action = operator.get("recommended_next_step")

    if (
        status in ("CONFIRMED_CHANGE", "CONFIRMED_CHANGE_HELD")
        and trajectory.get("direction") != "ambiguous"
    ):
        print(f"cycle: {i}")
        print(f"status: {status}")
        print(f"summary: {summary}")
        print(f"signals: {', '.join(signals)}")
        print(f"direction: {trajectory.get('direction')}")
        print(f"urgency: {trajectory.get('urgency')}")
        print(f"action: {action}")
        break

    time.sleep(0.1)
