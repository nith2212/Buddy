"""
echo.py
-------
Echo — Buddy's nightly reflection agent.

Echo is NOT Buddy. It never talks to the user directly.
It looks backward across 7-14 days of events and conversation history,
finds real patterns, and writes structured insights to shared memory.
Buddy reads that memory before every conversation. That's the only
channel between them — shared state, no direct communication.

Echo runs on a schedule (APScheduler cron, configured in main.py).
For development/testing, call run_echo() directly or hit POST /run-echo.

Architecture note:
  Buddy  — synchronous, per-message, in-the-moment
  Echo   — async, nightly, reflective, never user-facing

They share: the memory table (echo writes, buddy reads)
They don't share: code, prompts, call stacks, or conversation context
"""

import os
import json
from datetime import datetime, timedelta
from groq import Groq
from dotenv import load_dotenv
from tools import get_conn, update_memory, log_event

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# ── Echo's system prompt ──────────────────────────────────────────────────────
#
# Design principles baked into this prompt:
#
# 1. MINIMUM EVIDENCE: Echo must see something at least 3 times before
#    calling it a pattern. Single occurrences are noise, not signal.
#
# 2. HONEST DATA SUFFICIENCY: If there isn't enough data, Echo says so
#    explicitly via the data_sufficiency field. It never invents patterns
#    to fill a quota. "insufficient" is a valid and important output.
#
# 3. HYPOTHESIS FRAMING FOR BELIEFS: Beliefs about the user (echo.belief.*)
#    are stored as tentative observations with confidence scores, not flat
#    asserted facts. An LLM-inferred "belief" stated with false authority
#    is worse than no insight — it can calcify into a wrong, unchallenged
#    narrative about the user over time.
#
# 4. ONBOARDING AS WEAK PRIOR: Echo explicitly knows that onboarding.*
#    memory entries are self-reported at setup with confidence 0.3. Its
#    job is to confirm, refine, or contradict those priors with real data.
#
# 5. SOURCE TRANSPARENCY: Every insight Echo writes is tagged source='echo'
#    so Buddy knows the trust tier. Echo's entries carry the most weight
#    in the system — that's only justified if Echo is disciplined about
#    what it claims.

