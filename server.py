import uvicorn
import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# Import your LangGraph app
from agent import app 

# --- SETUP ---
api = FastAPI(title="Payment Agent Backend")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATA MODELS ---
class AgentRequest(BaseModel):
    thread_id: str = "demo_session_1"

class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool

# --- HELPER FUNCTIONS ---
def get_config(thread_id: str):
    return {"configurable": {"thread_id": thread_id}}

def parse_logs(event_stream) -> List[str]:
    """Helper to extract clean strings from LangGraph events"""
    logs = []
    for event in event_stream:
        for node, update in event.items():
            if "reasoning_log" in update:
                entry = f"[{node.upper()}] {update['reasoning_log'][-1]}"
                logs.append(entry)
    return logs

# --- ENDPOINTS ---

@api.get("/")
def health_check():
    return {"status": "Agent is online"}

@api.get("/telemetry")
def get_telemetry():
    """
    READS: transactions.log
    FEEDS: The React Frontend (Latency Chart + Metrics)
    """
    log_file = "transactions.log"
    if not os.path.exists(log_file):
        return {"logs": []}
        
    logs = []
    with open(log_file, "r") as f:
        # Get last 50 lines to keep the payload light and the chart responsive
        lines = f.readlines()[-50:]
        for line in lines:
            if not line.strip(): continue
            try:
                # Find the JSON part to avoid any leading timestamp/log level text
                json_start = line.find('{')
                if json_start != -1:
                    data = json.loads(line[json_start:])
                    logs.append(data)
            except:
                continue
    return {"logs": logs}

@api.post("/run_cycle")
async def run_cycle(req: AgentRequest):
    config = get_config(req.thread_id)
    try:
        # We pass None or empty state to trigger the Observer
        iterator = app.stream({"reasoning_log": []}, config=config)
        logs = parse_logs(iterator)
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api.get("/agent_state")
async def get_agent_state(thread_id: str = "demo_session_1"):
    """
    Checks if the agent is paused at the 'sentry' node for high-risk actions.
    """
    config = get_config(thread_id)
    snapshot = app.get_state(config)
    
    # Critical: Check for 'sentry' as defined in your agent.py
    if snapshot.next and "sentry" in snapshot.next:
        proposal_json = snapshot.values.get("decision_args")
        tool_name = snapshot.values.get("next_action") 
        
        return {
            "status": "WAITING_FOR_APPROVAL",
            "proposal": proposal_json,
            "tool": tool_name
        }
    
    return {"status": "IDLE", "proposal": None}

@api.post("/approve_action")
async def approve_action(req: ApprovalRequest):
    config = get_config(req.thread_id)
    
    if req.approved:
        # Resumes the stream from the 'sentry' interrupt point
        iterator = app.stream(None, config=config)
        logs = parse_logs(iterator)
        return {"status": "EXECUTED", "logs": logs}
    else:
        # Cancels and resets the next_action state
        app.update_state(config, {"next_action": "MONITOR"}) 
        return {"status": "REJECTED", "logs": ["Action cancelled by user."]}

if __name__ == "__main__":
    uvicorn.run(api, host="127.0.0.1", port=8000)
