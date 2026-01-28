import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from ..core.config import settings
from .state import AgentState
from .prompts import SCOUT_SYSTEM_PROMPT, EXPERT_SYSTEM_PROMPT

# 初始化 LLM
llm = ChatOpenAI(
    model=settings.MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_API_BASE,
    temperature=0.2,
    # DeepSeek 有时响应较慢，可以适当增加超时时间
    timeout=60 
)

def scout_agent(state: AgentState):
    """
    Agent 1: 数据侦察员
    职责：计算指标、监控稳定性、整理报告、决定是否调用专家。
    """
    print(f"\n[Agent 1] 正在处理任务: {state['task_id']}")
    
    # 1. 提取当前脉冲数据
    curr = state["current_data"]
    t_act = curr.get("t_actual")
    t_pre = curr.get("t_predicted")
    
    # 2. 计算 TDI (热偏移指数)
    # 避免除以零，加入 epsilon 1e-6
    current_tdi = abs(t_act - t_pre) / (t_pre + 1e-6)
    
    # 3. 稳定性与终止逻辑
    # 获取历史记录并加入当前值进行判定
    all_tdis = state.get("tdi_history", []) + [current_tdi]
    is_stable = False
    if len(all_tdis) >= settings.STABLE_CYCLES:
        # 判定最后 N 个周期是否都低于预设阈值
        recent = all_tdis[-settings.STABLE_CYCLES:]
        if all(v < settings.TDI_THRESHOLD for v in recent):
            is_stable = True

    # 4. 构建给 LLM 的上下文 (包含专家的历史要求)
    expert_context = ""
    if state["expert_requests"]:
        # 提取最近的一个专家要求
        expert_context = f"\n[重要] 专家此前要求核查: {state['expert_requests'][-1]}"

    human_input = (
        f"设备类型: {state['device_info'].get('category')}\n"
        f"当前数据: 真实温度={t_act}, 预测温度={t_pre}, TDI={current_tdi:.2%}\n"
        f"设备状态: {curr.get('status')}\n"
        f"{expert_context}"
    )

    # 5. 调用 LLM 生成分析报告
    response = llm.invoke([
        SystemMessage(content=SCOUT_SYSTEM_PROMPT),
        HumanMessage(content=human_input)
    ])
    
    # 6. 决定流程去向
    # 如果 TDI 超过阈值，去专家节点 (expert)；否则结束本次脉冲 (end)
    # 如果系统已经稳定，则标记 should_terminate 为 True
    next_node = "expert" if current_tdi > settings.TDI_THRESHOLD else "end"
    
    return {
        "tdi_history": [current_tdi], # Annotated 会自动 append
        "latest_report": response.content,
        "is_stable": is_stable,
        "should_terminate": is_stable,
        "next_node": next_node
    }

def expert_agent(state: AgentState):
    """
    Agent 2: 故障诊断专家
    职责：基于 Scout 的报告进行故障根因分析，并可能向 Scout 提出更多数据需求。
    """
    print(f"[Agent 2] 正在针对任务 {state['task_id']} 进行深度诊断...")

    # 1. 构建专家分析的上下文
    scout_report = state["latest_report"]
    device_type = state["device_info"].get("category")
    
    human_input = (
        f"监控专家报告: {scout_report}\n"
        f"设备类别: {device_type}\n"
        f"请基于上述信息进行诊断。"
    )

    # 2. 调用 LLM 进行诊断
    response = llm.invoke([
        SystemMessage(content=EXPERT_SYSTEM_PROMPT),
        HumanMessage(content=human_input)
    ])
    
    content = response.content
    
    # 3. 解析专家是否提出了新的数据要求
    # 简单逻辑：如果文本包含“请提供”或“需要查看”，则作为 request 记录
    new_requests = []
    if "请提供" in content or "需要" in content or "?" in content:
        # 这里可以进一步用 LLM 提取具体的字段，目前先记录全文
        new_requests = ["专家发起了新的数据补充请求"]

    return {
        "diagnostic_conclusion": content,
        "expert_requests": new_requests, # Annotated 会自动 append
        "next_node": "end" # 诊断完后，本轮结束，等待 30s 后的下一个数据脉冲
    }