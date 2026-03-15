import logging
from time import perf_counter
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.config import settings
from ..services.calc_utils import (
    coerce_int,
    collect_records_by_range,
    describe_recent_pulses,
    extract_json_block,
    format_records_block,
    make_message,
    merge_record_ids,
    normalize_string_list,
    pick_records_by_ids,
)
from ..services.mock_data_service import append_runtime_record
from .prompts import EXPERT_FINAL_SYSTEM_PROMPT, EXPERT_REVIEW_SYSTEM_PROMPT, SCOUT_SYSTEM_PROMPT
from .state import AgentState

logger = logging.getLogger("fault_diagnosis.agents")

llm = ChatOpenAI(
    model=settings.MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_API_BASE,
    temperature=0.2,
    timeout=60,
)


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(_stringify_content(item) for item in content if _stringify_content(item)).strip()
    text = getattr(content, "text", "") or getattr(content, "content", "")
    return str(text or content).strip()


def _summarize_ranges(ranges: List[Dict[str, Any]]) -> str:
    if not ranges:
        return "无"
    parts = []
    for item in ranges:
        start_seq = coerce_int(item.get("start"))
        end_seq = coerce_int(item.get("end"))
        if start_seq and end_seq:
            parts.append(f"#{start_seq}-#{end_seq}")
    return "、".join(parts) or "无"


def _summarize_record_ids(record_ids: List[int]) -> str:
    ordered = [coerce_int(record_id) for record_id in record_ids if coerce_int(record_id) > 0]
    if not ordered:
        return "无"
    if len(ordered) <= 8:
        return "、".join(f"#{record_id}" for record_id in ordered)
    head = "、".join(f"#{record_id}" for record_id in ordered[:4])
    tail = "、".join(f"#{record_id}" for record_id in ordered[-3:])
    return f"{head} ... {tail}"


def _invoke_text(system_prompt: str, human_input: str) -> str:
    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_input),
        ]
    )
    return _stringify_content(response.content)