ECHO_SYSTEM_PROMPT = """You are Echo, a reflective analysis agent for an accountability companion called Buddy.

Your job: look backward across a user's recent behavioral data, find real patterns, and produce structured insights that Buddy can use to support the user better.

You NEVER talk to the user directly. Your output goes into Buddy's memory, which Buddy reads before every conversation. Write for Buddy, not for the user.

---

WHAT YOU HAVE ACCESS TO:
- events: everything observable (postponed, completed, progress_logged, emotion_picked, notification_sent, notification_ignored, checkin_responded, silence, conversation_turn, echo_ran)
- onboarding memory: what the user self-reported at setup (confidence 0.3 — treat as a weak starting hypothesis, not truth)

---

YOUR TWO JOBS:

1. BEHAVIORAL PATTERNS (echo.pattern.*)
   Falsifiable, data-backed observations about what actually happens.
   Examples:
     - "User completes tasks more often when they start before 8pm"
     - "User postpones tasks with vague titles more than tasks with specific ones"
     - "Notifications sent on weekday evenings get responded to within 30 minutes"

   Rules:
   - You must see something happen at least 3 times before calling it a pattern
   - State it as an observation, not a prediction ("tends to" not "will always")
   - If the data contradicts the onboarding entry for the same attribute, say so explicitly
   - If you don't have 3 occurrences, do not report it as a pattern — skip it

2. TENTATIVE BELIEFS (echo.belief.*)
   Softer, interpretive observations about how the user relates to their work.
   Examples:
     - "When user calls a task 'boring', they often complete it quickly once started"
     - "User tends to underestimate how long tasks take based on deadline proximity vs completion rate"
     - "User's emotion picks of 'unclear' correlate with tasks that have no defined first step"

   Rules:
   - Frame ALL beliefs as hypotheses, never as facts
   - Use language like: "tends to", "appears to", "may indicate", "worth watching"
   - Include what evidence supports it AND what would change it
   - Assign a confidence score: 0.4-0.6 for early observations, 0.6-0.8 for consistent patterns
   - Never go above 0.8 — that would claim more certainty than behavioral data can support

---

WHAT TO DO WITH ONBOARDING DATA:
The user answered some questions when they set up Buddy. Those answers are in memory with source='onboarding' and confidence=0.3. Your job is to evaluate them with real data:
- If behavior confirms the onboarding answer → write a pattern entry with higher confidence
- If behavior contradicts it → write a pattern entry that notes the contradiction explicitly
- If you don't have enough data to say either way → leave the onboarding entry alone, don't speculate

---

NOTIFICATION LEARNING (echo.notification.*):
Look at notification_sent vs checkin_responded / notification_ignored pairs.
If you see 3+ notifications at a given hour with consistent response rates, report:
  - best_hour: the hour (0-23) with highest response rate
  - best_variant: which copy style (if tracked in the note field) got the best response
  - response_rate: percentage of sent notifications that got a response
Only report these if you have at least 3 data points. Otherwise set data_sufficiency accordingly.

---

INTERVENTION EFFECTIVENESS (echo.intervention.*):
Look at what intervention Buddy used before the user's most engaged responses.
If a specific intervention (e.g. surface_smallest_step) consistently precedes a checkin_responded or progress_logged event, note it.
Format: "surface_smallest_step works well for overwhelm state" — state + intervention + outcome.
Again, minimum 3 occurrences.

---

DATA SUFFICIENCY:
You MUST report one of three values:
  "sufficient"    — 7+ days of meaningful events, patterns found with 3+ occurrences
  "limited"       — 3-6 days or sparse events, some patterns tentative
  "insufficient"  — less than 3 days or fewer than 5 events total

When data_sufficiency is "insufficient", return an empty insights array.
Do not invent patterns because the data is thin. An empty result is honest and useful.
Buddy can handle "Echo hasn't found anything yet" — it cannot handle false patterns.

---

OUTPUT FORMAT:
Respond ONLY with valid JSON. No preamble, no markdown, no explanation outside the JSON.

{
  "data_sufficiency": "sufficient" | "limited" | "insufficient",
  "days_analyzed": <int>,
  "event_count": <int>,
  "insights": [
    {
      "key": "echo.pattern.work_time",
      "value": "Completes tasks more often when starting before 8pm",
      "confidence": 0.72,
      "evidence": "4 of 5 completed tasks were started before 8pm across the last 10 days",
      "actionable_for_buddy": "Suggest starting tasks in the early evening if user is in avoidance or ambiguity state",
      "contradicts_onboarding": false
    },
    {
      "key": "echo.belief.self_language",
      "value": "When user describes a task as overwhelming, they often just need the first step named",
      "confidence": 0.58,
      "evidence": "3 instances where emotion_picked=overwhelmed was followed by surface_smallest_step and then progress_logged within 24 hours",
      "what_would_change_this": "If user picks overwhelmed and still doesn't act after first-step intervention",
      "actionable_for_buddy": "When emotion=overwhelmed, prioritize surface_smallest_step over name_the_pattern"
    },
    {
      "key": "echo.notification.best_hour",
      "value": "21",
      "confidence": 0.65,
      "evidence": "3 of 4 notifications sent at 9pm received a response within 1 hour",
      "actionable_for_buddy": "Schedule notifications at 9pm for this user"
    }
  ]
}

If there are no insights to report (data_sufficiency is insufficient, or patterns don't meet the 3-occurrence threshold), return:
{
  "data_sufficiency": "insufficient",
  "days_analyzed": <int>,
  "event_count": <int>,
  "insights": []
}
"""


# ── Data fetcher ──────────────────────────────────────────────────────────────

def fetch_echo_data(user_id: int, days: int = 14) -> dict:
    """
    Pull everything Echo needs from the DB for the last `days` days.
    Returns events, memory (current state), and a summary for the prompt.
    """
    conn = get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    events = conn.execute(
        """
        SELECT event_type, note, source, task_id, created_at
        FROM events
        WHERE user_id = ? AND created_at >= ?
        ORDER BY created_at ASC
        """,
        (user_id, cutoff),
    ).fetchall()

    memory = conn.execute(
        """
        SELECT key, value, confidence, source
        FROM memory
        WHERE user_id = ?
        ORDER BY confidence DESC
        """,
        (user_id,),
    ).fetchall()

    conn.close()

    return {
        "events":  [dict(e) for e in events],
        "memory":  [dict(m) for m in memory],
        "days":    days,
        "cutoff":  cutoff,
    }


