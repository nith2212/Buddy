# How Buddy works, end to end

Status as of 2026-11-05. Written so another assistant (or a new developer) can understand the whole system. Code paths are
relative to the repo root.

## 1. The product

Buddy is a mobile companion for procrastination. Most to-do apps track the task; Buddy tracks the person.
When someone is avoiding a task, Buddy doesn't say "just start". It works out **why** they're stuck,
helps with that specific cause, and remembers the cause so it can notice patterns over time.

The five causes (the user taps one, or reveals one while chatting):

| Tap (user-facing) | Internal reason | State / framework |
|---|---|---|
| Don't know where to start | `unclear` | `ambiguity` |
| Feels too big | `too_much` | `overwhelm` |
| Scared it won't be good enough | `afraid` | `perfectionism` |
| Boring or pointless | `bored` | `low_interest` |
| Too tired | `tired` | `fatigue` |

**Voice.** The developer's own voice: a sweet, peppy, kind friend who gets genuinely excited about the user's
goals. Short and warm, never judgmental. Never shames, lectures, moralizes or optimizes. Excitement only for
something real the user said or did. No therapy phrases ("I hear you", "it's okay to feel...", "totally
understandable/valid"). No promises, no pressure ("relax", "buckle up").

**Core principles.**
1. Root cause first, advice second. Diagnose before suggesting.
2. Proactive: Buddy reaches out first (check-in notifications), and silence is data.
3. Work states only, never a mental-health diagnosis. If something bigger than work comes up, Buddy steps
   back honestly (it's a task companion, not the right support), points to someone they trust or a local
   helpline, and stops probing.
4. It remembers confirmed causes per person and mentions a pattern only when earned (3+ confirmations),
   softly, never with a number.
5. Buddy **offers**, never assigns. When the user has their own plan, Buddy backs it exactly as they said it.

**Who it's for right now.** An invite-only build used by the developer and testers. It's a portfolio and
interview project with a hard stop on Nov 11, 2026. No Play Store yet.

## 2. Architecture

```
Android app (Expo SDK 57, React Native, expo-router)
   │  HTTPS, Bearer token
   ▼
FastAPI backend on Render (free tier: sleeps when idle, ephemeral disk)
   │                      │                          │
   ▼                      ▼                          ▼
Neon Postgres       LLM provider               Expo push service → FCM → phone
(SQLite locally)    (Claude Haiku 5.5 now;
                     Groq models also supported)
   ▲
cron-job.org calls POST /cron/checkins hourly and POST /cron/echo weekly (secret header)
```

- No in-process schedulers: Render free sleeps, so every scheduled job is an HTTP call from cron-job.org.
  Each job runs twice a few minutes apart (the first call may only wake Render). Both jobs are idempotent.
- LLM calls are async, with timeouts, retries and a canned fallback reply. A model failure never returns
  a 500. No DB session is held while waiting on the model.
- **Model:** one setting, `GROQ_MODEL` (the name is historical). A `claude-...` value routes to Anthropic's
  official SDK; anything else goes to Groq's OpenAI-compatible API. Currently `claude-haiku-5-5`: no
  temperature, thinking disabled, structured JSON output for the reader call. A full eval run costs about
  INR 1. Earlier models: gpt-oss-20b on Groq free tier (weak at following the frameworks, see section 9).

## 3. Data model (every table has `user_id`)

- **User**: id (uuid), token_hash, timezone. No accounts or passwords: `POST /auth/anonymous` with an
  invite code returns a token. Identity comes **only** from the Bearer token.
- **Task**: title, due_date (optional), status (open/done), task_state (from the notification:
  not_started/in_progress/done), created/updated/completed_at.
- **Subtask** ("steps"): title, done, position.
- **EmotionLog**: one row per reason tap (from the notification or in-app chips), plus chat opt-in.
- **Event**: system/user events such as `checkin_sent` and `postponed` (due date moved later). Payload is JSON.
- **Message**: the chat history per task. Assistant rows store a JSON `reasoning` blob (state, stage,
  tries, notes, what the reader concluded, checks, fallback) so the next turn can continue the stage machine.
- **Memory**: key/value per user:
  - `blocker.task.<id>` = the confirmed cause for that task
  - `pattern.blocker.<cause>` = how many times that cause has been confirmed
  - `buddy.*` bookkeeping
  - `echo.week.<date>` = Echo's weekly facts (source `echo`)
- **DeviceToken**: the Expo push token.
- **Onboarding**: exists in the schema; onboarding itself is parked.

Privacy rules: every query is scoped to the caller, and another user's row returns 404 (isolation tests
cover every table). `DELETE /me` wipes everything, including causes and Echo. Secrets live only in env
vars. Message content is never logged. Chat text goes to the model provider (developer approved).

## 4. API

| Route | What it does |
|---|---|
| `POST /auth/anonymous` | Invite code → user + token |
| `POST/GET /tasks`, `GET/PATCH /tasks/{id}` | Task CRUD (no task delete yet); PATCH logs `postponed` when due_date moves later |
| `POST/PATCH/DELETE /tasks/{id}/subtasks[/{sid}]` | Steps |
| `POST /chat` | `{task_id, message?, reason?}`. A reason writes an EmotionLog first. With no message, Buddy speaks first. The reply has `ask_reason: true` when Buddy asked what's in the way (the app then shows the reason chips) |
| `POST /initiate` | Buddy opens the chat (used after "Yes, let's chat" on a notification) |
| `GET /chat/history` | Messages for one task |
| `POST /devices/register` | Save the Expo push token |
| `POST /checkin/action` | Notification button taps; drives the check-in stages |
| `POST /cron/checkins` | Hourly: picks tasks and sends check-ins |
| `POST /cron/echo` | Weekly: saves Echo facts for every user with tasks |
| `GET /echo/week` | The Echoes page: this week (live) and last week (saved), kind data only |
| `DELETE /me` | Wipe the account |

## 5. The user journey

**In the app** (hand-drawn design, the white "dumpling" Buddy mascot; files in `src/`)
- **Loading screen:** Buddy floating, "Waking Buddy up…" while the free-tier server wakes.
- **Home:** the task list. Add a task with an optional due date (preset options, no date picker), tick done.
- **Menu** (slides in): Tasks, Chat with Buddy, Echoes, Delete my data.
- **A task's own chat:** due date, a folding steps strip, the task's whole conversation.
  - No chat yet: "What's in the way?" with **five reason buttons**. Tapping one sends `POST /chat {reason}`,
    and Buddy opens the conversation for that cause.
  - Typing without a tap: Buddy reacts and asks what's in the way, and the chips appear under its reply.
  - "stuck again? tell Buddy why" reopens the chips once a chat exists.
- **Chat with Buddy:** "Which task do you need help starting?", then that task's own chat.
- **Echoes:** the weekly report (section 11).

**Proactive check-ins**
1. Every hour, `/cron/checkins` picks **at most one task per user**: an open task that is due within 24h,
   or has never been answered (no task_state) and is 24h+ old, and hasn't had a check-in in the last 20h.
   The most urgent (earliest due) goes first.
2. Push notification: "Daily Check-in 🌟 — How's “<task title>” going today?" Buttons: **Not started / In
   progress / Done**.
3. Tap → the backend saves task_state → a new notification: "How are you feeling?" Buttons: **😴 Tired /
   😤 Too much / 🤷 Don't know where to start**. Android allows only 3 buttons, so "scared" and "boring" are
   in-app chips only.
4. Tap → EmotionLog → "Want to talk about it?" **Yes, let's chat / No thanks**.
   - **Yes:** the app opens that task's chat and calls `/initiate`. Buddy opens with the framework for the
     tapped reason.
   - **No:** Buddy writes one short tailored closing notification (old pipeline, no question).

## 6. The conversation engine (the heart of it)

Design principle: **code decides the conversation's stage; the model only words the reply.** Small models
ignored prompt rules (handing out steps, repeating openers, shrinking the user's plan), so the structure
moved into code.

### 6.1 Which path runs
`run_turn` in `backend/brain/agent.py`:
- If a reason was tapped in the last 24h for this task → the **framework path** (`_flow_turn`), described below.
- A typed message with no recent tap (and not "thanks", not a finished task) → **ask the reason**
  (`_ask_reason_turn`): one reply that reacts and asks what's in the way, and the app shows the chips.
  Something bigger than work gets the step-back instead. If they type again instead of tapping, the next
  reply uses the generic path, so Buddy never asks twice in a row.
- Otherwise → the **older generic path**:
  - State detection: done → recovery; tapped → that state; 2+ ignored check-ins in a row →
    `avoidance`/`commitment_drift`.
  - Pick an intervention from the playbook docs (one "decide" LLM call), write the reply (one LLM call),
    then run the same reply checks.
  - The closing notification always uses this path.

### 6.2 Framework path, per user message
1. **Load** this session's messages (since the tap), the last stage, tries and notes (from the last
   assistant message's `reasoning`), the task, its steps, and at most one context line (section 7).
2. **Read the user's message** (`flow.read_message`):
   - First, cheap patterns with no model call:
     - distress words → `bigger`
     - clear tiredness words ("exhausted", "drained") → switch to fatigue
     - pure acks/sign-offs ("ok thanks bye") → `ack`
     - "idk"-style → `idk`
   - Otherwise, one small structured-JSON model call. It returns `kind`, plus `cause`, `flavor` and `fact`
     (their key point in their own words).
   - Kinds: `idk`, `answer`, `confirm`, `reject`, `unsure`, `own_plan` (their own action, including
     dropping/postponing the task), `accept` (agrees to the step Buddy offered), `wants_move`, `ack`,
     `new_cause` (a different reason), `bigger`.
   - A failed read becomes `unclear`: stay on the stage and re-ask in simpler words.
3. **Move the stage** with a fixed table (`flow.next_stage`). Rules that apply in every framework:
   - `bigger` → step_back (sticky for the session).
   - `new_cause` → switch to that cause's framework and save that cause.
   - `ack`/`own_plan`/`accept` → **release** (wrap up). `own_plan` adds a note "their plan: <their words>"
     so the wrap-up backs it exactly. `accept` wraps up without crediting them ("it was Buddy's idea").
   - Staying on the same stage gets reworded (idk → offer two concrete options; unsure → something more
     specific; no → a different option). After 2 tries on one stage, Buddy asks the **offer** question
     instead: "Want a tiny first move from me, or do you already know what you'll do?"
   - After release, anything else → **followup** (respond briefly; if corrected, agree in a few words; no
     new step unless they ask).
4. **Write** the reply. The writer prompt contains:
   - the voice
   - the facts (task, timing only on the first message, open steps, done steps — the only progress that may
     be praised — the tapped reason, "known so far" notes in their words)
   - the stage's instruction card and modifier, and the framework's "Never" list
   - rules: at most 3 sentences, exactly one question or none depending on the stage, no invented
     facts/times, step back if something bigger comes up

   Wording lives in Markdown docs (`backend/brain/buddy_docs/framework_*.md`), which the developer reviews.
5. **Check** the reply mechanically (`reply_check.py`), with one rewrite if it fails:
   - Hard bans: therapy phrases, promises, pressure, moralizing ("you don't have to like it", "still has
     to get done"), invented clock times. If still broken → canned fallback reply.
   - Soft flags: too long, too many questions, missing question, repeats the previous reply or opener, an
     invented resource ("watch a tutorial"), label-style openers, offer/guess shape.
6. **Learn**, in one transaction: save both messages, the reasoning blob, and the cause if this stage
   confirms it.

### 6.3 The five frameworks (stages in order)
- **Don't know where to start (ambiguity), "scaffold":** open (what does done look like?) → core (the one
  part everything depends on) → first_step (*their* first step) → release. Naming a part after the offer
  ("maybe the swipe thing?") goes to first_step. Buddy never supplies the content. Cause saved when they
  name their own plan.
- **Feels too big (overwhelm):** open (the smallest, even silliest first move?) → micro (Buddy offers ONE
  micro-step as "what about...?"; "that's all?" → "yes, that's all") → release. Never a second step.
- **Scared it won't be good enough (perfectionism), "diagnose":** open (what feels risky?) → narrow (two
  guesses as one question) / confirm ("is that it?") → reframe (a deliberately rough first version nobody
  sees) → release. Reframe declined → the offer. Cause saved when they confirm.
- **Boring or pointless (low_interest):**
  - open: does it need doing at all? (If optional, dropping it is their call.)
  - narrow: more boring, or more pointless?
  - boring → lighten: two lighter options (timer + reward, music, pair it with something fun, bare minimum).
  - pointless → purpose: *ask* whether it gives them anything.
    - They find a reason → own_reason (name it as theirs, lightly) → release.
    - None or no → lighten.

  Never persuades or moralizes.
- **Too tired (fatigue), "release":**
  - open: how was your day?
  - rest: permission to stop, no question, no task push.
  - If they still want to work: the offer → one tiny move small enough for a tired brain.

## 7. Memory and patterns
- A cause is saved **only when the user confirms it**. It writes `blocker.task.<id>` and increments
  `pattern.blocker.<cause>`.
- The writer gets **at most one context line**:
  - **Echo's cue** wins if this task has been neglected: "Context, never mention it: be extra gentle".
  - Else the **pattern line**, once a cause has 3+ confirmations: "may mention it once, softly, never a
    number".
- Raw memory rows about causes are never shown to the writer.

## 8. Echo (weekly learning)
Echo is the "Buddy knows *you*" layer. Built in steps:

- **E1, built:** every Sunday 23:00 India time, `/cron/echo` counts each user's week in code (no model
  call, so nothing can be invented). Runs for anyone with at least one task, including ignored tasks;
  skips users with no tasks. It counts:
  - causes confirmed this week, and totals
  - reasons tapped
  - tasks finished and steps done
  - per open task: days untouched, check-ins sent and **ignored** (no tap, chat or step within 12h),
    and times postponed

  Saved as `echo.week.<date>`; the last 8 weeks are kept, and the data is stale after 8 days. Buddy only
  gets the "go gentle" cue (task untouched 5+ days or 2+ ignored check-ins), never the numbers. **Buddy
  must never say Echo's facts.** A local text report exists for dev (`testing/echo_report.py`).
