# Copilot instructions for Buddy

You are continuing work on **Buddy**, built by one developer (Nithyasri). Read this whole file before you
change anything. It covers the product rules, the UI style, how the code is organised, how to run, test and
ship, the traps already found, and what to do next. Call the person you're working with "the developer",
never "the owner".

For the full picture, read `docs/HOW_BUDDY_WORKS.md` (end to end) and `docs/PIVOTS.md` (the build log: every
decision and every bug found on the phone). The developer's conversation designs are in
`docs/state_frameworks.md`.

---

## 1. The product: rules you must not break

Buddy helps people **start** a task by finding out **why** they're stuck, then helping with that specific
cause. Other apps track the task; Buddy tracks the person.

The five causes the user can tap:

| Reason | Internal key | Framework / state |
|---|---|---|
| Don't know where to start | `unclear` | `ambiguity` |
| Feels too big | `too_much` | `overwhelm` |
| Scared it won't be good enough | `afraid` | `perfectionism` |
| Boring or pointless | `bored` | `low_interest` |
| Too tired | `tired` | `fatigue` |

**Voice.** The developer's own: a sweet, peppy, kind friend. Short and warm.
- Never shame, lecture, moralize or pressure.
- Praise only something the user actually did.
- No therapy phrases. Excitement only for something real.

**Root cause first.**
- Buddy asks before it suggests.
- It **offers, never assigns**: one tiny move, phrased as a question.
- If the user has their own plan, back it exactly as they said it. Never shrink or change it.

**Safety.** If something sounds bigger than work (health, grief, crisis, hopelessness), Buddy steps back
honestly: it's a task companion, not the right support. It points to someone they trust or a local
helpline, and stops working on the task. Work states only, never a diagnosis.

**Memory and patterns.**
- Save a cause only when the user confirms it.
- Mention a pattern only after it has been confirmed 3+ times, softly, and **never with a number**.

**Echo** (weekly learning):
- Buddy never says Echo's facts or any count to the user.
- The Echoes page never shows ignored check-ins, days untouched, postpones, comparisons or percentages.
  Only earned, kind things.

**Privacy (non-negotiable).**
- `user_id` on every table. Identity comes **only** from the bearer token.
- Every query is scoped to the caller; another user's row returns 404 (use `owned_or_404`).
- Extend `backend/tests/test_isolation.py` for any new table or route.
- `DELETE /me` must wipe everything, including memory and Echo.
- Secrets only in env vars. Never commit `.env`, `*.db` or `google-services.json`.
- Never log message content or tokens.

**Buddy's wording is the developer's.** Everything Buddy is told to say lives in
`backend/brain/buddy_docs/*.md`. Change those docs only when asked, and tell the developer what you changed
so they can review it.

