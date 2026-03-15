import json
import re
import unittest

from fastapi.testclient import TestClient

from app.agents import nodes
from app.api import endpoints
from app.main import app


SCENARIO_PULSES = [
    {
        "t_predicted": 80.0,
        "t_actual": 81.4,
        "status": "RUNNING",
        "extra_metrics": {"current": 18.8, "vibration": 0.64, "pressure": 1.18},
    },
    {
        "t_predicted": 80.0,
        "t_actual": 82.6,
        "status": "RUNNING",
        "extra_metrics": {"current": 19.1, "vibration": 0.71, "pressure": 1.15},
    },
    {
        "t_predicted": 80.0,
        "t_actual": 84.2,
        "status": "RUNNING",
        "extra_metrics": {"current": 19.9, "vibration": 0.78, "pressure": 1.11},
    },
    {
        "t_predicted": 80.0,
        "t_actual": 88.4,
        "status": "RUNNING",
        "extra_metrics": {"current": 20.8, "vibration": 0.96, "pressure": 1.03},
    },
    {
        "t_predicted": 80.0,
        "t_actual": 95.6,
        "status": "RUNNING",
        "extra_metrics": {"current": 23.6, "vibration": 1.46, "pressure": 0.89},
    },
]


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def invoke(self, messages):
        system_prompt = messages[0].content
        human_input = messages[1].content

        if "实时监控 Agent" in system_prompt:
            matched = re.search(r"实际=(\d+(?:\.\d+)?), 预测=(\d+(?:\.\d+)?)", human_input)
            actual = float(matched.group(1)) if matched else 0.0
            predicted = float(matched.group(2)) if matched else 1.0
            tdi = abs(actual - predicted) / (predicted + 1e-6)
            if tdi > 0.15:
                return FakeResponse("温差显著扩大，异常已经形成，建议深度专家继续审查。")
            if tdi > 0.08:
                return FakeResponse("温差持续抬升但尚未越线，建议继续跟踪。")
            return FakeResponse("温差波动可控，设备继续保持常规监测。")

        if "深度故障审查专家" in system_prompt:
            if "是否已提供全部可用记录: 是" in human_input:
                return FakeResponse(
                    json.dumps(
                        {
                            "summary": "当前已经收到全部可用记录，证据链足够完整。",
                            "decision": "enough",
                            "range_start": None,
                            "range_end": None,
                            "reason": "无需继续取数。",
                        },
                        ensure_ascii=False,
                    )
                )

            if "#9" not in human_input:
                return FakeResponse(
                    json.dumps(
                        {
                            "summary": "还需要回看异常发生前的升温过程。",
                            "decision": "request_more",
                            "range_start": 9,
                            "range_end": 12,
                            "reason": "需要确认异常前是否已有持续抬升。",
                        },
                        ensure_ascii=False,
                    )
                )

            return FakeResponse(
                json.dumps(
                    {
                        "summary": "现有记录已经足够形成完整判断。",
                        "decision": "enough",
                        "range_start": None,
                        "range_end": None,
                        "reason": "异常前后演化已完整可见。",
                    },
                    ensure_ascii=False,
                )
            )

        if "深度故障诊断专家" in system_prompt:
            return FakeResponse(
                json.dumps(
                    {
                        "diagnosis": "综合序号#9至#15的温差演化，设备在异常发生前已有持续升温趋势，异常点集中放大。较大概率为轴承润滑不足或相关摩擦负荷上升引起的热失衡。",
                        "actions": [
                            "检查润滑系统与轴承状态。",
                            "复核冷却回路和现场散热条件。",
                            "处理完成后继续观察温差是否回落。",
                        ],
                        "report_summary": "异常前后记录完整，已可形成明确诊断。",
                    },
                    ensure_ascii=False,
                )
            )

        raise AssertionError(f"Unexpected prompt: {system_prompt}")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.original_llm = nodes.llm
        nodes.llm = FakeLLM()
        endpoints.sessions.clear()

    def tearDown(self):
        nodes.llm = self.original_llm
        endpoints.sessions.clear()

    def _start_task(self, task_id="task-demo"):
        response = self.client.post(
            "/v1/analysis/start",
            json={
                "task_id": task_id,
                "device_id": "PUMP-001",
                "category": "离心泵",
                "metadata": {"location": "产线A"},
            },
        )
        self.assertEqual(response.status_code, 200)
        return task_id

    def test_start_contains_seed_database(self):
        task_id = self._start_task("task-seed")

        report_response = self.client.get(f"/v1/analysis/report/{task_id}")
        self.assertEqual(report_response.status_code, 200)
        payload = report_response.json()

        self.assertEqual(payload["summary"]["latest_sequence"], 10)
        self.assertEqual(len(payload["history"]["data_records"]), 10)
        self.assertEqual(payload["history"]["data_records"][0]["sequence"], 1)
        self.assertEqual(payload["history"]["data_records"][-1]["sequence"], 10)
        self.assertFalse(payload["summary"]["is_anomaly"])

    def test_anomaly_flow_requests_range_and_finishes_on_record_15(self):
        task_id = self._start_task("task-anomaly")

        for index, pulse in enumerate(SCENARIO_PULSES[:4], start=11):
            response = self.client.post("/v1/analysis/pulse", json={"task_id": task_id, **pulse})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["feedback"]["latest_sequence"], index)
            self.assertFalse(payload["feedback"]["is_anomaly"])
            self.assertEqual(payload["feedback"]["expert_status"], "sleeping")

        anomaly_response = self.client.post(
            "/v1/analysis/pulse",
            json={"task_id": task_id, **SCENARIO_PULSES[-1]},
        )
        self.assertEqual(anomaly_response.status_code, 200)
        payload = anomaly_response.json()

        self.assertTrue(payload["feedback"]["is_anomaly"])
        self.assertEqual(payload["feedback"]["latest_sequence"], 15)
        self.assertEqual(payload["feedback"]["expert_status"], "done")
        self.assertTrue(payload["feedback"]["conversation_closed"])
        self.assertEqual(payload["feedback"]["expert_turn_count"], 2)

        titles = [item["title"] for item in payload["feedback"]["conversation_history"]]
        texts = [item["text"] for item in payload["feedback"]["conversation_history"]]
        self.assertIn("首轮异常数据包 #13-#15", titles)
        self.assertIn("深度专家取数请求 第1轮", titles)
        self.assertIn("补送数据包 #9-#12", titles)
        self.assertIn("系统提示", titles)
        self.assertIn("深度专家最终诊断", titles)
        self.assertTrue(any("序号#9-#12" in text for text in texts))

        report_payload = self.client.get(f"/v1/analysis/report/{task_id}").json()
        self.assertEqual(len(report_payload["history"]["data_records"]), 15)
        self.assertEqual(report_payload["summary"]["latest_sequence"], 15)
        self.assertIn("轴承润滑不足", report_payload["diagnosis"]["conclusion"])
        self.assertEqual(report_payload["diagnosis"]["requests"], ["请补充序号#9-#12的历史记录。"])

    def test_generate_report_then_restart(self):
        task_id = self._start_task("task-report")
        for pulse in SCENARIO_PULSES:
            self.client.post("/v1/analysis/pulse", json={"task_id": task_id, **pulse})

        original_generator = endpoints.generate_report_html
        endpoints.generate_report_html = lambda **_: "<section><h1>测试报告</h1></section>"
        try:
            response = self.client.post(
                "/v1/analysis/report/generate",
                json={
                    "task_id": task_id,
                    "issue_summary": "第15条记录温差明显放大",
                    "history_data": {},
                    "chat_messages": [],
                },
            )
        finally:
            endpoints.generate_report_html = original_generator

        self.assertEqual(response.status_code, 200)
        self.assertIn("测试报告", response.json()["report_html"])

        report_payload = self.client.get(f"/v1/analysis/report/{task_id}").json()
        self.assertTrue(report_payload["summary"]["monitoring_locked"])
        self.assertTrue(report_payload["summary"]["report_ready"])

        restart_response = self.client.post("/v1/analysis/restart", json={"task_id": task_id})
        self.assertEqual(restart_response.status_code, 200)

        restarted_report = self.client.get(f"/v1/analysis/report/{task_id}").json()
        self.assertEqual(restarted_report["summary"]["latest_sequence"], 10)
        self.assertEqual(len(restarted_report["history"]["data_records"]), 10)
        self.assertFalse(restarted_report["summary"]["monitoring_locked"])
        self.assertFalse(restarted_report["summary"]["report_ready"])
        self.assertEqual(restarted_report["conversation_history"], [])


if __name__ == "__main__":
    unittest.main()
