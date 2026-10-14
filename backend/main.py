"""
main.py
-------
FastAPI application — REST API layer for the Buddy accountability companion.

Endpoints:
  GET  /                            health check
  GET  /task/{task_id}              fetch task + full event history
  GET  /memory/{user_id}            fetch all agent memory for a user
  GET  /conversation/{user_id}      fetch recent conversation turns
  GET  /reasoning-history/{user_id} fetch all stored reasoning snapshots
  POST /chat                        send a user message, get agent reply
  POST /initiate                    agent speaks first (no user message)
  POST /event                       log a task event manually
  POST /simulate-next-day           dev tool: simulate a missed day + proactive check-in
  POST /complete-task               mark task as completed (no celebration message)
  POST /celebrate                   mark task complete + trigger celebration reply
  POST /emotion-pick                user taps emotion from notification picker → hook response
  POST /later                       user taps LATER on notification → logs postponed + emotion
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import run_agent, generate_hook
from database import init_db, get_conn
from echo import run_echo
from tools import (
    get_task_history, get_user_memory,
    get_conversation_history, save_conversation_turn,
    log_event, update_memory,
    get_reasoning_history, complete_task,
    log_emotion_pick,
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
    from rag import _get_model, _get_client
    _get_model()
    _get_client()


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


# ── Task endpoints ───────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    user_id:  int
    title:    str
    deadline: str | None = None

@app.post("/task")
def create_task(body: TaskRequest):
    """Create a new task. Returns the full task row including the new task_id."""
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO tasks (user_id, title, deadline, status) VALUES (?, ?, ?, 'active')",
        (body.user_id, body.title, body.deadline),
    )
    task_id = cursor.lastrowid
    conn.commit()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(task)


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


# ── Onboarding ────────────────────────────────────────────────────────────────

class OnboardingRequest(BaseModel):
    user_id: int
    preferred_work_time: str
    work_session_style: str
    procrastination_style: str
    notification_opted_in: bool

@app.post("/onboarding")
def onboarding(body: OnboardingRequest):
    """
    Write the onboarding row and seed initial memory entries at confidence=0.3,
    source='onboarding' — lowest-trust tier. Echo overwrites these with real
    behavioral observations as soon as it has enough data.
    """
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO onboarding
            (user_id, preferred_work_time, work_session_style,
             procrastination_style, notification_opted_in)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            body.user_id,
            body.preferred_work_time,
            body.work_session_style,
            body.procrastination_style,
            1 if body.notification_opted_in else 0,
        ),
    )
    conn.commit()
    conn.close()

    seeds = [
        ("onboarding.work_time",            body.preferred_work_time),
        ("onboarding.session_style",         body.work_session_style),
        ("onboarding.procrastination_style", body.procrastination_style),
        ("onboarding.notification_opted_in", str(body.notification_opted_in).lower()),
    ]
    for key, value in seeds:
        update_memory(body.user_id, key, value, confidence=0.3, source="onboarding")

    return {"status": "onboarding complete", "memory_seeded": len(seeds)}


# ── Emotion picker endpoints ──────────────────────────────────────────────────

class EmotionPickRequest(BaseModel):
    user_id: int
    task_id: int
    emotion: str  # "overwhelmed" | "tired" | "unclear" | "bored" | "anxious"

@app.post("/emotion-pick")
def emotion_pick(body: EmotionPickRequest):
    """
    User taps an emotion from the notification picker.

    Flow:
    1. Logs emotion_picked event (source='user' — highest trust signal)
    2. Runs agent with the emotion as context to generate a hook response
       (something that makes the user want to open chat, not a full conversation)

    Returns: {"reply": str, "reasoning": dict}
    The reply is the hook — short, specific, makes the user curious to go deeper.
    """
    # Log the emotion pick as a user self-report
    log_emotion_pick(
        user_id=body.user_id,
        emotion=body.emotion,
        task_id=body.task_id,
    )
    return generate_hook(body.user_id, body.task_id, body.emotion)


class LaterRequest(BaseModel):
    user_id: int
    task_id: int
    emotion: str  # the emotion they had already picked before tapping LATER

@app.post("/later")
def later(body: LaterRequest):
    """
    User taps LATER after seeing the hook — they're aware of the emotion,
    still choosing to delay. Logs both the emotion (if not already logged)
    and a postponed event with the emotion as context so Echo can see:
    "user identified they were overwhelmed AND still postponed."

    This is a richer signal than a plain postpone — it tells Echo the user
    has self-awareness but still couldn't act, which is avoidance, not ambiguity.

    Returns: {"status": "logged"} — no agent response, Buddy respects the LATER.
    """
    log_event(
        user_id=body.user_id,
        event_type="postponed",
        note=f"User tapped LATER after picking emotion: {body.emotion}",
        task_id=body.task_id,
        source="user",
    )
    return {"status": "logged"}


# ── Event logging ─────────────────────────────────────────────────────────────

class EventLog(BaseModel):
    user_id: int
    event_type: str
    note: str = None
    task_id: int = None

@app.post("/event")
def event(body: EventLog):
    """Manually log a task event."""
    log_event(
        user_id=body.user_id,
        event_type=body.event_type,
        note=body.note,
        task_id=body.task_id,
    )
    return {"status": "logged"}


# ── Dev / simulation endpoints ────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    task_id: int = 1

@app.post("/simulate-next-day")
def simulate_next_day(body: SimulateRequest):
    """
    Dev tool: simulates a day passing with no user activity.
    Logs a checkin_initiated event, then triggers a proactive agent check-in.
    """
    log_event(
        user_id=1,
        event_type="checkin_initiated",
        note="User said they'd work on the task. No activity recorded.",
        task_id=body.task_id,
        source="system",
    )
    return run_agent(user_id=1, task_id=body.task_id, user_message="")


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

class RunEchoRequest(BaseModel):
    user_id: int = 1  # defaults to 1 for single-user demo


@app.post("/run-echo")
def trigger_echo(body: RunEchoRequest):
    """
    Manually trigger Echo's nightly analysis.

    In production this fires via APScheduler cron (configured separately).
    During development, call this endpoint to test Echo without waiting for midnight.

    Returns Echo's full output — data_sufficiency, insights found,
    how many were written to memory, and any errors encountered.
    """
    result = run_echo(user_id=body.user_id)
    return result


# ── LATER: APScheduler cron (add in Week 2 once Echo is tested) ──────────────
#
# from apscheduler.schedulers.background import BackgroundScheduler
#
# scheduler = BackgroundScheduler()
#
# @app.on_event("startup")
# def start_scheduler():
#     scheduler.add_job(
#         func=lambda: run_echo(user_id=1),
#         trigger="cron",
#         hour=2,          # 2am — user is asleep, Echo runs quietly
#         minute=0,
#         id="echo_nightly",
#         replace_existing=True,
#     )
#     scheduler.start()
#
# @app.on_event("shutdown")
# def stop_scheduler():
#     scheduler.shutdown()
#
# pip install apscheduler    