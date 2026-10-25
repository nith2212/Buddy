@AGENTS.md
Note: the old hackathon code (incl. the React web frontend) lives only on origin/main (backend/, frontend/) and in git history (9f26c73). Use the frontend as UX reference only. Only the backend is being ported.

# Buddy: project rules

## What this is
Proactive accountability companion. Expo (React Native, Android first) app + FastAPI backend. Buddy notices when a user is struggling with a task and reaches out first. Tone: calm, non-judgmental, never generic (Baymax). It detects WORK states only (avoidance, overwhelm, fatigue, ambiguity, etc.), never mental-health states. If signals go beyond work, it steps back honestly.

## Layout
- backend/  : live FastAPI backend
- src/, app.json, eas.json : Expo app (repo root, not a mobile/ folder)
- backend/brain/ : imported hackathon brain (agent, echo, tools, rag, ingest, buddy_docs). Being ported to the rules below.
- origin/main : old hackathon code. READ-ONLY reference. Port from it, never edit it.

## Locked scope
Deadline: core deployed and working on a real phone by Oct 24. Skeleton deployed by Oct 17. Stretch window Oct 25-31.

CORE:
- Onboarding, tasks with due dates + manual subtasks
- Proactive notification check-in (task status -> feeling -> "want to talk?")
- Chat with the brain when the user opts in
- If user declines chat: brain still runs and sends ONE tailored closing notification
- Event-sourced memory
- Echo (weekly, night) writing patterns back to memory
- Backend deployed, APK installed on phone

STRETCH (only after core is deployed): tone adaptation/reinforcement, then bandit, Notes UI, context trimming.

NOT NOW (do not build or propose mid-task): multi-agent split, weekly/monthly reflections, per-user playbook annotations, accounts/passwords/OAuth, web frontend, Play Store, second deployment, queues (Redis/Celery), autoscaling, caching layers.
If a task seems to need something from NOT NOW, stop and ask.

## Per-turn pipeline (chat)
1. Identify user: auth header token -> user_id
2. Load context: active task, recent events, memory rows. ALL scoped by user_id and CAPPED (limit rows and characters injected)
3. Reason: layer 1 behavioral (task deltas, idle time), layer 2 keywords, layer 3 LLM only when 1 and 2 conflict -> confidence-weighted hypotheses
4. Retrieve playbook for the top state
5. Decide: LLM call 1 picks an intervention + justification, excluding recently used interventions
6. Act: LLM call 2 writes the message
7. Learn: save events + memory in ONE transaction

## Playbook retrieval
- The playbook (13 docs in buddy_docs/: states, interventions, core) is shared across users and holds NO user data.
- Default: get_playbook(state) reads the local buddy_docs/ files (state doc + its linked intervention docs + core docs). Optional USE_QDRANT=1: filter by detected state in Qdrant (no query embedding); if unreachable, fall back to the local files. No local torch embedding model: the host has little RAM. If semantic search is added later, use a lightweight ONNX embedder (e.g. fastembed). Never fall back to an LLM call.

## Non-chat paths
- Proactive check-in: external cron calls POST /cron/checkins -> pick users with due or untouched tasks not nudged recently -> per-user try/except -> Expo push in batches. Taps come back as events.
- User declines chat: run steps 2-7 on the logged taps; output is ONE tailored closing notification.
- Echo: cron calls POST /cron/echo weekly at night (writes echo.* memory only; no user-facing push) -> loop users one at a time -> skip users under a minimum-events threshold -> write echo.* memory for that user only. Also expose a manual trigger.
- Check-ins are proactive, driven by task state (due date proximity, untouched time). No fixed user-set times.

## Hosting reality (free tier)
- Render free sleeps and has an ephemeral disk: NO in-process schedulers (no APScheduler), no data on local disk.
- Neon Postgres in prod, SQLite locally. Keep the DB layer portable.
- cron-job.org fires the cron endpoints. Every /cron/* endpoint requires an X-Cron-Secret header matching an env var, else 401. Set generous timeouts for cold starts.
- Push via Expo push API, batched.

## Reliability rules
- The backend is stateless: no per-user data held in server memory.
- LLM calls must NOT block the event loop: use async clients or run sync calls in a thread pool.
- LLM calls get timeouts, retries with backoff, and a graceful fallback message when Groq errors or rate-limits.
- Index user_id on every table. Use connection pooling.
- Batch jobs isolate failures per user.
- Groq key is capped at 8,000 tokens/min (any model). A turn costs ~1.5-3k, so keep prompts lean; llm.py logs usage per call and honors Retry-After on 429.

## Data and privacy rules (non-negotiable)
- user_id on every table. No hardcoded user ids anywhere.
- Identity comes from an auth header token issued by the server at first launch (stored in expo-secure-store on the phone). NEVER from request body or URL params.
- Echo and all queries are scoped to one user at a time.
- Keep a test proving user A cannot read user B's tasks, events, memory or chats.
- DELETE /me wipes all of a user's rows.
- Secrets only in env vars. Never commit .env. DB URL, API keys, cron secret, host config all via env.

## Stack
FastAPI on Render free, Neon Postgres, Groq openai/gpt-oss-20b (llama-3.1-8b-instant was retired on Groq; override via GROQ_MODEL), Qdrant Cloud, cron-job.org, Expo push. Mobile: Expo, EAS APK.

## Working style
- One feature end to end at a time. Plan first for anything touching multiple files.
- Small diffs. No unrelated refactors. Ask before adding dependencies.
- Don't re-read the whole repo each time; read only what the task needs.
- Say what you changed and how to verify it.


## Merge plan status
Base branch: merge-brain. Brain imported at backend/brain/ (unwired). No runtime embeddings: playbook = local files in buddy_docs/, get_playbook(state); Qdrant only behind optional USE_QDRANT flag.
Steps: 1 schema+auth+isolation (DONE) | 2 auth on existing endpoints + POST/GET /tasks + DELETE /me (DONE) | 3 Render+Neon skeleton, mobile secure-store bootstrap + register push token | 4 cron endpoints + Expo batch push (static text) | 5 repo layer + get_playbook | 6 rewrite state detection on task deltas/idle time (no postponement) | 7 port agent turn (async Groq, timeouts, fallbacks, /chat, /initiate) | 8 mobile chat + task UI + notification response handler | 9 weekly Echo via /cron/echo.
Known issues to fix in the brain: keyword substring bugs (use word boundaries), [System:]/[EmotionPick:] in-band control strings (use explicit params), /run-echo must be behind X-Cron-Secret, `/later` means notification_ignored not postponed.