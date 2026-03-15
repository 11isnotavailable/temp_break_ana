import time
import uuid

import requests

BASE_URL = "http://127.0.0.1:8000/v1/analysis"
TASK_ID = str(uuid.uuid4())


def run_test():
    print(f"启动任务，task_id={TASK_ID}")
    start_payload = {
        "task_id": TASK_ID,
        "device_id": "PUMP-001",
        "category": "离心泵",
        "metadata": {"location": "三号车间", "rated_temp": 80.0},
    }
    start_response = requests.post(f"{BASE_URL}/start", json=start_payload, timeout=30)
    print(start_response.json())

    simulation_data = [
        {"t_pre": 80.0, "t_act": 81.0},
        {"t_pre": 80.0, "t_act": 80.5},
        {"t_pre": 80.0, "t_act": 95.0},
        {"t_pre": 80.0, "t_act": 98.5},
        {"t_pre": 80.0, "t_act": 80.2},
        {"t_pre": 80.0, "t_act": 80.1},
        {"t_pre": 80.0, "t_act": 80.0},
    ]

    for index, data in enumerate(simulation_data, start=1):
        pulse_payload = {
            "task_id": TASK_ID,
            "t_predicted": data["t_pre"],
            "t_actual": data["t_act"],
            "status": "RUNNING",
        }

        start_time = time.time()
        response = requests.post(f"{BASE_URL}/pulse", json=pulse_payload, timeout=60)
        elapsed = time.time() - start_time

        print(f"\n第 {index} 轮 pulse，用时 {elapsed:.2f}s")
        print(response.json())

        if response.ok and response.json()["decision"] == "TERMINATE":
            print("任务已稳定收敛，停止推送")
            break

        time.sleep(2)

    report_response = requests.get(f"{BASE_URL}/report/{TASK_ID}", timeout=30)
    print("\n完整报告：")
    print(report_response.json())


if __name__ == "__main__":
    run_test()
