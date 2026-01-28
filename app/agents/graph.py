from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import scout_agent, expert_agent

def create_industrial_graph():
    # 1. 初始化图
    workflow = StateGraph(AgentState)

    # 2. 添加节点
    workflow.add_node("scout", scout_agent)   # Agent 1: 数据排查
    workflow.add_node("expert", expert_agent) # Agent 2: 故障诊断

    # 3. 设置起点
    workflow.set_entry_point("scout")

    # 4. 定义跳转逻辑
    def router(state: AgentState):
        # 如果 Agent 1 认为情况已经稳定，直接发指令给后端终止
        if state.get("should_terminate"):
            return "terminate"
        
        # 根据 Scout 节点设置的 next_node 决定去向
        # 如果 TDI 异常或专家有未完成的要求 -> 去专家节点
        return state.get("next_node", "end")

    # 5. 构建连线
    workflow.add_conditional_edges(
        "scout",
        router,
        {
            "expert": "expert",    # 发现异常，去诊断
            "terminate": END,      # 情况稳定，结束调用
            "end": END             # 本轮分析结束，等待下个 30s 脉冲
        }
    )

    # 专家诊断完后，总是回到 Scout 节点，形成闭环等待下一轮数据
    workflow.add_edge("expert", "scout")

    return workflow.compile()

# 导出可供调用的 graph 实例
app_graph = create_industrial_graph()