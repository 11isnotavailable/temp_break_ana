from fastapi import APIRouter, HTTPException
from .schemas import StartTaskRequest, PulseRequest, PulseResponse
from ..agents.graph import app_graph

router = APIRouter()

# 模拟状态存储 (Task ID -> State)
sessions = {}

@router.post("/start")
async def start_task(req: StartTaskRequest):
    sessions[req.task_id] = {
        "task_id": req.task_id,
        "device_info": {"id": req.device_id, "category": req.category, **req.metadata},
        "tdi_history": [],
        "expert_requests": [],
        "latest_report": "等待首次数据输入...",
        "diagnostic_conclusion": "",
        "should_terminate": False
    }
    return {"status": "success"}

@router.post("/pulse", response_model=PulseResponse)
async def pulse(req: PulseRequest):
    if req.task_id not in sessions:
        raise HTTPException(status_code=404, detail="Task not found")
    
    try:
        state = sessions[req.task_id]
        # 确保使用 model_dump() 兼容 Pydantic v2
        state["current_data"] = req.model_dump() 
        
        # 运行图逻辑
        final_state = await app_graph.ainvoke(state)
        
        # 更新状态
        sessions[req.task_id] = final_state
        
        decision = "TERMINATE" if final_state.get("should_terminate") else "CONTINUE"
        
        return {
            "task_id": req.task_id,
            "decision": decision,
            "feedback": {
                "tdi_value": final_state["tdi_history"][-1],
                "latest_report": final_state.get("latest_report", ""),
                "diagnosis": final_state.get("diagnostic_conclusion", ""),
                "requests": final_state.get("expert_requests", [])
            }
        }
    except Exception as e:
        # 关键：这里会把具体的 LLM 报错打印在运行 main.py 的终端里
        print(f"！！！后端运行出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))