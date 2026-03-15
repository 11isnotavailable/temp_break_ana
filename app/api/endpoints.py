import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException

from ..agents.graph import app_graph
from ..services.mock_data_service import build_seed_records
from ..services.report_service import build_fallback_report, generate_report_html
from .schemas import (
    DiagnosisReport,
    GenerateReportRequest,
    GenerateReportResponse,
    PulseFeedback,
    PulseRequest,
    PulseResponse,
    ReportHistory,
    ReportResponse,
    ReportSummary,
    RestartTaskRequest,
    RestartTaskResponse,
    StartTaskRequest,
    StartTaskResponse,
)

router = APIRouter()
logger = logging.getLogger("fault_diagnosis.api")

sessions = {}


def make_session_state(task_id: str, device_id: str, category: str, metadata: dict) -> dict:
    return {
        "task_id": task_id,
        "device_info": {"id": device_id, "category": category, **metadata},
        "tdi_history": [],
        "scout_reports": [],
        "expert_requests": [],
        "conversation_history": [],
        "pulse_history": [],
        "data_records": build_seed_records(),
        "current_data": {},
        "latest_report": "等待首轮监控数据输入",
        "diagnostic_conclusion": "",
        "actions": [],
        "generated_report_html": "",
        "is_anomaly": False,
        "expert_status": "sleeping",
        "should_terminate": False,
        "next_node": "end",
        "pending_requests": [],
        "diagnosis_ready": False,
        "conversation_closed": False,
        "monitoring_locked": False,
        "report_ready": False,
        "expert_turn_count": 0,
        "current_cycle_recorded": False,
        "message_counter": 0,
        "pending_request": {},
        "expert_requested_ranges": [],
        "delivered_record_ids": [],
        "final_record_ids": [],
        "latest_data_window": [],
        "all_data_exhausted": False,
    }


def build_pulse_feedback(state: dict) -> PulseFeedback:
    latest_tdi = state["tdi_history"][-1] if state.get("tdi_history") else 0.0
    latest_record = state.get("data_records", [])[-1] if state.get("data_records") else {}
    return PulseFeedback(
        is_anomaly=state.get("is_anomaly", False),
        tdi_value=latest_tdi,
        latest_sequence=int(latest_record.get("sequence", 0) or 0),
        latest_recorded_at=str(latest_record.get("recorded_at", "") or ""),
        latest_report=state.get("latest_report", ""),
        expert_status=state.get("expert_status", "sleeping"),
        conversation_closed=state.get("conversation_closed", False),
        monitoring_locked=state.get("monitoring_locked", False),
        report_ready=state.get("report_ready", False),
        diagnosis=state.get("diagnostic_conclusion", ""),
        actions=state.get("actions", []),
        requests=state.get("pending_requests", []),
        expert_turn_count=state.get("expert_turn_count", 0),
        conversation_history=state.get("conversation_history", []),
    )


def build_report_response(task_id: str) -> ReportResponse:
    state = sessions[task_id]
    decision = "TERMINATE" if state.get("should_terminate") else "CONTINUE"
    latest_tdi = state["tdi_history"][-1] if state.get("tdi_history") else 0.0
    latest_record = state.get("data_records", [])[-1] if state.get("data_records") else {}

    return ReportResponse(
        task_id=task_id,
        device_info=state["device_info"],
        decision=decision,
        summary=ReportSummary(
            is_anomaly=state.get("is_anomaly", False),
            expert_status=state.get("expert_status", "sleeping"),
            conversation_closed=state.get("conversation_closed", False),
            monitoring_locked=state.get("monitoring_locked", False),
            report_ready=state.get("report_ready", False),
            latest_sequence=int(latest_record.get("sequence", 0) or 0),
            latest_recorded_at=str(latest_record.get("recorded_at", "") or ""),
            latest_tdi=latest_tdi,
            latest_report=state.get("latest_report", ""),
            expert_turn_count=state.get("expert_turn_count", 0),
        ),
        diagnosis=DiagnosisReport(
            conclusion=state.get("diagnostic_conclusion", ""),
            actions=state.get("actions", []),
            requests=state.get("expert_requests", []),
        ),
        conversation_history=state.get("conversation_history", []),
        history=ReportHistory(
            tdi_history=state.get("tdi_history", []),
            scout_reports=state.get("scout_reports", []),
            pulse_history=state.get("pulse_history", []),
            data_records=state.get("data_records", []),
        ),
        report_html=state.get("generated_report_html", ""),
    )


@router.post("/start", response_model=StartTaskResponse)
async def start_task(req: StartTaskRequest):
    logger.info(
        "start_task received | task_id=%s device_id=%s category=%s",
        req.task_id,
        req.device_id,
        req.category,
    )
    sessions[req.task_id] = make_session_state(req.task_id, req.device_id, req.category, req.metadata)
    logger.info("start_task completed | task_id=%s", req.task_id)
    return StartTaskResponse(status="success", message="Analysis session initialized")


