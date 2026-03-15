import logging
from time import perf_counter

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.config import settings
from ..services.calc_utils import (
    calculate_tdi,
    describe_recent_pulses,
    extract_json_block,
    make_message,
    normalize_string_list,
    resolve_pending_requests,
    summarize_recent_history,
)
from .prompts import EXPERT_SYSTEM_PROMPT, SCOUT_SYSTEM_PROMPT
from .state import AgentState

logger = logging.getLogger("fault_diagnosis.agents")

llm = ChatOpenAI(
    model=settings.MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_API_BASE,
    temperature=0.2,
    timeout=60,
)


def scout_agent(state: AgentState):
    started_at = perf_counter()
    curr = state["current_data"]
    t_act = curr.get("t_actual")
    t_pre = curr.get("t_predicted")
    current_tdi = calculate_tdi(t_act, t_pre)

    recorded_this_cycle = bool(state.get("current_cycle_recorded"))
    existing_tdis = state.get("tdi_history", [])
    all_tdis = existing_tdis if recorded_this_cycle else existing_tdis + [current_tdi]
    recent = all_tdis[-settings.STABLE_CYCLES :]
    is_stable = len(recent) == settings.STABLE_CYCLES and all(value < settings.TDI_THRESHOLD for value in recent)
    is_anomaly = current_tdi > settings.TDI_THRESHOLD
    pending_requests = state.get("pending_requests", [])
    should_continue_dialogue = is_anomaly or bool(pending_requests)

    logger.info(
        "scout start | task_id=%s anomaly=%s pending_requests=%s current_cycle_recorded=%s",
        state.get("task_id"),
        is_anomaly,
        len(pending_requests),
        recorded_this_cycle,
    )

    request_context = resolve_pending_requests(state, pending_requests)
    human_input = (
        f"设备类别: {state['device_info'].get('category')}\n"
        f"当前温度: 实际={t_act}, 预测={t_pre}, TDI={current_tdi:.2%}\n"
        f"设备状态: {curr.get('status')}\n"
        f"扩展指标: {curr.get('extra_metrics', {})}\n"
        f"最近脉冲摘要:\n{describe_recent_pulses(state.get('pulse_history', []))}\n"
        f"待回应请求: {pending_requests or '无'}\n"
        f"请求对应数据:\n{request_context or '无'}"
    )

    logger.info("scout model invoke started | task_id=%s", state.get("task_id"))
    response = llm.invoke(
        [
            SystemMessage(content=SCOUT_SYSTEM_PROMPT),
            HumanMessage(content=human_input),
        ]
    )
    latest_report = str(response.content).strip()
    logger.info(
        "scout model invoke completed | task_id=%s elapsed=%.2fs report_len=%s",
        state.get("task_id"),
        perf_counter() - started_at,
        len(latest_report),
    )

    updates = {
        "scout_reports": [latest_report],
        "latest_report": latest_report,
        "is_anomaly": is_anomaly,
        "should_terminate": is_stable and not should_continue_dialogue,
        "expert_status": "running" if should_continue_dialogue else "sleeping",
        "next_node": "expert" if should_continue_dialogue else "end",
        "conversation_closed": False,
        "report_ready": False,
        "current_cycle_recorded": True,
    }

    if not recorded_this_cycle:
        updates["tdi_history"] = [current_tdi]

    if should_continue_dialogue:
        title = "实时监控 Agent 数据回应" if pending_requests else "实时监控 Agent 异常摘要"
        message, counter = make_message(state, "scout", title, latest_report, "agent")
        updates["conversation_history"] = [message]
        updates["message_counter"] = counter

    logger.info(
        "scout end | task_id=%s next_node=%s should_terminate=%s expert_status=%s",
        state.get("task_id"),
        updates["next_node"],
        updates["should_terminate"],
        updates["expert_status"],
    )
    return updates