**Parked** (don't build or propose): sprint timer, check-back commitments, firmness levels, escalation,
onboarding, a date picker, a bandit, a notes UI, multi-agent split, monthly reflections, passwords,
a web frontend, Play Store, a second deployment.

---

## 2. Repository map

```
src/app/                 screens (expo-router): index (tasks), task/[id] (a task's chat), chat (task picker),
                         echoes (weekly report), _layout (fonts, auth, push, loading screen)
src/components/          sketch.tsx (the design system), buddy-blob.tsx (the mascot), side-menu.tsx,
                         buddy-splash.tsx, checkbox.tsx
src/constants/sketch.ts  palette, fonts, corner shapes  (src/constants/api.ts: API URL + invite code)
src/lib/                 api.ts (typed client), dates.ts, reasons.ts, checkin-flow.ts, checkin-categories.ts
src/hooks/               use-auth.ts (anonymous token in SecureStore), use-session.tsx (token + restart)

backend/main.py          FastAPI app; routers: auth, tasks, chat, notifications, cron, me, echo_routes
backend/brain/agent.py   run_turn: picks the path (framework / ask-the-reason / generic), writes, learns
backend/brain/flow.py    the per-cause stage machine and the "read the user's message" call
backend/brain/echo.py    Echo E1 (weekly facts), E2 (reactions), E3 (adapt rules), the Echoes page data
backend/brain/llm.py     the only place a model is called (Anthropic SDK for claude-*, else Groq)
backend/brain/reply_check.py   mechanical checks every reply must pass (hard bans + soft rewrites)
backend/brain/buddy_docs/      Buddy's playbook and framework wording (developer reviews)
backend/tests/           pytest, fake model, no network
testing/                 evals against the real model (cost money), grading kit, Echo dev report
scripts/make_icons.py    redraws icon, adaptive/themed icons, splash, favicon from Buddy's vector art
docs/                    HOW_BUDDY_WORKS.md, PIVOTS.md, state_frameworks.md, buddy.svg (README animation)
```

---

## 3. The UI style: follow it exactly

The look is **hand-drawn**: ink outlines, slightly uneven corners, hatched or offset shadows, a handwritten
heading font, and **Buddy**, a soft white "dumpling" blob. Every screen is built from the components in
`src/components/sketch.tsx` and the tokens in `src/constants/sketch.ts`. **Don't write raw styled `View`s or
`Text` for things these components already do**, and don't add another UI library.

### Tokens (`src/constants/sketch.ts`)

| Token | Value | Use |
|---|---|---|
| `Ink` | `#2A2238` | all text, all outlines, button shadows |
| `Palette.bg` | `#F2EAE0` cream | every screen's background |
| `Palette.card` | `#FFFCF8` | cards, Buddy's chat bubbles, headers, input bars |
| `Palette.soft` | `#B4D3D9` sky | selected chips, highlight banners, Buddy's quote |
| `Palette.pop` | `#BDA6CE` lavender | primary buttons, the user's bubbles, checked boxes |
| `Palette.deep` | `#9B8EC7` violet | **shadows and accents only, never text** (too light to read) |
| `Palette.white` | `#FFFFFF` | inputs, unselected chips |
| `Palette.danger` | `#9E2F2A` | error text only. No red backgrounds, nothing alarming |
| `Palette.muted` | `#5A5168` | placeholders, small secondary text |
| `Border` | `2.5` | outline width (chips and small boxes use 2) |
| `Wobble.a/b/c/round/buddy/me` | per-corner radii | pick one per element; vary neighbours (a, b, c…) so boxes look drawn |
| `Font.hand` | `Gaegu_700Bold` | headings, buttons, chips, labels |
| `Font.body/semi/bold` | Nunito 400/600/700 | reading text |

Android ignores `fontWeight` for custom fonts, so always pick a family from `Font`, never `fontWeight`. The
fonts are loaded in `src/app/_layout.tsx`, and the app waits for them behind the splash screen.

### Components (`src/components/sketch.tsx` and friends)

| Component | Props | Use it for |
|---|---|---|
| `Txt` | `variant`: `title` (34), `heading` (26), `hand` (19), `body`, `semi`, `bold` (16), `small` (13) | all text. Gaegu variants for headings and labels, Nunito for anything people read |
| `Card` | `shadow`: `hatch` (default), `solid`, `none`; `wobble`; `dashed`; `style` = inside, `outerStyle` = margins/flex | any boxed content. Hatched violet shadow for main cards, dashed for secondary info |
| `SketchButton` | `label` or `children`, `tone`: `pop`/`soft`/`plain`/`card`, `wobble`, `lifted` (ink offset shadow, default on), plus Pressable props | every button. It presses into its shadow. Icon-only buttons need `accessibilityLabel` |
| `Chip` | `label`, `selected`, `onPress`, `disabled` | choices (reasons, due dates, which task). Selected = sky |
| `Bubble` | `from`: `buddy` / `me` | chat messages. Buddy's is cream with a violet shadow; the user's is lavender |
| `Hatch` | `color`, `style` | diagonal pen hatching that fills its parent (shadows, filled day dots) |
| `BuddyBlob` | `width`, `mood`: `default`/`happy`/`worried`, `animated` (wobble + blink), `label` | the mascot |
| `Checkbox` | `checked`, `onPress`, `label`, `size` | the sketch square checkbox (44px touch target) |
| `MenuButton`, `BrandHeader` (`side-menu.tsx`) | `topInset` | top-level screens: menu button + "buddy." |
| `BuddySplash` (`buddy-splash.tsx`) | `failed` | the loading screen |

**Buddy's moods:**
- `default`: loading, chat, menu, empty states.
- `happy`: wins, Echoes, celebrations.
- `worried`: **only** for "can't reach the server" or "didn't send". Never in response to the user's feelings.
- Use `animated={false}` for small avatars next to text (38–52px).

### Layout conventions
- Screen root: `flex: 1, backgroundColor: Palette.bg`. Side padding 16–24, gaps 8–20.
- Top-level screens start with `<BrandHeader topInset={insets.top} />`. Pushed screens (a task's chat) get a
  back button: `SketchButton tone="plain" wobble="round" lifted={false}`, with an ink arrow drawn in
  `react-native-svg`.
- Headers and bottom input bars: `Palette.card` background with a **dashed** ink border on the side that
  faces the content.
- Inputs: white, `Border` ink outline, `Wobble.c` or `Wobble.round`, `Font.semi` 16, placeholder `Palette.muted`.
- Empty states and errors: a `BuddyBlob` (default or worried) plus a short, kind `Txt variant="hand"` line
  and, if useful, a `SketchButton` ("Try again").
- Icons: draw them with `react-native-svg` in `Ink` with round caps. No icon fonts, and no emoji in UI chrome.
- Light theme only (the design has no dark mode yet).

### Accessibility (required)
- Touch targets at least 44px.
- `accessibilityRole` and `accessibilityLabel` on every pressable, especially icon-only ones.
- `accessibilityState` for selected or checked.
- Text stays `Ink` on light colours. Violet is never text.
- Every animation respects `useReducedMotion()` (`BuddyBlob` and `BuddySplash` already do).

### A new screen, as a template

```tsx
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BuddyBlob } from '@/components/buddy-blob';
import { BrandHeader } from '@/components/side-menu';
import { Card, SketchButton, Txt } from '@/components/sketch';
import { Palette } from '@/constants/sketch';

export default function ExampleScreen() {
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.screen}>
      <BrandHeader topInset={insets.top} />
      <View style={styles.content}>
        <Txt variant="title" accessibilityRole="header">Title:</Txt>
        <Card wobble="a" style={styles.card}>
          <Txt variant="bold">Something worth reading</Txt>
        </Card>
        <SketchButton label="do the thing" onPress={() => {}} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Palette.bg },
  content: { paddingHorizontal: 24, gap: 18 },
  card: { padding: 16, gap: 6 },
});
```
The approved mockup the UI was built from: https://claude.ai/artifact/1HqNqLYwuuZuWbqxWJgtGo (private to
the developer).

---

## 4. How the backend thinks

**Code decides, the model words.** `run_turn` in `backend/brain/agent.py` picks one of three paths:

1. **Framework path** (`_flow_turn`): a reason was tapped in the last 24h.
   - `flow.read_message` reads the user's message: patterns first, then one structured-JSON model call.
   - `flow.next_stage` moves a fixed stage table.
   - The writer gets that stage's card from `buddy_docs/framework_*.md`.
2. **Ask the reason** (`_ask_reason_turn`): a typed message with no recent tap.
   - Buddy reacts and asks what's in the way; the reply has `ask_reason: true` and the app shows the chips.
   - It never asks twice in a row.
3. **Generic path**: everything else. Closing notifications, finished tasks, a second untapped message.

**Every reply** goes through `reply_check.check_reply`.
- A hard violation gets one rewrite, then the canned fallback.
- **Never weaken the bans.** They're there because the model drifted on the phone.

**LLM rules.**
- `llm.complete` is async, with timeouts and retries.
- **Never hold a DB session across a model call.** Do every read first, then `db.rollback()`.
- A model failure must never return a 500. Fall back.

**Echo** (`backend/brain/echo.py`):
- **E1 + E2:** saved weekly by `POST /cron/echo` (Sunday 23:00 India time) as memory rows `echo.week.<date>`.
- **E3:** four rules in `echo.adapt`. Each switches on after 3+ occurrences, and gives a reroute or one hint line.
- **The page:** `GET /echo/week` returns this week (live) plus `last_week`. User-facing text is code templates only.

**Hosting reality** (Render free tier): it sleeps when idle and has no persistent disk, so there are no
in-process schedulers. cron-job.org calls `POST /cron/checkins` (hourly) and `POST /cron/echo` (weekly),
both with the `X-Cron-Secret` header. Both are idempotent.

---

## 5. Run, test, ship

**Backend (local)**
```bash
cd backend
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/uvicorn main:app --reload
venv/bin/python -m pytest -q            # must stay green (359 tests as of 2026-11-05)
```
Env vars: `INVITE_CODE`, `CRON_SECRET`, `GROQ_MODEL=claude-haiku-5-5`, `ANTHROPIC_API_KEY` (or
`GROQ_API_KEY` for Groq models), and optionally `DATABASE_URL` (defaults to local SQLite).

**App**
- The phone runs a **development build**.
- **JS-only changes:** run `npx expo start`, then press `r` to reload.
- **New native dependency:** rebuild with `npx eas-cli build -p android --profile development`.
- **Typecheck:** `npx tsc --noEmit`. There is no ESLint and no app test runner. Don't add either without
  asking.

**Evals (cost real money).** `backend/venv/bin/python -m testing.evals.run --model claude-haiku-5-5
--no-rubric`, run from the repo root. Grading rules are in `testing/GRADING.md`, and the kit is in
`testing/README.md`. Ask before running a full eval.

**Deploy**
- **Backend:** push to `dev`, then **Render → Manual Deploy → Deploy latest commit**. Auto-deploy is off, so
  a push alone does not deploy.
- **App:** the EAS env var `GOOGLE_SERVICES_JSON` is a secret file, used by `app.config.js`.
- **A standalone build** (`--profile preview`) also needs `EXPO_PUBLIC_API_URL` and `EXPO_PUBLIC_INVITE_CODE`
  set in the EAS preview environment. Both are set (2026-11-06). Without them, the APK falls back to
  `localhost:8000` and can't reach the server.
- **When a new APK is needed:** a backend change only needs a Render deploy, since every phone talks to the
  server. **Any** app change (any file in `src/`, even a typo) needs a new APK, and testers reinstall it,
  because the APK carries a frozen copy of the JS. The dev build is different: it loads JS from Metro, so it
  only needs a rebuild for new native dependencies.

**Git**
- Work on `dev`. `main` is updated through a dev → main PR.
- The old hackathon version is at tag `hackathon-v1`.
- Never push or open PRs unless the developer asks. End commit messages with a short "why".

---

## 6. Traps already found (don't repeat them)

- **Reanimated worklets.** A module-level array captured by a worklet came through `undefined` on the UI
  thread. That crashed the frame loop and froze the loading screen. Keep data a worklet needs **inside** the
  worklet (see `shapePoint` in `buddy-blob.tsx`).
- **Typed routes.** After adding a screen, `tsc` fails until `.expo/types/router.d.ts` regenerates. Run
  `npx expo start` once.
- **`npx expo lint`** silently adds `eslint` to `package.json` and creates a config file. Don't run it
  unless the developer approves the dependency.
- **"App not installed"** on Android means the signing key differs from the installed app. Uninstall first,
  which also clears the anonymous token, so it becomes a new user.
- **The reader's labels matter to the writer.** "okay I can do that" is `accept` (Buddy's idea), not
  `own_plan`. Mixing them up made Buddy credit the user with its own suggestion.