@router.post("/restart", response_model=RestartTaskResponse)
async def restart_task(req: RestartTaskRequest):
    if req.task_id not in sessions:
        logger.warning("restart_task rejected | task_id=%s reason=session_not_found", req.task_id)
        raise HTTPException(status_code=404, detail="Task not found")

    state = sessions[req.task_id]
    device_info = dict(state.get("device_info", {}))
    device_id = str(device_info.pop("id", "UNKNOWN"))
    category = str(device_info.pop("category", "UNKNOWN"))
    sessions[req.task_id] = make_session_state(req.task_id, device_id, category, device_info)
    logger.info("restart_task completed | task_id=%s", req.task_id)
    return RestartTaskResponse(status="success", task_id=req.task_id, message="Monitoring restarted")


@router.post("/pulse", response_model=PulseResponse)
async def pulse(req: PulseRequest):
    if req.task_id not in sessions:
        logger.warning("pulse rejected | task_id=%s reason=session_not_found", req.task_id)
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        started_at = perf_counter()
        state = sessions[req.task_id]
        payload = req.model_dump()
        logger.info(
            "pulse received | task_id=%s t_actual=%s t_predicted=%s status=%s",
            req.task_id,
            payload.get("t_actual"),
            payload.get("t_predicted"),
            payload.get("status"),
        )

        if state.get("monitoring_locked"):
            logger.info("pulse short-circuited | task_id=%s reason=monitoring_locked", req.task_id)
            return PulseResponse(
                task_id=req.task_id,
                decision="CONTINUE",
                feedback=build_pulse_feedback(state),
            )

        if state.get("conversation_closed"):
            logger.info("pulse short-circuited | task_id=%s reason=conversation_closed", req.task_id)
            return PulseResponse(
                task_id=req.task_id,
                decision="CONTINUE",
                feedback=build_pulse_feedback(state),
            )

        state["current_data"] = payload
        state["pulse_history"] = list(state.get("pulse_history", [])) + [payload]
        state["current_cycle_recorded"] = False

        logger.info("graph invoke started | task_id=%s pulse_count=%s", req.task_id, len(state["pulse_history"]))
        final_state = await app_graph.ainvoke(state)
        sessions[req.task_id] = final_state
        elapsed = perf_counter() - started_at
        logger.info(
            "graph invoke completed | task_id=%s elapsed=%.2fs decision=%s anomaly=%s expert_status=%s turns=%s messages=%s closed=%s locked=%s",
            req.task_id,
            elapsed,
            "TERMINATE" if final_state.get("should_terminate") else "CONTINUE",
            final_state.get("is_anomaly", False),
            final_state.get("expert_status", "sleeping"),
            final_state.get("expert_turn_count", 0),
            len(final_state.get("conversation_history", [])),
            final_state.get("conversation_closed", False),
            final_state.get("monitoring_locked", False),
        )

        decision = "TERMINATE" if final_state.get("should_terminate") else "CONTINUE"
        return PulseResponse(task_id=req.task_id, decision=decision, feedback=build_pulse_feedback(final_state))
    except Exception as exc:
        logger.exception("pulse failed | task_id=%s error=%s", req.task_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/report/{task_id}", response_model=ReportResponse)
async def get_report(task_id: str):
    if task_id not in sessions:
        logger.warning("get_report rejected | task_id=%s reason=session_not_found", task_id)
        raise HTTPException(status_code=404, detail="Task not found")
    logger.info("get_report | task_id=%s", task_id)
    return build_report_response(task_id)


@router.post("/report/generate", response_model=GenerateReportResponse)
async def generate_report(req: GenerateReportRequest):
    if req.task_id not in sessions:
        logger.warning("generate_report rejected | task_id=%s reason=session_not_found", req.task_id)
        raise HTTPException(status_code=404, detail="Task not found")

    started_at = perf_counter()
    logger.info(
        "generate_report received | task_id=%s input_messages=%s",
        req.task_id,
        len(req.chat_messages),
    )
    state = sessions[req.task_id]
    history_data = {
        "tdi_history": state.get("tdi_history", []),
        "scout_reports": state.get("scout_reports", []),
        "pulse_history": state.get("pulse_history", []),
        "data_records": state.get("data_records", []),
        **req.history_data,
    }
    chat_messages = [message.model_dump() for message in req.chat_messages] or state.get(
        "conversation_history", []
    )
    logger.info("generate_report engine start | task_id=%s", req.task_id)
    try:
        report_html = generate_report_html(
            state=state,
            issue_summary=req.issue_summary,
            history_data=history_data,
            chat_messages=chat_messages,
        )
    except Exception as exc:
        logger.exception("generate_report engine failed | task_id=%s error=%s", req.task_id, exc)
        report_html = build_fallback_report(
            state=state,
            issue_summary=req.issue_summary,
            history_data=history_data,
            chat_messages=chat_messages,
        )
    logger.info("generate_report engine end | task_id=%s html_len=%s", req.task_id, len(report_html))

    state["generated_report_html"] = report_html
    state["report_ready"] = True
    state["monitoring_locked"] = True
    state["conversation_closed"] = True
    state["latest_report"] = "诊断报告已生成，当前监控已锁定，请人工处理后手动恢复监控。"
    sessions[req.task_id] = state
    logger.info(
        "generate_report completed | task_id=%s elapsed=%.2fs report_size=%s",
        req.task_id,
        perf_counter() - started_at,
        len(report_html),
    )

    return GenerateReportResponse(task_id=req.task_id, status="success", report_html=report_html)
