"""
seed.py
-------
Wipes and re-seeds the database with a realistic demo scenario.

Scenario:
  - User "Nith" has been trying to study for the AWS CCP exam for 3 days
  - The task has been postponed twice (fatigue, then overwhelm)
  - Agent memory reflects what Buddy has "learned" about the user

Run this before demoing to reset to a clean, meaningful starting state:
  python seed.py
"""

from database import get_conn, init_db
from datetime import datetime, timedelta


def seed():
    init_db()
    conn = get_conn()
    c    = conn.cursor()

    # Wipe all existing data
    c.execute("DELETE FROM conversations")
    c.execute("DELETE FROM agent_memory")
    c.execute("DELETE FROM task_events")
    c.execute("DELETE FROM tasks")
    c.execute("DELETE FROM users")

    now          = datetime.now()
    two_days_ago = (now - timedelta(days=2)).isoformat()
    yesterday    = (now - timedelta(days=1)).isoformat()

    # User
    c.execute(
        "INSERT INTO users (id, name, created_at) VALUES (1, 'Nith', ?)",
        (two_days_ago,),
    )

    # Task — AWS exam study, due in 3 days from now
    c.execute(
        """
        INSERT INTO tasks (id, user_id, title, status, created_at, due_at)
        VALUES (1, 1, 'Study for AWS CCP exam', 'pending', ?, ?)
        """,
        (two_days_ago, (now + timedelta(days=3)).isoformat()),
    )

    # Event log — two postponements to set up avoidance pattern
    c.execute(
        """
        INSERT INTO task_events (task_id, event_type, note, detected_state, created_at)
        VALUES (1, 'postponed', 'Said he was tired, would do it tomorrow', 'fatigue', ?)
        """,
        (two_days_ago,),
    )
    c.execute(
        """
        INSERT INTO task_events
            (task_id, event_type, note, user_response_text, detected_state, created_at)
        VALUES (1, 'postponed', 'Felt overwhelmed by the billing section',
                'too much to cover, feels overwhelming', 'overwhelm', ?)
        """,
        (yesterday,),
    )

    # Agent memory — pre-loaded "learned" user preferences and patterns
    memories = [
        ("best_work_time",       "evenings, typically after 8pm"),
        ("common_obstacle",      "overwhelm when scope feels large"),
        ("encouragement_style",  "responds well to breaking tasks into smaller steps"),
        ("avoidance_pattern",    "tends to postpone learning tasks when tired"),
        ("streak_current",       "0"),
        ("streak_best",          "3"),
    ]
    for key, value in memories:
        c.execute(
            """
            INSERT INTO agent_memory (user_id, memory_key, memory_value, updated_at)
            VALUES (1, ?, ?, ?)
            """,
            (key, value, two_days_ago),
        )

    conn.commit()
    conn.close()
    print("Seeded successfully.")


if __name__ == "__main__":
    seed()
