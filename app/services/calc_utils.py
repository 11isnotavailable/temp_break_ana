import json
from typing import Any, Dict, List, Tuple


def calculate_tdi(t_actual: float, t_predicted: float) -> float:
    return abs(t_actual - t_predicted) / (t_predicted + 1e-6)


def extract_json_block(text: str) -> Dict[str, Any]:
    if not text:
        return {}

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return {}

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def normalize_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def make_message(
    state: Dict[str, Any],
    speaker: str,
    title: str,
    text: str,
    kind: str,
) -> Tuple[Dict[str, Any], int]:
    counter = int(state.get("message_counter", 0)) + 1
    return (
        {
            "id": f"msg-{counter}",
            "speaker": speaker,
            "title": title,
            "text": text,
            "type": kind,
        },
        counter,
    )


def summarize_recent_history(conversation_history: List[Dict[str, Any]], limit: int = 6) -> str:
    if not conversation_history:
        return "无历史对话。"

    recent = conversation_history[-limit:]
    return "\n".join(
        f"{item.get('speaker', 'agent')} | {item.get('title', '')}: {item.get('text', '')}" for item in recent
    )


def describe_recent_pulses(pulse_history: List[Dict[str, Any]], limit: int = 5) -> str:
    if not pulse_history:
        return "暂无历史脉冲数据。"

    lines = []
    for index, item in enumerate(pulse_history[-limit:], start=1):
        lines.append(
            f"第{index}条: 预测温度={item.get('t_predicted')}, 实际温度={item.get('t_actual')}, "
            f"状态={item.get('status')}, 扩展指标={item.get('extra_metrics', {})}"
        )
    return "\n".join(lines)


def format_record(record: Dict[str, Any]) -> str:
    return (
        f"序号#{record.get('sequence')} | 时间={record.get('recorded_at')} | "
        f"实际温度={record.get('t_actual')} | 预测温度={record.get('t_predicted')} | "
        f"TDI={record.get('tdi_value', 0):.2%} | 状态={record.get('status')} | "
        f"监控分析={record.get('scout_analysis', '')}"
    )


def format_records_block(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "暂无记录。"
    return "\n".join(format_record(record) for record in records)


def merge_record_ids(existing: List[int], incoming: List[int]) -> List[int]:
    return sorted({coerce_int(item) for item in existing + incoming if coerce_int(item) > 0})


def pick_records_by_ids(records: List[Dict[str, Any]], record_ids: List[int]) -> List[Dict[str, Any]]:
    wanted = {coerce_int(record_id) for record_id in record_ids if coerce_int(record_id) > 0}
    return [record for record in records if coerce_int(record.get("sequence")) in wanted]


def collect_records_by_range(
    records: List[Dict[str, Any]],
    start_seq: int,
    end_seq: int,
) -> Tuple[List[Dict[str, Any]], int, int, bool]:
    if not records:
        return [], 0, 0, True

    available_start = coerce_int(records[0].get("sequence"), 1)
    available_end = coerce_int(records[-1].get("sequence"), available_start)
    normalized_start = max(min(coerce_int(start_seq, available_start), available_end), available_start)
    normalized_end = max(min(coerce_int(end_seq, available_end), available_end), normalized_start)
    subset = [
        record
        for record in records
        if normalized_start <= coerce_int(record.get("sequence")) <= normalized_end
    ]
    exhausted = normalized_start != coerce_int(start_seq, normalized_start) or normalized_end != coerce_int(
        end_seq, normalized_end
    )
    return subset, normalized_start, normalized_end, exhausted


def resolve_pending_requests(state: Dict[str, Any], pending_requests: List[str]) -> str:
    if not pending_requests:
        return ""

    curr = state.get("current_data", {})
    extra = curr.get("extra_metrics", {})
    pulse_history = state.get("pulse_history", [])
    latest_pulse = pulse_history[-1] if pulse_history else {}
    response_lines = []

    for request in pending_requests:
        parts = [f"请求：{request}"]
        if "振动" in request:
            value = extra.get("vibration", latest_pulse.get("extra_metrics", {}).get("vibration"))
            parts.append(f"振动数据：{value if value is not None else '当前暂无该项数据'}")
        if "电流" in request or "负载" in request:
            value = extra.get("current", latest_pulse.get("extra_metrics", {}).get("current"))
            parts.append(f"电流/负载数据：{value if value is not None else '当前暂无该项数据'}")
        if "温度" in request:
            parts.append(
                f"当前温度：实际={curr.get('t_actual', '未知')}，预测={curr.get('t_predicted', '未知')}"
            )
        if len(parts) == 1:
            parts.append(f"当前可用扩展指标：{extra or '暂无'}")
        response_lines.append("；".join(parts))

    return "\n".join(response_lines)