def scout_agent(state: AgentState):
    started_at = perf_counter()
    current_data = state.get("current_data", {})
    pending_request = dict(state.get("pending_request") or {})
    current_cycle_recorded = bool(state.get("current_cycle_recorded"))
    data_records = list(state.get("data_records", []))

    logger.info(
        "scout start | task_id=%s pending_request=%s current_cycle_recorded=%s",
        state.get("task_id"),
        bool(pending_request),
        current_cycle_recorded,
    )

    if pending_request:
        requested_start = coerce_int(pending_request.get("range_start"))
        requested_end = coerce_int(pending_request.get("range_end"), requested_start)
        packet_records, actual_start, actual_end, clipped = collect_records_by_range(
            data_records,
            requested_start,
            requested_end,
        )
        available_start = coerce_int(data_records[0].get("sequence")) if data_records else 0
        available_end = coerce_int(data_records[-1].get("sequence")) if data_records else 0
        sent_everything = bool(packet_records) and actual_start == available_start and actual_end == available_end
        delivered_ids = [coerce_int(item.get("sequence")) for item in packet_records]
        merged_ids = merge_record_ids(state.get("delivered_record_ids", []), delivered_ids)
        final_record_ids = merge_record_ids(state.get("final_record_ids", []), delivered_ids)
        request_reason = str(pending_request.get("reason") or "需要补充上下文数据。").strip()

        summary_text = (
            f"已按专家要求补送序号#{actual_start}-#{actual_end}的监测记录。"
            if packet_records
            else "当前没有可供补送的监测记录。"
        )
        if clipped or sent_everything:
            summary_text += " 当前已提供全部可用记录，请专家直接生成诊断报告。"

        summary_message, counter = make_message(
            state,
            "scout",
            "实时监控 Agent 数据补送",
            summary_text,
            "agent",
        )
        working_state = {**state, "message_counter": counter}
        payload_message, counter = make_message(
            working_state,
            "system",
            f"补送数据包 #{actual_start}-#{actual_end}",
            f"专家取数原因：{request_reason}\n{format_records_block(packet_records)}",
            "system",
        )

        logger.info(
            "scout delivered requested range | task_id=%s requested=%s-%s actual=%s-%s clipped=%s",
            state.get("task_id"),
            requested_start,
            requested_end,
            actual_start,
            actual_end,
            clipped,
        )
        logger.info(
            "scout end | task_id=%s next_node=expert elapsed=%.2fs",
            state.get("task_id"),
            perf_counter() - started_at,
        )
        return {
            "expert_status": "running",
            "next_node": "expert",
            "conversation_closed": False,
            "report_ready": False,
            "pending_request": {},
            "pending_requests": [],
            "latest_data_window": packet_records,
            "delivered_record_ids": merged_ids,
            "final_record_ids": final_record_ids,
            "all_data_exhausted": clipped or sent_everything,
            "conversation_history": [summary_message, payload_message],
            "message_counter": counter,
        }

    if not current_data:
        logger.warning("scout skipped | task_id=%s reason=no_current_data", state.get("task_id"))
        return {
            "expert_status": "sleeping",
            "next_node": "end",
            "conversation_closed": False,
            "report_ready": False,
        }

    human_input = (
        f"设备类别: {state['device_info'].get('category')}\n"
        f"当前温度: 实际={current_data.get('t_actual')}, 预测={current_data.get('t_predicted')}\n"
        f"设备状态: {current_data.get('status')}\n"
        f"扩展指标: {current_data.get('extra_metrics', {})}\n"
        f"最近脉冲摘要:\n{describe_recent_pulses(state.get('pulse_history', []))}"
    )

    logger.info("scout model invoke started | task_id=%s", state.get("task_id"))
    latest_report = _invoke_text(SCOUT_SYSTEM_PROMPT, human_input)
    logger.info(
        "scout model invoke completed | task_id=%s elapsed=%.2fs report_len=%s",
        state.get("task_id"),
        perf_counter() - started_at,
        len(latest_report),
    )

    next_records = data_records
    current_record: Dict[str, Any] = data_records[-1] if data_records else {}
    if not current_cycle_recorded:
        next_records, current_record = append_runtime_record(data_records, current_data, latest_report)

    current_tdi = float(current_record.get("tdi_value", 0.0))
    is_anomaly = current_tdi > settings.TDI_THRESHOLD
    updates: Dict[str, Any] = {
        "data_records": next_records,
        "tdi_history": [current_tdi] if not current_cycle_recorded else [],
        "scout_reports": [latest_report],
        "latest_report": latest_report,
        "is_anomaly": is_anomaly,
        "should_terminate": False,
        "report_ready": False,
        "current_cycle_recorded": True,
        "all_data_exhausted": False,
    }

    if not is_anomaly:
        logger.info("scout end | task_id=%s next_node=end anomaly=%s", state.get("task_id"), is_anomaly)
        updates.update(
            {
                "expert_status": "sleeping",
                "next_node": "end",
                "conversation_closed": False,
                "pending_request": {},
                "pending_requests": [],
                "latest_data_window": [],
            }
        )
        return updates

    recent_records = next_records[-3:]
    recent_ids = [coerce_int(item.get("sequence")) for item in recent_records]
    delivered_record_ids = merge_record_ids(state.get("delivered_record_ids", []), recent_ids)
    final_record_ids = merge_record_ids(state.get("final_record_ids", []), recent_ids)
    start_seq = coerce_int(recent_records[0].get("sequence")) if recent_records else 0
    end_seq = coerce_int(recent_records[-1].get("sequence")) if recent_records else 0

    summary_message, counter = make_message(
        state,
        "scout",
        "实时监控 Agent 异常摘要",
        f"第{current_record.get('sequence')}条记录触发异常，TDI={current_tdi:.2%}。已将最近3条记录及对应监控分析发送给深度专家，建议继续审查。",
        "agent",
    )
    working_state = {**state, "message_counter": counter}
    payload_message, counter = make_message(
        working_state,
        "system",
        f"首轮异常数据包 #{start_seq}-#{end_seq}",
        format_records_block(recent_records),
        "system",
    )

    logger.info(
        "scout end | task_id=%s next_node=expert anomaly=%s range=%s-%s",
        state.get("task_id"),
        is_anomaly,
        start_seq,
        end_seq,
    )
    updates.update(
        {
            "expert_status": "running",
            "next_node": "expert",
            "conversation_closed": False,
            "pending_request": {},
            "pending_requests": [],
            "latest_data_window": recent_records,
            "delivered_record_ids": delivered_record_ids,
            "final_record_ids": final_record_ids,
            "conversation_history": [summary_message, payload_message],
            "message_counter": counter,
        }
    )
    return updates


