import html
import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.config import settings

logger = logging.getLogger("fault_diagnosis.report")

report_llm = ChatOpenAI(
    model=settings.MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_API_BASE,
    temperature=0.2,
    timeout=45,
    max_retries=1,
)

REPORT_SYSTEM_PROMPT = """
你是工业设备故障诊断报告生成助手。

请基于输入的设备信息、监控摘要、历史脉冲、双 Agent 对话记录、诊断结论和处置建议，
生成一份适合在前端弹窗中展示的完整 HTML 报告。

要求：
1. 只输出 HTML 片段，不要输出 Markdown，不要输出解释文字。
2. 只使用以下标签：section、h1、h2、h3、p、ul、li、table、thead、tbody、tr、th、td、div、span。
3. 内容应包含：问题概述、设备信息、异常摘要、历史数据对比、诊断过程摘要、最终诊断结论、处置建议、后续观察建议。
4. 风格应正式、专业、简洁，适合工业竞赛项目展示。
5. 不要输出 html、body、style、script 标签。
"""


def _render_list(items: List[str]) -> str:
    if not items:
        return "<p>暂无数据。</p>"
    lines = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul>{lines}</ul>"


def _render_chat_messages(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return "<p>暂无对话记录。</p>"

    rows = []
    for item in messages:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('speaker', '')))}</td>"
            f"<td>{html.escape(str(item.get('title', '')))}</td>"
            f"<td>{html.escape(str(item.get('text', '')))}</td>"
            "</tr>"
        )

    return (
        "<table><thead><tr><th>角色</th><th>阶段</th><th>内容</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_history_rows(history_data: Dict[str, Any]) -> str:
    pulse_history = history_data.get("pulse_history", [])
    if not pulse_history:
        return "<p>暂无历史脉冲数据。</p>"

    rows = []
    for index, item in enumerate(pulse_history, start=1):
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{html.escape(str(item.get('t_predicted', '')))}</td>"
            f"<td>{html.escape(str(item.get('t_actual', '')))}</td>"
            f"<td>{html.escape(str(item.get('status', '')))}</td>"
            f"<td>{html.escape(str(item.get('extra_metrics', {})))}</td>"
            "</tr>"
        )

    return (
        "<table><thead><tr><th>序号</th><th>预测温度</th><th>实际温度</th><th>状态</th><th>扩展指标</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _normalize_llm_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "text", "") or getattr(item, "content", "")
                if text:
                    parts.append(str(text))
        return "\n".join(part.strip() for part in parts if part).strip()
    return str(content).strip()


def build_fallback_report(
    state: Dict[str, Any],
    issue_summary: str,
    history_data: Dict[str, Any],
    chat_messages: List[Dict[str, Any]],
) -> str:
    device_info = state.get("device_info", {})
    diagnosis = html.escape(state.get("diagnostic_conclusion", "") or "当前未生成诊断结论。")
    latest_report = html.escape(state.get("latest_report", "") or "暂无最新监控摘要。")
    device_id = html.escape(str(device_info.get("id", "")))
    category = html.escape(str(device_info.get("category", "")))
    location = html.escape(str(device_info.get("location", "未知")))
    issue = html.escape(issue_summary or "未提供问题摘要。")

    return f"""
<section>
  <h1>工业设备故障分析报告</h1>
  <h2>一、问题概述</h2>
  <p>{issue}</p>

  <h2>二、设备信息</h2>
  <ul>
    <li>设备 ID：{device_id}</li>
    <li>设备类别：{category}</li>
    <li>安装位置：{location}</li>
  </ul>

  <h2>三、异常摘要</h2>
  <p>{latest_report}</p>

  <h2>四、历史脉冲与运行数据</h2>
  {_render_history_rows(history_data)}

  <h2>五、双 Agent 诊断过程</h2>
  {_render_chat_messages(chat_messages)}

  <h2>六、最终诊断结论</h2>
  <p>{diagnosis}</p>

  <h2>七、处置建议</h2>
  {_render_list(state.get("actions", []))}

  <h2>八、后续观察建议</h2>
  <ul>
    <li>继续跟踪设备温度、振动、电流和压力等关键指标的变化趋势。</li>
    <li>完成处置后进行复测，确认 TDI 是否回落至稳定区间。</li>
    <li>如异常仍持续，请升级为人工检修并补录现场巡检信息。</li>
  </ul>
</section>
""".strip()


def generate_report_html(
    state: Dict[str, Any],
    issue_summary: str,
    history_data: Dict[str, Any],
    chat_messages: List[Dict[str, Any]],
) -> str:
    payload = {
        "device_info": state.get("device_info", {}),
        "issue_summary": issue_summary,
        "latest_report": state.get("latest_report", ""),
        "diagnostic_conclusion": state.get("diagnostic_conclusion", ""),
        "actions": state.get("actions", []),
        "requests": state.get("expert_requests", []),
        "history_data": history_data,
        "chat_messages": chat_messages,
    }

    logger.info(
        "report llm start | task_id=%s chat_messages=%s pulse_history=%s",
        state.get("task_id"),
        len(chat_messages),
        len(history_data.get("pulse_history", [])),
    )

    try:
        response = report_llm.invoke(
            [
                SystemMessage(content=REPORT_SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        logger.info("report llm response received | task_id=%s", state.get("task_id"))
        content = _normalize_llm_content(response.content)
        logger.info(
            "report llm content normalized | task_id=%s content_len=%s",
            state.get("task_id"),
            len(content),
        )
        if "<section" in content or "<h1" in content:
            logger.info("report llm html accepted | task_id=%s", state.get("task_id"))
            return content
        logger.warning("report llm html rejected, fallback used | task_id=%s", state.get("task_id"))
    except Exception as exc:
        logger.exception("report llm failed, fallback used | task_id=%s error=%s", state.get("task_id"), exc)

    fallback = build_fallback_report(state, issue_summary, history_data, chat_messages)
    logger.info("report fallback built | task_id=%s content_len=%s", state.get("task_id"), len(fallback))
    return fallback