- **The boring chip** is where the model most often drifts into persuading. `reply_check` bans
  "don't have to like it", "still has to get done" and "totally valid". Keep those bans.
- **Logging:** never log tokens or message text (`use-auth.ts` used to log the token in dev).
- **zsh** doesn't word-split `$VARS`, so file lists in shell loops break. Use Python or arrays.

---

## 7. Where things stand, and what's next

**Done (2026-11-05):**
- the per-cause conversation engine on Claude Haiku 5.5 (86% "follows the framework" in hand-graded evals,
  up from 25%)
- Echo E1–E3
- the Echoes page (this week, last week, share as text)
- the new hand-drawn UI, plus icons and splash
- ask-the-reason for untapped chats
- named check-in notifications
- a cleaned-up repo
- an all-rights-reserved license

**Next, in order:**
1. **Support the developer's phone testing.** Fix what they report, in small commits, with tests.
2. **Task edit and delete** (the developer asked for small task CRUD).
   - **Backend:** add `DELETE /tasks/{id}`.
     - Use `owned_or_404`.
     - Delete the task's subtasks, messages, events and emotion logs, plus the memory row
       `blocker.task.<id>`, in one transaction.
     - Add tests: delete works; another user gets 404; nothing of that task is left.
     - `PATCH /tasks/{id}` already edits `title`, `due_date` and `status`.
   - **App:** on a task card, long-press (or a small "edit" `SketchButton`) opens a sketch-styled sheet:
     - a `Card` with a title input and the due-date `Chip`s
     - "save" (`tone="pop"`) and "delete task" (`tone="plain"`, behind an `Alert` confirm)
     - Add `deleteTask` and an extended `updateTask` to `src/lib/api.ts`.
