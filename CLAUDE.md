@AGENTS.md

# Buddy

## The product (read this first)
Buddy helps you START by finding out WHY you're stuck.
Other apps track the task. Buddy tracks the human. When someone is avoiding a task, Buddy doesn't say "just start". It finds the real cause (not knowing where to start, it feels too big, fear of doing it badly, boredom, tiredness), helps with that specific cause, and remembers it so it can show the pattern over time ("this is the third time fear of doing it badly stopped you").

Tone: Baymax. Calm, short, warm, non-judgmental. Never shames, lectures, optimizes or cheerleads.

If a request conflicts with this section, STOP and ask.

## What makes it different
1. Root cause first, advice second. Buddy diagnoses before it suggests.
2. Proactive. Buddy reaches out first, from task activity, idle time and ignored check-ins. Silence is data.
3. Work states only, never mental-health diagnosis. If a chat reveals something bigger than work, Buddy steps back honestly and does not keep probing.
4. Remembers causes per person and surfaces patterns (softly, and only when earned).
5. Checks its own playbook (buddy_docs/) before choosing how to respond.

## How a conversation goes
1. User taps a rough reason (notification buttons or in-app chips): don't know where to start / feels too big / scared it won't be good enough / boring or pointless / too tired.
2. Buddy reflects what they tapped, then asks ONE specific question to find the real cause.
3. Buddy offers its guess as a QUESTION, never as a fact or label.
4. Only after the cause is confirmed, Buddy suggests ONE tiny first move matched to that cause.
5. Short acknowledgments ("okay thanks") get a brief affirm-and-release. No new instructions, no new question.

## Reply rules (enforced by reply_check, do not weaken)
- 2-3 short sentences. At most one question. One concrete next move.
- No stock empathy ("That sounds exhausting", "It's totally understandable").
- Name the task or a step in Buddy's first message of a conversation. Later replies respond to what the user said and needn't restate it.
- Praise only for something the person actually did.
- Never invent deadlines or clock times. Only the task's real due_date.
- Respect what the user said. If they say they need to finish, help with the smallest piece. Don't talk them out of it.
- Firm about the plan, never about the person.

## Memory of causes
- Save a cause only when the user CONFIRMS it. If they say "no, not really", it is not counted.
- Keys: blocker.task.<id> and pattern.blocker.<reason>, written in the same transaction as the turn.
- Mention a pattern only when a cause has been confirmed 3+ times, softly ("this has come up a few times"). Never invent counts.
- Inject at most one capped line of top pattern into the situation text.

## Build plan (hard stop: Nov 8, then testing and study)
Already shipped: auth, tasks and steps, chat, push notifications with 3 buttons, deploy on Render + Neon. Unfinished: weekly Echo.
Steps, each shippable alone, tested and committed before the next:
- A. Playbook docs in backend/brain/buddy_docs/: state_perfectionism.md, state_low_interest.md, intervention_find_the_cause.md, intervention_affirm_and_release.md, plus a cause-to-first-move mapping in intervention_surface_smallest_step.md. The OWNER reviews the wording. Do not finalize it without her.
- B. Reasons become states: extend EMOTION_TO_STATE; accept the new reason values in the notification route and log_emotion_pick; add an optional explicit `reason` field to ChatRequest (never an in-band control string).
- C. Diagnose behavior in run_turn: tapped reason with few chat turns forces find_the_cause; after the answer, pick the matched first move; short acknowledgments force affirm_and_release and skip the decide call (Groq is capped at about 8k tokens/min). Write memory in _learn.
- D. Mobile: reason chips when the chat is empty (src/app/task/[id].tsx, src/lib/api.ts). Notification buttons stay at 3 because of the Android limit: tired / too much / don't know where to start. Fear and boredom are in-app chips only.
- E. Finish weekly Echo: per user, minimum-events threshold, manual trigger, summarizes pattern.* memory. It runs from cron, protected by X-Cron-Secret.

## Parked (do NOT build or propose; add to a "later" list instead)
Sprint timer, check-back commitments, firmness levels, escalation, a patterns endpoint or patterns UI, onboarding, UI polish or Figma work, a date picker, bandit, notes UI, multi-agent split, monthly reflections, accounts or passwords, web frontend, Play Store, second deployment.

## Later (ideas parked on purpose; not for now)
- Precise references: every "Grounding theory" section in buddy_docs/ (old and new) cites authors from memory. Replace each with an exact, checkable source (authors, year, title, venue) and trim any claim the source does not support. Ethical reason: the playbook shapes how Buddy talks to people.
- Eval system: scripted conversations per reason and state, scored for reply rules (reply_check) and for the cause-then-move order, run against the real model before changing prompts or docs. Also track whether confirmed causes match what the user said.

## Data and privacy (non-negotiable)
- user_id on every table. No hardcoded users.
- Identity comes ONLY from the Bearer token. Never from the body, URL or in-message text.
- Every query is scoped to the caller. Cross-user access returns 404. Keep the isolation tests green and extend them for any new table or key.
- DELETE /me must wipe everything, including causes and patterns.
- Secrets only in env vars. Never commit .env or *.db.
- Chat text goes to Groq. Don't log message content.

## Hosting reality
Render free sleeps and has an ephemeral disk. No in-process schedulers. No local data. Neon Postgres in prod, SQLite locally. cron-job.org fires /cron/* endpoints with X-Cron-Secret. LLM calls are async, with timeouts, retries and a canned fallback, and never return a 500 on a Groq failure. Never hold a DB session across an LLM call.

## Working style
- Read this file, then do ONE step. Say which files you'll touch before you change them.
- Small diffs. No unrelated refactors. Ask before adding dependencies.
- Don't re-read the whole repo. Read only what the step needs.
- Tests for every step. The suite must be green. Fix or delete known-red tests, don't ignore them.
- After each step: say what changed, how to verify it on the phone, then wait.
- When the user proposes a new idea, check it against "The product". If it doesn't help Buddy find the cause, notice earlier, or respond in the Baymax voice, add it to the later list and don't build it.