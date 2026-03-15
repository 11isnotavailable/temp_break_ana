from langgraph.graph import END, StateGraph

from ..core.config import settings
from .nodes import expert_agent, scout_agent
from .state import AgentState


def create_industrial_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("scout", scout_agent)
    workflow.add_node("expert", expert_agent)
    workflow.set_entry_point("scout")

    def route_after_scout(state: AgentState):
        if state.get("should_terminate"):
            return "terminate"
        return state.get("next_node", "end")

    def route_after_expert(state: AgentState):
        if state.get("diagnosis_ready"):
            return "end"
        if state.get("pending_request") and state.get("expert_turn_count", 0) < settings.MAX_EXPERT_TURNS:
            return "scout"
        return "end"

    workflow.add_conditional_edges(
        "scout",
        route_after_scout,
        {
            "expert": "expert",
            "terminate": END,
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "expert",
        route_after_expert,
        {
            "scout": "scout",
            "end": END,
        },
    )
    return workflow.compile()


app_graph = create_industrial_graph()