3. **Standalone preview APK:** the first one was built on 2026-11-06 (Render deployed from `dev` first) and
   goes to Android friends for weekend testing. On Monday Nov 9 their Echo shows a real "last week".
   - **While friends test, deploy only for fixes.** Every deploy restarts the server, and anything
     half-finished on `dev` reaches their phones.
   - **After testing (Nov 9–11):** merge `dev` → `main` with a PR, then switch Render's deploy branch to
     `main`, so `main` = what's live.
4. **EAS Update, at the next APK rebuild** (developer's call, 2026-11-06). Add `expo-updates` (a new
   dependency: ask first), run `eas update:configure`, then build one more APK. After that, app-code fixes
   reach installed APKs over the air with `eas update`, and testers don't reinstall. Native changes still
   need a new build. Don't cancel a running build just for this; add it when a rebuild is needed anyway.
5. **iPhone testers.** There's no APK-style install on iOS. The options:
   - **TestFlight:** needs an Apple Developer account ($99 a year).
   - **Expo Go + `npx expo start --tunnel`:** free. All the deps are standard Expo modules, so it should
     run, but only while the developer's laptop serves it, and push notifications probably won't work.
   - **Possibly Expo Go loading an EAS Update** (no laptop needed): unverified for SDK 57, so try it once
     EAS Update exists.
   - **A web build is parked** (web frontend and a second deployment are both on the parked list). It would
     need CORS on the backend, a web fallback for `expo-secure-store` in `use-auth.ts`, notification guards,
     and static hosting.
6. **After that**, in no particular order: Google sign-in (Expo auth + Google ID-token check on the backend,
   linking the current anonymous user), the "talk about my week" reflection chat, per-user time zones for
   Echo, exact citations in the playbook, and dark mode.

**Known limitations:**
- Accounts are anonymous (token + invite code).
- The Echo week is India time for everyone.
- "Talk to Buddy about my week" opens the task picker.

---

## 8. Working style the developer expects

- Say which files you'll touch before you change them. Make small diffs, with no unrelated refactors.
- **Ask before adding any dependency.**
- Every change comes with tests, and the suite stays green.
- Check new ideas against section 1. If an idea doesn't help Buddy find the cause, notice earlier, or speak in
  its voice, add it to the "later" list in `docs/PIVOTS.md` instead of building it.
- Keep `docs/PIVOTS.md` updated with decisions and bugs found on the phone.
- When a reply to the developer is long, lead with what changed and how to check it on the phone.
