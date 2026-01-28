from typing import TypedDict, List, Annotated, Dict, Any
import operator

class AgentState(TypedDict):
    # --- 外部传入的上下文 ---
    task_id: str
    device_info: Dict[str, Any]  # 包含 ID, 类别, 状态等
    
    # --- 数据流 (使用 operator.add 实现自动追加) ---
    # 记录每次传入的 TDI，用于趋势分析
    tdi_history: Annotated[List[float], operator.add] 
    # 记录专家提过的所有要求
    expert_requests: Annotated[List[str], operator.add]
    
    # --- 实时动态数据 (由 API 每次传入) ---
    current_data: Dict[str, Any] # 包含当前的 t_actual, t_predicted 等
    
    # --- 智能体产出 ---
    latest_report: str           # Agent 1 给 Agent 2 的分析报告
    diagnostic_conclusion: str   # Agent 2 给出的诊断结论
    
    # --- 流程控制 ---
    should_terminate: bool       # Agent 1 决定是否结束整场监控
    next_node: str               # 内部路由占位符