- **E2, built (2026-11-05):** count how the user reacts to Buddy's moves: which offered moves they accept or decline
  (rough version, tiny move, lighter way), whether they bring their own plan, which notification buttons
  they tap or ignore, and whether progress follows a chat within a day. Counted and reported only.
- **E3, built (2026-11-05):** four developer-approved adaptation rules (own plan first, straight to Buddy's move, lean on what helped (said softly), avoid what they decline) that fire only after something has
  happened 3+ times. Example: always brings their own plan → skip the offer and ask what they'll do. No
  automatic optimization (a bandit is parked).
- **The user's Echoes page:** see section 11.

## 9. Testing and quality
- **Unit tests:** 359, all green, with a fake model. They cover user isolation, the stage tables walked
  through the developer's "dream conversations", reply checks, Echo, cron and the Anthropic adapter.
- **Evals** (`testing/`): 17 scripted conversations (3 per chip, plus 2 from phone tests) run through the
  real app against the real model. Mechanical flags plus **hand-grading** on 7 criteria:
  1. follows the framework
  2. reacts to the user
  3. offers, doesn't assign
  4. no premature step
  5. keeps their plan
  6. warm voice
  7. no invention

  A separate read eval checks the reader on about 100 labeled messages.
- **Results** ("follows the framework", hand-graded):

  | Version | Follows the framework | Warm voice | Notes |
  |---|---|---|---|
  | Old Buddy, gpt-oss-20b | 17/69 (25%) | 10/69 | |
  | New engine on gpt-oss-20b | ~85% on the chips tested | | |
  | **New engine on Claude Haiku 5.5** | **59/69 (86%)** | 62/69 | kept their plan 18/18, 0 fallbacks, read eval 91% right route |

- **Phone test** (2026-11-04, Haiku): replies under 5s, no fallbacks, 6 of 8 chats clean. Two bugs found and
  fixed the same night:
  - Buddy credited the user with Buddy's own suggestion.
  - The boring chip persuaded ("you don't have to like it", "it builds your manager's trust").
- **Known remaining weak spots:**
  - The boring chip is still the weakest.
  - Occasionally a 4-sentence opener, or a question tacked on after a step.
  - Grading is Claude grading Claude (the developer spot-checks).

## 10. Constraints and what's parked
- **Timeline:** wrap up by Wed Nov 11 (Nov 7-8 off). Built: E2, E3, the new UI and the Echoes page.
  Remaining: the developer's phone testing, minor task CRUD (edit/delete), final test, ship.
- **Hosting:** Render free + Neon + cron-job.org; Expo push; no second deployment.
- **Parked on purpose** (don't build): sprint timer, check-back commitments, firmness levels, escalation,
  onboarding, a date picker, bandit, notes UI, multi-agent split, monthly reflections, accounts/passwords,
  web frontend, Play Store.
- **Later:**
  - Exact citations for the playbook's psychology claims.
  - Possibly LoRA fine-tuning a small open model on Buddy's own conversations, only after the eval exists to
    measure it.

## 11. The Echoes page (built)
A friend telling you what they noticed, never a report card. All user-facing text comes from code
templates (`brain/echo.py`), not free model text, so nothing is invented.

- **This week** (live, since Sunday 23:00 India time):
  - wins: tasks finished, steps ticked, "got going N times when it felt hard"
  - seven dots, one per day you touched any task; an up-only "shown up N days since you started"
  - one Buddy line built from the week
  - in the very first week: "Your first Echo lands on Monday!"
- **Last week** (from the Sunday save): the same wins, dots and line. The page opens on it Monday to
  Wednesday, and it can be saved or shared as plain text through the phone's share sheet.
- **What helped:** only for causes confirmed 3+ times, e.g. "Worrying it won't be good enough has come up
  a few times. A rough first version helped you get going twice."
- **Never shown:** ignored check-ins, days untouched, postpone counts, comparisons, percentages.
- "Talk to buddy about my week" opens the task picker for now; a reflection chat is planned.