def expert_agent(state: AgentState):
    started_at = perf_counter()
    turn_number = int(state.get("expert_turn_count", 0)) + 1
    force_finalize = turn_number >= settings.MAX_EXPERT_TURNS
    current_tdi = state.get("tdi_history", [])[-1] if state.get("tdi_history") else 0.0
    recent_history = summarize_recent_history(state.get("conversation_history", []))

    human_input = (
        f"当前专家轮次: 第 {turn_number} 轮\n"
        f"最大追问轮次: {settings.MAX_EXPERT_TURNS}\n"
        f"设备类别: {state['device_info'].get('category')}\n"
        f"当前 TDI: {current_tdi:.2%}\n"
        f"监控摘要: {state.get('latest_report', '')}\n"
        f"最近对话历史:\n{recent_history}\n"
        f"最近脉冲数据:\n{describe_recent_pulses(state.get('pulse_history', []))}\n"
        f"当前待回应请求: {state.get('pending_requests', [])}\n"
        f"{'当前已到最后允许轮次，必须直接给出诊断结论和处置建议。' if force_finalize else ''}"
    )

    logger.info(
        "expert start | task_id=%s turn=%s force_finalize=%s pending_requests=%s",
        state.get("task_id"),
        turn_number,
        force_finalize,
        len(state.get("pending_requests", [])),
    )
    logger.info("expert model invoke started | task_id=%s turn=%s", state.get("task_id"), turn_number)
    response = llm.invoke(
        [
            SystemMessage(content=EXPERT_SYSTEM_PROMPT),
            HumanMessage(content=human_input),
        ]
    )

    content = str(response.content).strip()
    parsed = extract_json_block(content)
    thinking = str(parsed.get("thinking") or content).strip()
    need_more_data = bool(parsed.get("need_more_data")) and not force_finalize
    requests = normalize_string_list(parsed.get("requests"))
    diagnosis = str(parsed.get("diagnosis") or "").strip()
    actions = normalize_string_list(parsed.get("actions"))
    logger.info(
        "expert model invoke completed | task_id=%s turn=%s elapsed=%.2fs need_more_data=%s requests=%s diagnosis_present=%s actions=%s",
        state.get("task_id"),
        turn_number,
        perf_counter() - started_at,
        need_more_data,
        len(requests),
        bool(diagnosis),
        len(actions),
    )

    updates = {
        "expert_turn_count": turn_number,
        "expert_status": "running",
        "diagnosis_ready": False,
        "conversation_closed": False,
        "report_ready": False,
        "next_node": "end",
    }

    first_message, counter = make_message(
        state,
        "expert",
        f"深度专家评估 第 {turn_number} 轮",
        thinking,
        "agent",
    )
    conversation_updates = [first_message]
    working_state = {**state, "message_counter": counter}

    if need_more_data and requests:
        request_message, counter = make_message(
            working_state,
            "expert",
            f"深度专家请求 第 {turn_number} 轮",
            "；".join(requests),
            "system",
        )
        conversation_updates.append(request_message)
        updates.update(
            {
                "pending_requests": requests,
                "expert_requests": requests,
                "conversation_history": conversation_updates,
                "message_counter": counter,
                "next_node": "scout",
                "actions": state.get("actions", []),
                "conversation_closed": False,
            }
        )
        logger.info(
            "expert loop back to scout | task_id=%s turn=%s requests=%s",
            state.get("task_id"),
            turn_number,
            requests,
        )
        return updates

    if not diagnosis:
        diagnosis = thinking
    if not actions:
        actions = ["建议立即复核润滑、冷却及运行负载等关键部件状态。"]

    diagnosis_message, counter = make_message(
        working_state,
        "expert",
        "诊断结论",
        diagnosis,
        "result",
    )
    conversation_updates.append(diagnosis_message)
    working_state = {**working_state, "message_counter": counter}

    actions_message, counter = make_message(
        working_state,
        "expert",
        "处置建议",
        "；".join(actions),
        "result",
    )
    conversation_updates.append(actions_message)

    updates.update(
        {
            "diagnostic_conclusion": diagnosis,
            "actions": actions,
            "pending_requests": [],
            "conversation_history": conversation_updates,
            "message_counter": counter,
            "expert_status": "done",
            "diagnosis_ready": True,
            "conversation_closed": True,
            "report_ready": False,
            "next_node": "end",
        }
    )
    logger.info(
        "expert finalized | task_id=%s turn=%s diagnosis_len=%s actions=%s",
        state.get("task_id"),
        turn_number,
        len(diagnosis),
        len(actions),
    )
    return updates
