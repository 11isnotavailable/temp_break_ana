import unittest

from fastapi.testclient import TestClient

from app.api import endpoints
from app.main import app


class FakeGraph:
    async def ainvoke(self, state):
        current_tdi = abs(state["current_data"]["t_actual"] - state["current_data"]["t_predicted"]) / (
            state["current_data"]["t_predicted"] + 1e-6
        )
        is_anomaly = current_tdi > 0.15
        final_state = dict(state)
        final_state["tdi_history"] = list(state.get("tdi_history", [])) + [current_tdi]
        final_state["scout_reports"] = list(state.get("scout_reports", [])) + [
            "监控发现温差异常扩大" if is_anomaly else "监控正常"
        ]
        final_state["latest_report"] = final_state["scout_reports"][-1]
        final_state["is_anomaly"] = is_anomaly
        final_state["expert_status"] = "done" if is_anomaly else "sleeping"
        final_state["diagnostic_conclusion"] = "疑似润滑异常" if is_anomaly else ""
        final_state["actions"] = ["检查润滑系统"] if is_anomaly else []
        final_state["pending_requests"] = ["补充振动数据"] if is_anomaly else []
        final_state["expert_turn_count"] = 2 if is_anomaly else 0
        final_state["conversation_history"] = (
            [
                {
                    "id": "msg-1",
                    "speaker": "scout",
                    "title": "实时监控 Agent 异常摘要",
                    "text": "检测到温差快速扩大，建议专家继续判断。",
                    "type": "agent",
                },
                {
                    "id": "msg-2",
                    "speaker": "expert",
                    "title": "深度专家评估 第 2 轮",
                    "text": "优先怀疑润滑系统异常，需要补充振动数据。",
                    "type": "agent",
                },
            ]
            if is_anomaly
            else []
        )
        final_state["should_terminate"] = False
        final_state["next_node"] = "end"
        final_state["diagnosis_ready"] = is_anomaly
        final_state["conversation_closed"] = is_anomaly
        final_state["monitoring_locked"] = False
        final_state["report_ready"] = False
        return final_state


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.original_graph = endpoints.app_graph
        endpoints.app_graph = FakeGraph()
        endpoints.sessions.clear()

    def tearDown(self):
        endpoints.app_graph = self.original_graph
        endpoints.sessions.clear()

    def test_start_and_pulse_normal(self):
        start_response = self.client.post(
            "/v1/analysis/start",
            json={
                "task_id": "task-normal",
                "device_id": "PUMP-001",
                "category": "离心泵",
                "metadata": {"location": "产线A"},
            },
        )
        self.assertEqual(start_response.status_code, 200)

        pulse_response = self.client.post(
            "/v1/analysis/pulse",
            json={
                "task_id": "task-normal",
                "t_predicted": 80.0,
                "t_actual": 81.0,
                "status": "RUNNING",
            },
        )
        self.assertEqual(pulse_response.status_code, 200)
        payload = pulse_response.json()
        self.assertEqual(payload["decision"], "CONTINUE")
        self.assertFalse(payload["feedback"]["is_anomaly"])
        self.assertEqual(payload["feedback"]["expert_status"], "sleeping")
        self.assertFalse(payload["feedback"]["conversation_closed"])
        self.assertFalse(payload["feedback"]["monitoring_locked"])
        self.assertEqual(payload["feedback"]["conversation_history"], [])

    def test_report_after_anomaly(self):
        self.client.post(
            "/v1/analysis/start",
            json={
                "task_id": "task-anomaly",
                "device_id": "PUMP-002",
                "category": "离心泵",
                "metadata": {"location": "产线B"},
            },
        )

        self.client.post(
            "/v1/analysis/pulse",
            json={
                "task_id": "task-anomaly",
                "t_predicted": 80.0,
                "t_actual": 96.0,
                "status": "RUNNING",
            },
        )

        report_response = self.client.get("/v1/analysis/report/task-anomaly")
        self.assertEqual(report_response.status_code, 200)
        payload = report_response.json()
        self.assertTrue(payload["summary"]["is_anomaly"])
        self.assertEqual(payload["summary"]["expert_status"], "done")
        self.assertTrue(payload["summary"]["conversation_closed"])
        self.assertFalse(payload["summary"]["monitoring_locked"])
        self.assertFalse(payload["summary"]["report_ready"])
        self.assertEqual(payload["summary"]["expert_turn_count"], 2)
        self.assertEqual(payload["diagnosis"]["conclusion"], "疑似润滑异常")
        self.assertEqual(payload["diagnosis"]["actions"], ["检查润滑系统"])
        self.assertEqual(payload["diagnosis"]["requests"], ["补充振动数据"])
        self.assertEqual(len(payload["conversation_history"]), 2)

    def test_generate_report_then_restart(self):
        self.client.post(
            "/v1/analysis/start",
            json={
                "task_id": "task-report",
                "device_id": "PUMP-003",
                "category": "离心泵",
                "metadata": {"location": "产线C"},
            },
        )

        self.client.post(
            "/v1/analysis/pulse",
            json={
                "task_id": "task-report",
                "t_predicted": 80.0,
                "t_actual": 96.0,
                "status": "RUNNING",
            },
        )

        original_generator = endpoints.generate_report_html
        endpoints.generate_report_html = lambda **_: "<section><h1>测试报告</h1></section>"
        try:
            response = self.client.post(
                "/v1/analysis/report/generate",
                json={
                    "task_id": "task-report",
                    "issue_summary": "温差快速扩大",
                    "history_data": {"pulse_history": [{"t_actual": 96.0, "t_predicted": 80.0}]},
                    "chat_messages": [
                        {
                            "id": "msg-1",
                            "speaker": "expert",
                            "title": "深度专家评估 第 2 轮",
                            "text": "已定位异常时段。",
                            "type": "agent",
                        }
                    ],
                },
            )
        finally:
            endpoints.generate_report_html = original_generator

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("测试报告", payload["report_html"])

        report_payload = self.client.get("/v1/analysis/report/task-report").json()
        self.assertTrue(report_payload["summary"]["monitoring_locked"])
        self.assertTrue(report_payload["summary"]["report_ready"])
        self.assertIn("测试报告", report_payload["report_html"])

        restart_response = self.client.post("/v1/analysis/restart", json={"task_id": "task-report"})
        self.assertEqual(restart_response.status_code, 200)

        restarted_report = self.client.get("/v1/analysis/report/task-report").json()
        self.assertFalse(restarted_report["summary"]["monitoring_locked"])
        self.assertFalse(restarted_report["summary"]["report_ready"])
        self.assertEqual(restarted_report["conversation_history"], [])


if __name__ == "__main__":
    unittest.main()
