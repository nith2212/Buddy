# Eval run: openai/gpt-oss-20b

- When: 2026-11-04 15:49  (1.4 min)
- Code: after: stages + trimmed prompt + read fixes (uncommitted)
- **Unfinished (daily limit): perfectionism_main, perfectionism_own_plan, perfectionism_bigger, fatigue_main, fatigue_still_wants, overwhelm_main, overwhelm_own_step, overwhelm_vague, low_interest_boring, low_interest_pointless_none, low_interest_pointless_purpose, low_interest_optional**
- Writer model: `openai/gpt-oss-20b`; grader: `claude (by hand, testing/GRADING.md)`
- Groq calls: pipeline 24 (13465 prompt / 1550 completion tokens), grader 11

## Summary

| State | Scenarios | Replies | Clean replies (no mechanical flag) | Rubric pass | Cause saved right | Fallbacks |
|---|---|---|---|---|---|---|
| ambiguity | 3 | 15 | 100% | 88% | 3/3 | 0 |

| Rubric criterion | Pass | n/a | Errors |
|---|---|---|---|
| follows_framework | 87% (13/15) | 0 | 0 |
| reacts_to_user | 75% (9/12) | 3 | 0 |
| offers_not_assigns | 100% (1/1) | 14 | 0 |
| no_premature_step | 100% (15/15) | 0 | 0 |
| keeps_their_plan | 100% (3/3) | 12 | 0 |
| warm_voice | 73% (11/15) | 0 | 0 |
| no_invention | 100% (15/15) | 0 | 0 |

| Mechanical flag | Replies |
|---|---|
| request failed | 0 |
| canned fallback reply (Groq failed or every draft broke a hard rule) | 0 |
| more than one question | 0 |
| more than 3 sentences | 0 |
| therapy phrase, promise or pressure | 0 |
| invented clock time | 0 |
| opens like an earlier reply | 0 |
| near-copy of an earlier reply | 0 |
| asks something after the user signed off | 0 |

## Scenarios

### ambiguity_main  (ambiguity, chip: unclear)

_Goal -> core -> their own first step -> release. Buddy never supplies the content._

Cause expected: `unclear` · saved: `unclear` · OK

> **Buddy** (ambiguity, open; 1.8s): Hey, I see you're working on finishing the Nixly app. It’s totally normal to feel a bit stuck at the start. What would “done” look like for this task?

> **User:** This app will help me declutter my gallery while swiping. And each save gives me points. With those points I can build a cat sanctuary!
>
> **Buddy** (ambiguity, core, read: answer; 1.0s): You’re aiming to clear your gallery by swiping, earn points, and use those points to build a cat sanctuary. What’s the one core feature that will make the swipe‑to‑declutter work?
>
> - ⚠ ✗ warm_voice: right stage, but no reaction to the cat sanctuary: not peppy

> **User:** Hmmm for this, I need the swipe mechanism. Once that's built, others are additions.
>
> **Buddy** (ambiguity, first_step, read: answer; 1.5s): Sounds good—let’s focus on the swipe mechanism first. What’s the very first tiny action you can take to start building that swipe?

> **User:** Hmmm I can start setting up expo on my phone and laptop.
>
> **Buddy** (ambiguity, release, read: own_plan; 3.9s): Great plan—setting up Expo on your phone and laptop is a solid first step. Keep that momentum going! I'm around if you need a quick check-in.

> **User:** okay thanks!
>
> **Buddy** (ambiguity, release, read: ack; 0.4s): You're on the right track! Keep going and let me know if anything comes up.

<details><summary>Dream version (the owner's reference)</summary>

> **Buddy:** Hey, I can understand. Some tasks might feel huge. do u have an end goal for this task? What will that look like?

> **User:** This app will help me declutter my gallery while swiping. And each save gives me points. With those points I can build a cat sanctuary!
>
> **Buddy:** That sounds great! Every task has a simple core working/design. what would that be for this task?

> **User:** Hmmm for this, I need the swipe mechanism. Once that's built, others are additions.
>
> **Buddy:** Good! You've narrowed it down. Now what would be the first ever step? Even as simple as opening your laptop is valid.

> **User:** Hmmm I can start setting up expo on my phone and laptop.
>
> **Buddy:** Yes, that sounds like a plan. I'll be here if you wanna plan more. Now go on you.

> **User:** okay thanks!
>
> **Buddy:** (release)

</details>

### ambiguity_idk  (ambiguity, chip: unclear)

_Repeated idk: Buddy must narrow with two concrete options, never repeat the question._

Cause expected: `unclear` · saved: `unclear` · OK

> **Buddy** (ambiguity, open; 0.8s): Finishing the Nixly app sounds like a big win for you! I totally get how the first step can feel fuzzy. What would “done” look like for this project?
>
> - ⚠ ✗ warm_voice: two warm reactions in one opener ('big win', 'totally get')

> **User:** idk honestly
>
> **Buddy** (ambiguity, open, read: idk; 1.4s): Is it more that you’re unsure what the first feature should be, or that you’re unsure how to set up the environment?

> **User:** idk, all of it I guess
>
> **Buddy** (ambiguity, offer, read: idk; 2.0s): Want a tiny first move from me, or do you already know what you'll do?
>
> - ⚠ ✗ reacts_to_user: canned offer fallback: ignores 'all of it'
> - ⚠ ✗ warm_voice: canned offer fallback: ignores 'all of it'

> **User:** maybe the swipe thing?
>
> **Buddy** (ambiguity, release, read: own_plan; 1.1s): That sounds like a great start!
>
> - ⚠ ✗ follows_framework: 'maybe the swipe thing?' names a core: should ask for a tiny first move, not wrap up
> - ⚠ ✗ reacts_to_user: 'maybe the swipe thing?' names a core: should ask for a tiny first move, not wrap up

> **User:** I'll set up expo then
>
> **Buddy** (ambiguity, release, read: own_plan; 4.3s): Good plan!
>
> - ⚠ ✗ follows_framework: 'Good plan!' is too thin: doesn't say their plan back or that Buddy's around
> - ⚠ ✗ reacts_to_user: 'Good plan!' is too thin: doesn't say their plan back or that Buddy's around

> **User:** thanks bye
>
> **Buddy** (ambiguity, release, read: ack; 3.4s): You’ve got this—just let me know if anything comes up!

### ambiguity_switch_tired  (ambiguity, chip: unclear)

_Tapped unclear, reveals tiredness: switch to tired. No task step after that._

Cause expected: `tired` · saved: `tired` · OK

> **Buddy** (ambiguity, open; 1.2s): Finishing the Nixly app.  
It’s totally normal to feel a bit stuck at the start.  
What would “done” look like for this task?
>
> - ⚠ ✗ warm_voice: robotic fragment opener with line breaks; same 'totally normal' line again

> **User:** honestly I'm just exhausted today, I worked all day
>
> **Buddy** (fatigue, rest, read: new_cause; 0.6s): Sounds exhausting!  
Take the rest you need—I'll be here when you’re ready.

> **User:** yeah I just want to sleep
>
> **Buddy** (fatigue, release, read: own_plan; 1.4s): Got it, rest well!

> **User:** bye
>
> **Buddy** (fatigue, release, read: ack; 0.4s): Bye! Take care.
