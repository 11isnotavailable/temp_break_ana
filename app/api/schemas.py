from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class StartTaskRequest(BaseModel):
    task_id: str
    device_id: str
    category: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StartTaskResponse(BaseModel):
    status: str
    message: str


class PulseRequest(BaseModel):
    task_id: str
    t_predicted: float
    t_actual: float
    status: str
    extra_metrics: Dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    id: str
    speaker: str
    title: str
    text: str
    type: Literal["agent", "system", "result"]


class PulseFeedback(BaseModel):
    is_anomaly: bool
    tdi_value: float
    latest_sequence: int
    latest_recorded_at: str
    latest_report: str
    expert_status: Literal["sleeping", "running", "done"]
    conversation_closed: bool
    monitoring_locked: bool
    report_ready: bool
    diagnosis: str
    actions: List[str]
    requests: List[str]
    expert_turn_count: int
    conversation_history: List[ChatMessage]


class PulseResponse(BaseModel):
    task_id: str
    decision: Literal["CONTINUE", "TERMINATE"]
    feedback: PulseFeedback


class ReportSummary(BaseModel):
    is_anomaly: bool
    expert_status: Literal["sleeping", "running", "done"]
    conversation_closed: bool
    monitoring_locked: bool
    report_ready: bool
    latest_sequence: int
    latest_recorded_at: str
    latest_tdi: float
    latest_report: str
    expert_turn_count: int


class DiagnosisReport(BaseModel):
    conclusion: str
    actions: List[str]
    requests: List[str]


class ReportHistory(BaseModel):
    tdi_history: List[float]
    scout_reports: List[str]
    pulse_history: List[Dict[str, Any]]
    data_records: List[Dict[str, Any]]


class ReportResponse(BaseModel):
    task_id: str
    device_info: Dict[str, Any]
    decision: Literal["CONTINUE", "TERMINATE"]
    summary: ReportSummary
    diagnosis: DiagnosisReport
    conversation_history: List[ChatMessage]
    history: ReportHistory
    report_html: str = ""


class GenerateReportRequest(BaseModel):
    task_id: str
    issue_summary: str
    history_data: Dict[str, Any] = Field(default_factory=dict)
    chat_messages: List[ChatMessage] = Field(default_factory=list)


class GenerateReportResponse(BaseModel):
    task_id: str
    status: Literal["success"]
    report_html: str


class RestartTaskRequest(BaseModel):
    task_id: str


class RestartTaskResponse(BaseModel):
    status: Literal["success"]
    task_id: str
    message: str
