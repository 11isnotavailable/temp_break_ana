from typing import Annotated, Any, Dict, List, TypedDict
import operator


class AgentState(TypedDict):
    task_id: str
    device_info: Dict[str, Any]
    tdi_history: Annotated[List[float], operator.add]
    scout_reports: Annotated[List[str], operator.add]
    expert_requests: Annotated[List[str], operator.add]
    conversation_history: Annotated[List[Dict[str, Any]], operator.add]
    pulse_history: List[Dict[str, Any]]
    current_data: Dict[str, Any]
    latest_report: str
    diagnostic_conclusion: str
    actions: List[str]
    generated_report_html: str
    is_anomaly: bool
    expert_status: str
    should_terminate: bool
    next_node: str
    pending_requests: List[str]
    diagnosis_ready: bool
    conversation_closed: bool
    monitoring_locked: bool
    report_ready: bool
    expert_turn_count: int
    current_cycle_recorded: bool
    message_counter: int
