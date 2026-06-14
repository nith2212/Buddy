"""
main.py
-------
FastAPI application — REST API layer for the Buddy accountability companion.

Endpoints:
  GET  /                          health check
  GET  /task/{task_id}            fetch task + full event history
  GET  /memory/{user_id}          fetch all agent memory for a user
  GET  /conversation/{user_id}    fetch recent conversation turns
  GET  /reasoning-history/{user_id} fetch all stored reasoning snapshots
  POST /chat                      send a user message, get agent reply
  POST /initiate                  agent speaks first (no user message)
  POST /event                     log a task event manually
  POST /simulate-next-day         dev tool: simulate a missed day + proactive check-in
  POST /complete-task             mark task as completed (no celebration message)
  POST /celebrate                 mark task complete + trigger celebration reply
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import run_agent
from database import init_db
from tools import (
    get_task_history, get_user_memory,
    get_conversation_history, save_conversation_turn,
    log_event, update_memory,
    get_reasoning_history, complete_task,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


# ── Read endpoints ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "Accountability Companion API running"}

@app.get("/task/{task_id}")
def task_detail(task_id: int):
    return get_task_history(task_id)

@app.get("/memory/{user_id}")
def memory(user_id: int):
    return get_user_memory(user_id)

@app.get("/conversation/{user_id}")
def conversation(user_id: int):
    return get_conversation_history(user_id)

@app.get("/reasoning-history/{user_id}")
def reasoning_history(user_id: int):
    return get_reasoning_history(user_id)


# ── Chat endpoints ────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    user_id: int
    task_id: int
    message: str

@app.post("/chat")
def chat(body: ChatMessage):
    """User sends a message; agent responds."""
    return run_agent(body.user_id, body.task_id, body.message)


class InitiateRequest(BaseModel):
    user_id: int
    task_id: int

@app.post("/initiate")
def initiate(body: InitiateRequest):
    """Agent speaks first — used on initial load of the chat screen."""
    return run_agent(body.user_id, body.task_id, "")


# ── Event logging ─────────────────────────────────────────────────────────────

class EventLog(BaseModel):
    task_id: int
    event_type: str
    note: str = None
    user_response_text: str = None
    detected_state: str = None

@app.post("/event")
def event(body: EventLog):
    """Manually log a task event (e.g. postponed, check-in)."""
    log_event(body.task_id, body.event_type, body.note, body.user_response_text, body.detected_state)
    return {"status": "logged"}


# ── Dev / simulation endpoints ────────────────────────────────────────────────

@app.post("/simulate-next-day")
def simulate_next_day():
    """
    Dev tool: simulates a day passing with no user activity.
    Logs a missed_checkin event, then triggers a proactive agent check-in.
    """
    log_event(
        task_id=1,
        event_type="missed_checkin",
        note="User said they'd spend 1 hour studying. No activity recorded.",
        detected_state="avoidance",
    )
    return run_agent(user_id=1, task_id=1, user_message="")


# ── Task completion endpoints ─────────────────────────────────────────────────

class CompleteRequest(BaseModel):
    task_id: int

@app.post("/complete-task")
def complete(body: CompleteRequest):
    """Mark a task as completed without generating a celebration message."""
    complete_task(body.task_id)
    return {"status": "completed"}

@app.post("/celebrate")
def celebrate(body: CompleteRequest):
    """Mark task complete and generate a specific, warm celebration reply from Buddy."""
    complete_task(body.task_id)
    return run_agent(
        user_id=1,
        task_id=body.task_id,
        user_message=(
            "[System: The user just marked this task as complete. "
            "Celebrate this specifically and warmly — reference what "
            "they pushed through to get here based on the task history. "
            "Keep it short, one or two sentences, genuinely warm.]"
        ),
    )
