import requests
import time
import uuid

# FastAPI 服务地址
BASE_URL = "http://127.0.0.1:8000/v1/analysis"
TASK_ID = str(uuid.uuid4())

def run_test():
    # --- 1. 启动任务 ---
    print(f"发送启动指令，Task ID: {TASK_ID}")
    start_payload = {
        "task_id": TASK_ID,
        "device_id": "PUMP-001",
        "category": "离心泵",
        "metadata": {"location": "三号车间", "rated_temp": 80.0}
    }
    requests.post(f"{BASE_URL}/start", json=start_payload)

    # --- 2. 模拟脉冲数据 (每周期模拟 30s) ---
    # 模拟数据序列：前3次正常，中间4次异常（触发诊断），后3次恢复（触发终止）
    simulation_data = [
        {"t_pre": 80.0, "t_act": 81.0}, # 正常
        {"t_pre": 80.0, "t_act": 80.5}, # 正常
        {"t_pre": 80.0, "t_act": 81.2}, # 正常
        {"t_pre": 80.0, "t_act": 95.0}, # 异常启动！Agent 2 应该介入
        {"t_pre": 80.0, "t_act": 98.5}, # 异常持续
        {"t_pre": 80.0, "t_act": 92.0}, # 异常开始缓解
        {"t_pre": 80.0, "t_act": 82.0}, # 恢复中
        {"t_pre": 80.0, "t_act": 80.8}, # 稳定 1
        {"t_pre": 80.0, "t_act": 80.5}, # 稳定 2
        {"t_pre": 80.0, "t_act": 80.2}, # 稳定 3 -> 应该触发 TERMINATE
    ]

    for i, data in enumerate(simulation_data):
        print(f"\n--- 第 {i+1} 次脉冲数据推送 ---")
        pulse_payload = {
            "task_id": TASK_ID,
            "t_predicted": data["t_pre"],
            "t_actual": data["t_act"],
            "status": "RUNNING"
        }
        
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/pulse", json=pulse_payload)
        end_time = time.time()

        if response.status_code == 200:
            res_json = response.json()
            decision = res_json["decision"]
            feedback = res_json["feedback"]

            print(f"耗时: {end_time - start_time:.2f}s")
            print(f"决策: {decision}")
            print(f"TDI 指标: {feedback['tdi_value']:.2%}")
            print(f"监控报告摘要: {feedback['latest_report'][:50]}...")
            
            if feedback['diagnosis']:
                print(f"专家诊断结论: {feedback['diagnosis'][:100]}...")
            
            if feedback['requests']:
                print(f"专家追加要求: {feedback['requests']}")

            if decision == "TERMINATE":
                print("\n[SUCCESS] 检测到系统已稳定，主后端停止轮询。")
                break
        else:
            print(f"请求失败: {response.text}")
        
        # 实际场景是 30s，测试时我们等 2s
        time.sleep(2)

if __name__ == "__main__":
    run_test()