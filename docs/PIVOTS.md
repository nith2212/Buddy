# Pivots

Flaws found and decisions made while testing Buddy on the phone (from 2026-11-01).
We are still collecting. Nothing here is built yet unless marked.

## Status
- origin/dev (Render, the phone) is at `d74b719`: frameworks + Echo E1 + Haiku (`GROQ_MODEL=claude-haiku-5-5` on Render). Developer phone-tested every chip on 2026-11-04: replies under 5s, no fallbacks, 6 of 8 chats clean.
- Local, uncommitted: the two phone-test fixes and the named check-in (see section 6), 327 tests green.
- Evals and grading now live in `testing/` (see `testing/README.md` and `testing/GRADING.md`). Run from the repo root.

## Build plan (approved 2026-11-04, hard stop Nov 8)
Quality first, on Groq. Haiku only after Nov 8 and only if Groq doesn't hold up.

**Step 1. Eval harness (Nov 4-5)**
- [x] `testing/evals/run.py --model <groq model>` (moved from backend/evals on 2026-11-04): runs the real `run_turn` on a throwaway SQLite DB against real Groq. Not part of pytest.
- [x] ~15 conversation scenarios from state_frameworks.md: per state a main path, an "idk" path, one edge case (own plan, saying no, switching to tired mid-chat, bigger than work). Only the user's lines are scripted; the dream Buddy lines are the reference, never prompt text.
- [x] Scoring: (1) mechanical: length, questions, banned phrases, clock times, repeated openers or replies, release has no question, saved cause matches (stage-order check gets added in step 3, once stages exist; "no step before confirm" is graded by the rubric); (2) rubric graded by gpt-oss-120b: reacts to what they said, offers not assigns, never shrinks their plan, warm without empty cheer; (3) the developer reads a side-by-side markdown report.
- [x] Output: `testing/results/<date>_<model>.md` with a pass-rate table per state.
- [x] ~80 labeled single messages for the read-call eval ("kinda", "the latter", "both", "yeah but...", "haan maybe", sarcasm, typos). Run once the read call exists.

**Step 2. Baseline run (in the background, during step 3)**
- [ ] One run on today's code (gpt-oss-20b) = the "before" numbers.