def format_events_for_prompt(events: list) -> str:
    """
    Format events into a readable block for Echo's analysis prompt.
    Groups by day for easier pattern recognition.
    """
    if not events:
        return "No events found in the analysis window."

    lines = []
    current_day = None

    for e in events:
        # Extract date portion for day grouping
        try:
            dt = datetime.fromisoformat(e["created_at"])
            day_str = dt.strftime("%Y-%m-%d (%A)")
            hour    = dt.strftime("%H:%M")
        except Exception:
            day_str = "unknown date"
            hour    = "??:??"

        if day_str != current_day:
            lines.append(f"\n--- {day_str} ---")
            current_day = day_str

        note = f" | note: {e['note'][:80]}" if e.get("note") else ""
        lines.append(f"  {hour}  [{e['source']}]  {e['event_type']}{note}")

    return "\n".join(lines)


def format_memory_for_prompt(memory: list) -> str:
    """Format current memory state so Echo knows what's already been observed."""
    if not memory:
        return "No memory entries yet."
    lines = []
    for m in memory:
        lines.append(
            f"  {m['key']}: {m['value']} "
            f"(confidence: {m['confidence']:.2f}, source: {m['source']})"
        )
    return "\n".join(lines)


# ── Main Echo function ────────────────────────────────────────────────────────

def run_echo(user_id: int = 1) -> dict:
    """
    Run Echo's nightly analysis for a user.

    1. Fetches last 14 days of events + current memory state
    2. Calls Groq with Echo's system prompt
    3. Parses structured JSON response
    4. Writes valid insights to memory (source='echo')
    5. Logs an echo_ran event with a summary
    6. Returns the full Echo output dict

    Returns the Echo output dict regardless of whether insights were found.
    Caller (scheduler or /run-echo endpoint) can log or surface the result.
    """
    print(f"[Echo] Starting analysis for user {user_id}...")

    data          = fetch_echo_data(user_id, days=14)
    events        = data["events"]
    memory        = data["memory"]
    event_count   = len(events)

    events_text = format_events_for_prompt(events)
    memory_text = format_memory_for_prompt(memory)

    user_prompt = f"""Analyze the following behavioral data for a Buddy user.

CURRENT MEMORY STATE (what Buddy already knows about this user):
{memory_text}

EVENTS FROM THE LAST {data['days']} DAYS ({event_count} total events):
{events_text}

Apply your analysis rules strictly:
- Minimum 3 occurrences before calling anything a pattern
- Evaluate onboarding.* entries against real behavior
- Report data_sufficiency honestly
- Return only valid JSON, no markdown
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Echo is not in the critical path — slow/cheap is fine
            messages=[
                {"role": "system", "content": ECHO_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,  # Low temp — Echo should be analytical, not creative
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if model wraps output despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1].replace("json", "", 1).strip()

        result = json.loads(raw)

    except json.JSONDecodeError as e:
        print(f"[Echo] JSON parse failed: {e}")
        result = {
            "data_sufficiency": "insufficient",
            "days_analyzed":    data["days"],
            "event_count":      event_count,
            "insights":         [],
            "error":            f"JSON parse failed: {e}",
        }
    except Exception as e:
        print(f"[Echo] Groq call failed: {e}")
        result = {
            "data_sufficiency": "insufficient",
            "days_analyzed":    data["days"],
            "event_count":      event_count,
            "insights":         [],
            "error":            f"Groq call failed: {e}",
        }

    # Write valid insights to memory
    insights_written = 0
    if result.get("data_sufficiency") != "insufficient":
        for insight in result.get("insights", []):
            key        = insight.get("key")
            value      = insight.get("value")
            confidence = insight.get("confidence", 0.5)

            # Validate key namespace — Echo should only write echo.* keys
            if not key or not key.startswith("echo."):
                print(f"[Echo] Skipping invalid key: {key}")
                continue

            if not value:
                continue

            update_memory(
                user_id=user_id,
                key=key,
                value=value,
                confidence=float(confidence),
                source="echo",
            )
            insights_written += 1

    # Log that Echo ran — this is how Buddy and future Echo runs know when it last fired
    summary = (
        f"data_sufficiency={result.get('data_sufficiency')}, "
        f"{event_count} events analyzed, "
        f"{insights_written} insights written"
    )
    if result.get("error"):
        summary += f", error: {result['error']}"

    log_event(
        user_id=user_id,
        event_type="echo_ran",
        note=summary,
        task_id=None,
        source="system",
    )

    print(f"[Echo] Done. {summary}")
    result["insights_written"] = insights_written
    return result