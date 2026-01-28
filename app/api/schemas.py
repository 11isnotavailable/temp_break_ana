from pydantic import BaseModel
from typing import Optional, Dict, List, Any

class StartTaskRequest(BaseModel):
    task_id: str
    device_id: str
    category: str
    metadata: Optional[Dict] = {}

class PulseRequest(BaseModel):
    task_id: str
    t_predicted: float
    t_actual: float
    status: str
    extra_metrics: Optional[Dict] = {}

class PulseResponse(BaseModel):
    task_id: str
    decision: str  # CONTINUE 或 TERMINATE
    feedback: Dict[str, Any]