def expert_agent(state: AgentState):
    started_at = perf_counter()
    turn_number = int(state.get("expert_turn_count", 0)) + 1
    force_finalize = turn_number >= settings.MAX_EXPERT_TURNS or bool(state.get("all_data_exhausted"))
    data_window = list(state.get("latest_data_window", []))
    delivered_ids = list(state.get("delivered_record_ids", []))
    requested_ranges = list(state.get("expert_requested_ranges", []))

    review_input = (
        f"当前专家轮次: 第{turn_number}轮\n"
        f"最大允许轮次: {settings.MAX_EXPERT_TURNS}\n"
        f"设备类别: {state['device_info'].get('category')}\n"
        f"最新监控异常摘要: {state.get('latest_report', '')}\n"
        f"本轮送达记录:\n{format_records_block(data_window)}\n"
        f"已送达过的全部记录序号: {_summarize_record_ids(delivered_ids)}\n"
        f"历史取数范围: {_summarize_ranges(requested_ranges)}\n"
        f"是否已提供全部可用记录: {'是' if state.get('all_data_exhausted') else '否'}\n"
        f"{'当前必须停止取数并直接给出 enough。' if force_finalize else ''}"
    )

    logger.info(
        "expert review started | task_id=%s turn=%s force_finalize=%s delivered=%s",
        state.get("task_id"),
        turn_number,
        force_finalize,
        len(delivered_ids),
    )
    review_raw = _invoke_text(EXPERT_REVIEW_SYSTEM_PROMPT, review_input)
    parsed = extract_json_block(review_raw)
    summary = str(parsed.get("summary") or review_raw or "已完成本轮审查。").strip()
    decision = str(parsed.get("decision") or "enough").strip().lower()
    range_start = parsed.get("range_start")
    range_end = parsed.get("range_end")
    reason = str(parsed.get("reason") or "").strip()

    summary_message, counter = make_message(
        state,
        "expert",
        f"深度专家审查 第{turn_number}轮",
        summary,
        "agent",
    )

    if not force_finalize and decision == "request_more":
        start_seq = coerce_int(range_start)
        end_seq = coerce_int(range_end, start_seq)
        if start_seq > 0 and end_seq >= start_seq:
            request_text = f"请补充序号#{start_seq}-#{end_seq}的历史记录。"
            working_state = {**state, "message_counter": counter}
            request_message, counter = make_message(
                working_state,
                "expert",
                f"深度专家取数请求 第{turn_number}轮",
                f"{request_text} {reason}".strip(),
                "system",
            )
            logger.info(
                "expert requested more data | task_id=%s turn=%s range=%s-%s",
                state.get("task_id"),
                turn_number,
                start_seq,
                end_seq,
            )
            return {
                "expert_turn_count": turn_number,
                "expert_status": "running",
                "diagnosis_ready": False,
                "conversation_closed": False,
                "report_ready": False,
                "next_node": "scout",
                "pending_request": {
                    "range_start": start_seq,
                    "range_end": end_seq,
                    "reason": reason,
                },
                "pending_requests": [request_text],
                "expert_requests": [request_text],
                "expert_requested_ranges": [*requested_ranges, {"start": start_seq, "end": end_seq}],
                "conversation_history": [summary_message, request_message],
                "message_counter": counter,
            }

    final_record_ids = list(state.get("final_record_ids", [])) or delivered_ids
    final_records = pick_records_by_ids(state.get("data_records", []), final_record_ids)
    package_text = (
        f"系统已整理最终资料包，包含记录 {_summarize_record_ids(final_record_ids)}。请基于这些记录直接生成诊断报告。"
    )
    working_state = {**state, "message_counter": counter}
    package_message, counter = make_message(
        working_state,
        "system",
        "系统提示",
        package_text,
        "system",
    )

    final_input = (
        f"设备信息: {state.get('device_info', {})}\n"
        f"最新监控异常摘要: {state.get('latest_report', '')}\n"
        f"多轮取数范围: {_summarize_ranges(requested_ranges)}\n"
        f"最终资料包记录:\n{format_records_block(final_records)}"
    )
    final_raw = _invoke_text(EXPERT_FINAL_SYSTEM_PROMPT, final_input)
    final_parsed = extract_json_block(final_raw)
    diagnosis = str(final_parsed.get("diagnosis") or summary or "基于现有记录判断存在温差异常。").strip()
    actions = normalize_string_list(final_parsed.get("actions"))
    if not actions:
        actions = [
            "检查润滑系统与轴承状态。",
            "复核冷却回路与现场散热条件。",
            "在人工处理后继续观察温差是否回落。",
        ]

    working_state = {**working_state, "message_counter": counter}
    diagnosis_message, counter = make_message(
        working_state,
        "expert",
        "深度专家最终诊断",
        diagnosis,
        "result",
    )
    working_state = {**working_state, "message_counter": counter}
    actions_message, counter = make_message(
        working_state,
        "expert",
        "处置建议",
        "；".join(actions),
        "result",
    )

    logger.info(
        "expert finalized | task_id=%s turn=%s elapsed=%.2fs records=%s actions=%s",
        state.get("task_id"),
        turn_number,
        perf_counter() - started_at,
        len(final_records),
        len(actions),
    )
    return {
        "expert_turn_count": turn_number,
        "diagnostic_conclusion": diagnosis,
        "actions": actions,
        "pending_request": {},
        "pending_requests": [],
        "conversation_history": [summary_message, package_message, diagnosis_message, actions_message],
        "message_counter": counter,
        "expert_status": "done",
        "diagnosis_ready": True,
        "conversation_closed": True,
        "report_ready": False,
        "next_node": "end",
        "all_data_exhausted": False,
    }