**Step 3. Stages + trimmed context (Nov 5-6)**
- [x] Each state's framework becomes one doc in buddy_docs/ with one section per stage; code picks the section.
- [x] Code tracks the stage (saved with each turn). Code catches idk / okay thanks / question mark / tired or distress words; one "read their message" JSON call (sees Buddy's last question) judges confirm / own plan / different cause / bigger than work. Replaces today's judge + decide calls: 2 calls per turn.
- [x] Unsure or broken read result = stay on the stage, writer responds to what they said and re-asks in new words. After 2 tries at a stage, offer the choice. Own plan always leads to a release. Bigger than work always overrides.
- [x] Writer prompt (target 300-400 words): voice card, stage card, situation, this stage's rules only (step-back rule always), last 8 messages, "Known so far" facts saved from the read call. No philosophy doc, intervention docs, memory dump or other stages' rules.
- [x] A new chip tap starts a new session: "Known so far" from last time plus new messages only.
- [x] Loosen the banned-phrase check to the new voice; fold in the held offer/guess fix.
- [x] Unit tests for every stage transition; suite green.
- [x] Avoidance / commitment drift / recovery keep the old path (no frameworks yet), lightly trimmed.

Built 2026-11-04: `brain/flow.py` (stage table + read call), `buddy_docs/framework_*.md` (stage wording, developer to review), `_flow_turn` / `_flow_prompt` in `brain/agent.py`. Writer prompt is now ~300-335 words (was ~1,146). Tests: `tests/test_flow.py` walks every dream conversation through the table. Not yet run against live Groq.

**Step 4. Read-call eval + model comparison (Nov 6-7)**
- [ ] Read-call eval on each model: accuracy per field.
- [ ] Conversation evals on gpt-oss-20b, gpt-oss-120b, Qwen 3 32B. If the daily limit hits, continue hours later or the next day.
- [ ] Developer reads the transcripts and picks the model.

Status 2026-11-04 afternoon: Groq's free-tier daily token caps (per model) ran out. gpt-oss-120b is also the grader, so its cap is the real bottleneck. Done so far: baseline (`testing/results/2026-11-04_1244_*`), new code on 3 chips (`..._1312_*`: framework 31% -> 89%), read eval on qwen3.8-27b (98% right route) and gpt-oss-120b (94%). Qwen 3 32B no longer exists on Groq; qwen/qwen3.8-27b replaces it.
Grading moved off Groq on 2026-11-04: Claude grades in-session against the same 7 criteria (so all runs share one grader and Groq's cap goes only to the writer). Run with `--no-rubric`; graded copies are saved as `testing/results/*_graded.md/json` (rules: `testing/GRADING.md`).
Resume when the caps reset (one at a time, from the repo root):
- [x] Baseline graded by Claude: `testing/results/2026-11-04_1244_openai-gpt-oss-20b_graded.md` (framework 17/69 = 25%, warm voice 10/69 = 14%).
- [x] New Buddy graded by Claude so far: don't know where to start 13/15 (`..._1549_..._graded.md`); scared + too tired 16/20 (`..._1312_..._graded.md`, slightly older code). Feels too big and boring need new runs.
- [ ] `backend/venv/bin/python -m testing.evals.run --model openai/gpt-oss-20b --no-rubric --resume testing/results/2026-11-04_1710_openai-gpt-oss-20b.json`
- [ ] `backend/venv/bin/python -m testing.evals.run --model openai/gpt-oss-20b --no-rubric --only ambiguity_idk` (re-run after the offer-stage fix: "maybe the swipe thing?" now asks for their first step instead of wrapping up)
- [ ] `backend/venv/bin/python -m testing.evals.run --model qwen/qwen3.8-27b --no-rubric` (full re-run: an earlier run had every opener fall back, because qwen refuses a request with no user message. Fixed in `brain/llm.py` `with_user_turn`; that invalid run was deleted.)
- [ ] `backend/venv/bin/python -m testing.evals.run --model openai/gpt-oss-120b --no-rubric --resume testing/results/2026-11-04_1756_openai-gpt-oss-120b.json`
- [ ] `backend/venv/bin/python -m testing.evals.read_eval --model openai/gpt-oss-20b`
- [ ] Grade each finished run by hand (`testing/GRADING.md`: export, grade, merge).

**Haiku result (2026-11-04 evening).** Claude Haiku 5.5 (`claude-haiku-5-5`, Anthropic API, developer paid $5.90 prepaid, auto-reload off) on the new code, all 15 chats, hand-graded: follows the framework 59/69 (86%) vs old Buddy 17/69 (25%); warm voice 62/69 (90%) vs 10/69; keeps their plan 18/18; 0 fallbacks; read eval 91% route. Full run: 3 min, ~109K input + 6K output tokens (about INR 1). Weakest chip: boring/pointless (14/21): persuades or moralizes after they say it's pointless, and the opener guesses instead of asking whether it needs doing. Report: `testing/results/2026-11-04_1915_claude-haiku-5-5_graded.md`. Grader is Claude grading Claude: developer spot-checks before deciding.

**Echo, in steps (agreed 2026-11-04).** Echo is for Buddy only: no push, no user-facing text. A UI for the user is Later.
- [x] **E1. Facts.** (built 2026-11-04, uncommitted: `brain/echo.py`, `POST /cron/echo`, postpone event in `tasks.py`, Buddy's line in `agent._context_line`, `testing/echo_report.py`, `tests/test_echo.py`. Buddy never says the facts; week ends Sunday 23:00 India time; "ignored" = no tap, chat or step on that task within 12 hours of a check-in. Developer still needs to add the cron-job.org job.) Weekly, per user, counted by code (no model call, so nothing can be invented and no Groq quota): confirmed causes and counts; ignored tasks (days untouched, check-ins ignored, postpones); what got finished. Runs for anyone with at least one task, including tasks they're ignoring (ignoring is data); skips users with no tasks. Saved as memory rows (source `echo`), wiped by DELETE /me. Buddy gets at most one line, only when it's relevant. A local text report for dev.
- [x] **E2. Reactions to Buddy.** (built 2026-11-05: `echo.reactions`, saved in the weekly row as `reactions` keyed `<cause>.<move>` with offered / took / own_plan / wanted_move / declined / idk / ack / switched / other / no_reply / progress_after / helped; plus `checkins`, `days_active`, `started_after_tap`; shown in `testing/echo_report.py`. A reaction = the reading on Buddy's next reply within 12h; a repeated stage is judged once, on its last time. "helped" = took the move or their own plan, then a step ticked or the task finished within 24h.) Count, per user: which of Buddy's moves they took or said no to (rough first version, tiny move, lighter way), whether they bring their own plan, which notification buttons they tap or ignore, and whether progress followed a chat within a day. Counted and shown in the report only: Buddy doesn't change yet. Before Nov 8 if E1 goes smoothly.
- [x] **E3. Buddy adapts.** (built 2026-11-05, developer picked all four rules: `echo.profile` + `echo.adapt`, applied in `agent._flow_turn`, rule name saved as `flow.adapt`. own_plan_first: own plans 3+ and more than asks -> at the offer, ask theirs first, Buddy's move as backup; if they then ask Buddy, Buddy suggests as usual. move_first: asked for Buddy's move at the offer 3+ times, never their own -> skip the either/or, straight to the tiny move (never back to a move they just declined). lean_on_helped: a move helped 3+ times for that cause -> offer it first, may say softly it helped before, no numbers. avoid_declined: a move declined 3+ times and never taken -> offer something different. The hint is the one context line and wins over the away cue and pattern line. Dev report lists the rules on per user.) One or two hand-written rules the developer approves, only after something has shown up 3+ times (e.g. always brings their own plan: skip the offer and ask what they'll do). No automatic picking: bandit stays parked. Developer moved it into this week (2026-11-04 night): build it right after E2, Nov 5.
- Later: Echo shaping proactive check-ins (gentler for ignored tasks, best hour); a patterns UI for the user.

**Step 5. Ship (Nov 7-8)**
- [ ] Push to dev, set the model on Render, phone test every chip.
- [ ] Update INTERVIEW_NOTES.md (before/after numbers) and CLAUDE.md "How a conversation goes".

## 1. Conversation design: per-state frameworks (from the dream conversations)
The developer wrote "dream" conversations for unclear, afraid and tired. In them, Buddy never supplies content. It asks until the user names their own goal, core and first step, using the user's own words.

Three shapes:
- **Scaffold** (unclear, probably too big): goal -> simple core -> the user's own first step ("even opening your laptop counts") -> back it and release.
- **Diagnose** (afraid, probably bored): find the flavor (e.g. "don't know how" vs "others will judge it"), then the specific reframe (fear: it has to exist before it can be good, make it rough on purpose), ask if that works, release.
- **Release** (tired): take the pressure off, no task, honest promise to revisit.

To do:
- [ ] Developer writes dream conversations for **feels too big** and **boring or pointless** (both reachable from chips today).
- [ ] Then **avoidance** (no tap, Buddy speaks first after ignored check-ins; silence is data).
- [ ] Later: **commitment drift** (decide if it exists, check-backs are parked) and **recovery**.
- [ ] Code tracks the stage (like `_last_buddy_phase`); the model only words it. Prompt rules alone did not hold on the small model.

Decisions:
- **Voice changed (2026-11-04): Buddy speaks in the developer's own voice, sweet and peppy, not Baymax.** Warm reactions are allowed when they react to something the user said, one per reply, never the same opener twice. Still banned: therapy phrases, promises, pressure. CLAUDE.md and state_frameworks.md updated. TODO in code: `_STOCK` in `brain/reply_check.py` still hard-bans "I understand", "sounds like", "hey there"; loosen it to match, and swap the Baymax line in `_system_prompt` (`brain/agent.py`).
- Never shrink or change the user's own plan; back it as they said it.
- First moves are ONE action, never a list.
- Tired: only say "we'll revisit" if a check-in is really scheduled. Only say "not touched for a while" when activity data supports it.
- Dream replies run 4-6 sentences; the limit is 3. Decide per-stage limits with the frameworks.

## 2. State detection
Now: `detect_state` runs every turn, but only from the chip (fixed for 24h) or task data. Chat text is never read.
Flaw: tap "unclear", then say "I'm exhausted": Buddy stays in ambiguity and keeps breaking the task down.

Decisions:
- The chip sets the starting state.
- A **confirmed cause switches the state** from the next turn (the judge already returns the cause, no extra call).
- No LLM classifier on every message (extra Groq call, flips on one word). Exception: a cheap keyword check for clear tiredness or distress ("exhausted", "can't anymore") switches to tired or to the step-back reply.

## 3. Prompt slimming
Now: docs are already scoped to the detected state (philosophy + that state's stance + one intervention). The writer prompt is about 1,130 words for a guess turn: philosophy 220, stance 149, intervention 214, **rules 463**, plus up to 12 history turns. The hackathon prompt was about 25 lines.
Flaw: voice and tone repeated in three places; every turn carries rules for other stages (tired, distress, praise, first moves). Too many rules make the small model stiff ("You're working on X..." every time).

Decisions (target 300-400 words):
- A ~5-line voice card instead of the full philosophy doc.
- A stage card from the developer's framework instead of the whole intervention doc.
- Only the rules for this stage. Rules the code already checks (clock times, stock phrases, length) get one line or none.
- Fewer history turns (4-6); the model copies its own past wording.
- Probably drop the decide call once every state has a framework (saves a Groq call per turn).

## 4. Model
- Hackathon (`bd361af`, on `main`) used **llama-3.1-8b-instant**, smaller than today's **gpt-oss-20b**. Its better feel likely came from the short, loose prompt, not the model. Its slowness came from 3 blocking LLM calls plus Azure search per turn.
- Plan: separate setting for the writer model (judge/decide stay small). Compare current writer vs llama-3.1-8b with a short prompt vs llama-3.3-70b, on the dream scenarios, side by side. Watch the Groq cap (8k tokens/min, 1,000 requests/day).

- **Goal is a STRONGER model, not a free-tier small one.** Locally (24GB Mac, Ollama, 4-bit): Mistral Small 24B (~14 GB, comfortable), Gemma 3 27B (~17 GB), Qwen 3 32B (~19-20 GB, tight). 70B does not fit.
- Test locally, ship the same model through a pay-per-token API (Groq, Bedrock, Together, OpenRouter). Self-hosting a cloud GPU is ~$400-700/month even idle, so no.
- Rough cost (estimates, check current prices): ~$0.10-0.60 per M tokens; a 20-user demo about $5-25/month, about half that with the slimmed prompt. Fits a ~Rs 700-1,000/month budget.
- Model alone will not fix it: the 1,130-word rule-heavy prompt also makes models stiff. Slimming and stage-in-code still apply.
- Later: fine-tune a small model on Buddy's own conversations (see CLAUDE.md "Later"), not on therapy datasets.

## 4b. Priority (2026-11-04)
Quality first, before Echo. Backend and frontend work as intended; the prompt and context are what disappoint. Next input: the developer's remaining dream conversations, then decide what to build.

## 5. Evals (from CLAUDE.md "Later")
- The developer's dream conversations become the scripted eval scenarios.
- Run against the real model before changing prompts, docs or models. Score reply rules, stage order, and whether saved causes match what the user said.

## 6. Flaws seen on device (log)
- Same opener every reply, due time repeated. Fixed in `6e36a94`.
- "The latter" to an either/or guess counted as confirmation, skipped the guess. Fixed in `6e36a94`.
- Same reply sent three times; "Bye" got the last instruction again. Fixed in `6e36a94` (release after a move or plan).
- User's own plan ("work on the RAG docs") shrunk to "highlight one paragraph". Fixed in `6e36a94`.
- Model ignored the offer step and handed out a step anyway; first move was a list ("three layout options"). Fixed locally, HELD.
- After "idk", asked another open question instead of a guess. Fixed locally (soft check), HELD.
- State never changes from what the user types. See section 2.
- Phone test 2026-11-04 (Haiku), fixed locally the same night, replayed live on Haiku (`testing/results/2026-11-04_2240..2242_*`), new eval scenarios `phone_overwhelm_took_buddys_step` and `phone_low_interest_must_do`:
  - "Okie I can do that" to Buddy's micro-step got "you picked it yourself!", and Buddy argued when corrected. Cause: the reader called accepting Buddy's step `own_plan`, so the wrap-up was told "their plan". Fix: a new reading `accept` (wraps up with "If they took your move": never credit them), and the Followup card agrees with a correction in a few words, no new step.
  - Boring chip persuaded: "you don't have to like it to get through it", "a report like this can build your manager's trust". Causes: "I HAVE to do it" read as a no, so the "try a different option" wording kicked in; "I don't like it" stayed on narrow with the no wording; the purpose card listed what it could give, and the model stated it. Fix: open+no and narrow+confirm route on, purpose+no goes to lighten, the cards say ask-never-tell, lighten offers "the bare minimum", and reply_check hard-bans "don't have to like it", "still has to get done" and "totally valid".
  - The daily check-in never said which task it was about. Now: "How's “<title>” going today?" (title capped at 60 chars; goes through Expo/Google push, developer OK).

## Echo page for the user (proposal, 2026-11-04 night; developer to pick)
A friend telling you what they noticed, never a report card. Code templates only (no free model text).
- Must: (1) wins this week (tasks finished, steps ticked, "started N times when it felt hard"); (2) gentle streak: 7 dots, one per day you touched a task, quiet reset every Sunday, optional up-only total ("shown up 23 days"); (4) one Buddy line from the week's numbers.
- Should (needs E2): (3) what got in the way + what helped, only causes confirmed 3+ times ("fear came up 3 times; a rough first version helped twice").
- Stretch: (5) "Talk about my week" chat (new short framework: open, reflect, one gentle intention, release).
- Never: ignored check-ins, days untouched, postpones, comparisons, percentages, empty praise. Quiet week: "Quiet week. That's okay."
- Backend: read-only `GET /echo/week` (scoped to the caller), **built 2026-11-05** (`echo_routes.py`, `echo.this_week`): `days` (Mon..Sun, active or not), `total_days` (up-only), `wins` {tasks_finished, steps_done, started_when_hard}, `line` (template), `helped` [{cause, move, times, text}] only for causes confirmed 3+ times. Template wording (`CAUSE_TEXT`, `MOVE_TEXT`, `week_line`) awaits the developer's review. Weekly only: monthly reflections stay parked.

## New UI (step F), built 2026-11-05
Developer-approved mockup: https://claude.ai/artifact/1HqNqLYwuuZuWbqxWJgtGo (private to the developer). Hand-drawn style: ink outlines,
uneven corners, hatched offset shadows, Gaegu (headings) + Nunito (text), "Dusk" palette (cream F2EAE0, sky B4D3D9,
lavender BDA6CE, violet 9B8EC7; violet only for shadows, text is always ink 2A2238). Buddy = the developer's white "dumpling"
blob that wobbles and blinks (moods: default, happy, worried; worried only for connection problems).
- Files: `src/constants/sketch.ts` (palette, fonts, corners), `src/components/sketch.tsx` (Txt, Card, Hatch, SketchButton,
  Chip, Bubble), `src/components/buddy-blob.tsx`, `src/components/side-menu.tsx` (menu + BrandHeader),
  `src/components/buddy-splash.tsx` (loading screen, honest about Render waking up).
- Screens: `/` tasks; `/task/[id]` that task's own chat (steps strip, its history, reason chips; "stuck again?" reopens them);
  `/chat` "which task?" picker that opens the task's own thread; `/echoes` from GET /echo/week.
- Menu has "Delete my data" instead of "Log out" (no accounts: DELETE /me, then a fresh anonymous identity via `restart()`).
- New deps (developer OK): react-native-svg, @expo-google-fonts/gaegu, @expo-google-fonts/nunito. Native change: needs a new APK
  (`eas build -p android --profile preview`). Native splash background is now cream; its icon is still the old one.
- App icon, Android adaptive + themed (monochrome) icon, splash and favicon are dumpling Buddy, drawn by
  `scripts/make_icons.py` (stdlib + macOS QuickLook, no installs). Icon background lavender, splash cream.
- Not done: "talk to buddy about my week" opens the task picker (the reflection chat is Later); dark mode (light-only design).

## Cleanup and the untapped-chat fix (2026-11-05)
- Removed the Expo starter-template files and images, the reset-project script, `brain/rag.py` + `ingest.py`
  (an unused vector-search experiment) and `playbook.get_playbook`. The iOS icon now uses Buddy.
- Docs moved to `docs/` (this file, `state_frameworks.md`, `HOW_BUDDY_WORKS.md`).
- Typed without a reason tap: Buddy reacts and asks what's in the way, and the app shows the chips
  (`agent._ask_reason_turn`, wording in `framework_shared.md` "Ask the reason"). Before this, those chats
  went straight to the generic path, which scored 25% in the evals.
