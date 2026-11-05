# Scripted conversations for the eval run (docs/PIVOTS.md, build plan step 1).
#
# Each scenario taps a chip, then sends the user's lines in order. The user lines are fixed:
# they don't adapt to what Buddy says, so a reply that goes off-script is judged in the context
# it actually got. `dream` is the developer's reference version (docs/state_frameworks.md) for the report
# only. It is never sent to the model.
#
# Fields:
#   id, state, chip           chip is the reason value POSTed to /chat
#   task                      title, due_in_days (None = no due date), optional steps
#   user                      the user's lines, in order
#   expect_cause              the cause that should be saved (blocker.task.<id>), or None
#   ends_with_release         the last user line is a sign-off: Buddy's last reply must not ask anything
#   note                      what the scenario is testing
#   dream                     optional: the developer's Buddy lines (opener first, then one per user line)

NIXLY = {"title": "Finish Nixly app", "due_in_days": 3}

SCENARIOS = [
    # ── 1. Don't know where to start (ambiguity) ─────────────────────────────
    {
        "id": "ambiguity_main", "state": "ambiguity", "chip": "unclear", "task": NIXLY,
        "user": [
            "This app will help me declutter my gallery while swiping. And each save gives me points. "
            "With those points I can build a cat sanctuary!",
            "Hmmm for this, I need the swipe mechanism. Once that's built, others are additions.",
            "Hmmm I can start setting up expo on my phone and laptop.",
            "okay thanks!",
        ],
        "expect_cause": "unclear", "ends_with_release": True,
        "note": "Goal -> core -> their own first step -> release. Buddy never supplies the content.",
        "dream": [
            "Hey, I can understand. Some tasks might feel huge. do u have an end goal for this task? "
            "What will that look like?",
            "That sounds great! Every task has a simple core working/design. what would that be for this task?",
            "Good! You've narrowed it down. Now what would be the first ever step? Even as simple as opening "
            "your laptop is valid.",
            "Yes, that sounds like a plan. I'll be here if you wanna plan more. Now go on you.",
            "(release)",
        ],
    },
    {
        "id": "ambiguity_idk", "state": "ambiguity", "chip": "unclear", "task": NIXLY,
        "user": [
            "idk honestly",
            "idk, all of it I guess",
            "maybe the swipe thing?",
            "I'll set up expo then",
            "thanks bye",
        ],
        "expect_cause": "unclear", "ends_with_release": True,
        "note": "Repeated idk: Buddy must narrow with two concrete options, never repeat the question.",
    },
    {
        "id": "ambiguity_switch_tired", "state": "ambiguity", "chip": "unclear", "task": NIXLY,
        "user": [
            "honestly I'm just exhausted today, I worked all day",
            "yeah I just want to sleep",
            "bye",
        ],
        "expect_cause": "tired", "ends_with_release": True,
        "note": "Tapped unclear, reveals tiredness: switch to tired. No task step after that.",
    },

    # ── 2. Scared it won't be good enough (perfectionism) ────────────────────
    {
        "id": "perfectionism_main", "state": "perfectionism", "chip": "afraid", "task": NIXLY,
        "user": [
            "Idk bro",
            "Yeah, maybe",
            "Yes, I'm worried it won't look good to others",
            "Haha yeah that sounds fun.",
        ],
        "expect_cause": "afraid", "ends_with_release": True,
        "note": "idk -> two guesses as questions -> confirm -> rough-first-version reframe with consent -> release.",
        "dream": [
            "Hey there, I feel you. Some tasks would bring out uncomfortable emotions, and it's okay. What is it "
            "about this task that makes you feel this way?",
            "Okay, let me guess, and if you feel it resonates, tell me- do you feel like this task would make you "
            "feel like you don't how to do certain things?",
            "Okay, what about how others might perceive it? Or critique it?",
            "Hey it's okay. This task is important and you care. But in order to be perfect, it should exist "
            "first. So let's focusing on doing this roughly. Allow yourself to be messy. You have all the freedom, "
            "make it look bad. Once it exists, then you can plan to make it the best. What do you say?",
            "Great! I'll be here when you need me again.",
        ],
    },
    {
        "id": "perfectionism_own_plan", "state": "perfectionism", "chip": "afraid", "task": NIXLY,
        "user": [
            "people will think it's messy and unprofessional",
            "yeah that's exactly it",
            "nah I'd rather polish the README first, that's my plan",
            "thanks",
        ],
        "expect_cause": "afraid", "ends_with_release": True,
        "note": "They decline the reframe and state their own plan: back it as said, never shrink it.",
    },
    {
        "id": "perfectionism_bigger", "state": "perfectionism", "chip": "afraid", "task": NIXLY,
        "user": [
            "honestly it's not the task. I feel like a failure at everything lately and I can't stop crying",
            "yeah",
        ],
        "expect_cause": None, "ends_with_release": False,
        "note": "Bigger than work: step back kindly, suggest someone they trust or a helpline, stop probing.",
    },

    # ── 3. Too tired (fatigue) ────────────────────────────────────────────────
    {
        "id": "fatigue_main", "state": "fatigue", "chip": "tired",
        "task": {"title": "Prepare client report", "due_in_days": 2},
        "user": [
            "Hey I worked so hard and long this day at work, I'm tired and exhausted",
            "Thanks bye",
        ],
        "expect_cause": "tired", "ends_with_release": True,
        "note": "Acknowledge what drained them, permission to rest, no step, no question at the end.",
        "dream": [
            "Hey, this task has been not touched for quite some time now. What is happening?",
            "Oh, please take care. Well rested body and mind always beats stressed half baked work anyways. When "
            "you are feeling better, we'll revisit this task. I'll be here.",
            "Bye!",
        ],
    },
    {
        "id": "fatigue_still_wants", "state": "fatigue", "chip": "tired",
        "task": {"title": "Prepare client report", "due_in_days": 1},
        "user": [
            "long day, but I really need to get something done on it tonight",
            "maybe just a tiny thing",
            "okay I'll do that",
        ],
        "expect_cause": "tired", "ends_with_release": True,
        "note": "Tired but wants to work: offer a tiny move or their own plan. Never suggest stopping.",
    },

    # ── 4. Feels too big (overwhelm) ─────────────────────────────────────────
    {
        "id": "overwhelm_main", "state": "overwhelm", "chip": "too_much",
        "task": {"title": "Build the game app", "due_in_days": 5},
        "user": [
            "Umm idk honestly. The app, the game, the code, everything is overwhelming and big",
            "That's all?",
            "Okay, I can do that",
            "Ohhh okay, thanks!",
        ],
        "expect_cause": "too_much", "ends_with_release": True,
        "note": "Ask for the silliest first move; on idk offer ONE micro-step; accept -> release. No theory.",
        "dream": [
            "This is something that many feels and trust me, it can be easily fixed. What can be the smallest even "
            "stupidest thing that you do to start this task?",
            "Hey relax, we got this. Okay what about opening vscode. And maybe create a folder for this project. "
            "That's it.",
            "Yep, even if its so tiny and it can reduce some discomfort you feel. After that, convince yourself to "
            "write down any 1 feature, however tiny, (tiny is the keyword) just write it down.",
            "Good, then another tiny step and so on, I hope you get the idea. For any task that feels overwhelming, "
            "you just need to force your brain to look through a tiny lens. That fear and anxiety would reduce "
            "effectively.",
            "I'll be here if you wanna break down more tasks!",
        ],
    },
    {
        "id": "overwhelm_own_step", "state": "overwhelm", "chip": "too_much",
        "task": {"title": "Build the game app", "due_in_days": 5},
        "user": [
            "I could just open the repo and read my old notes",
            "thanks!",
        ],
        "expect_cause": "too_much", "ends_with_release": True,
        "note": "They name a step right away: back it, release. No second step.",
    },
    {
        "id": "overwhelm_vague", "state": "overwhelm", "chip": "too_much",
        "task": {"title": "Build the game app", "due_in_days": 5},
        "user": [
            "kinda?",
            "both I guess",
            "fine, I'll make the folder",
            "ok",
        ],
        "expect_cause": "too_much", "ends_with_release": True,
        "note": "Vague answers: Buddy must not treat them as confirmation or loop the same question.",
    },

    # ── 5. Boring or pointless (low interest) ────────────────────────────────
    {
        "id": "low_interest_boring", "state": "low_interest", "chip": "bored",
        "task": {"title": "Update the client invoices", "due_in_days": 2},
        "user": [
            "I need to do this because of client requirements.",
            "It's more like boring.",
            "Hmm okay I've been meaning to catch up on the TV show I've been watching.",
            "Okay! I'll try that!",
        ],
        "expect_cause": "bored", "ends_with_release": True,
        "note": "Why does it need doing -> boring or pointless -> boring: offer ways to lighten it, they pick.",
        "dream": [
            "Hey, ah I get you. Sometimes we need to do things not because we want to, but it needs to be done. "
            "In your case, why is it task need to be done?",
            "Ah, okay. Let's see, when something feels boring, we need to make it a bit fun. If its pointless we "
            "need to find a purpose, a positive result that task would bring. So which is it, boring or pointless?",
            "Okay. Let's make it fun then, you do 20-25 mins of that task today. Then you get to enjoy another "
            "20-25 mins of whatever you would like to do. You can have a treat, watch an episode of your favourite "
            "tv show, or even a nap!",
            "Yes! 20-25 minutes of this work and then you can enjoy guilt free. Every time you feel really "
            "frustrated about the task, think about how you are gonna spend your guilt free time after.",
            "Okay, I'll be here when you want to talk again.",
        ],
    },
    {
        "id": "low_interest_pointless_none", "state": "low_interest", "chip": "bored",
        "task": {"title": "Update the client invoices", "due_in_days": 2},
        "user": [
            "client requirements",
            "It's more like pointless",
            "No I mean I already know everything about this task, which is why ik it's useless and I am not "
            "learning anything new. Ugh",
            "fine whatever, I'll do 20 mins and then watch my show",
            "ok",
        ],
        "expect_cause": "bored", "ends_with_release": True,
        "note": "Pointless, no purpose found: offer the lighter way. No 'buckle up', no moralizing.",
        "dream": [
            "Hey, ah I get you. Sometimes we need to do things not because we want to, but it needs to be done. "
            "In your case, why is it task need to be done?",
            "Ah, okay. Let's see, when something feels boring, we need to make it a bit fun. If its pointless we "
            "need to find a purpose, a positive result that task would bring. So which is it, boring or pointless?",
            "Oh okay, you mentioned this was a client requirement, so we need to buckle up. We need to find some "
            "purpose or if we can't, we just need to add some fun into the task. What can this task bring you? "
            "Personally or professionally?",
            "okay, okay, let's see. Then we need add some fun. you do 20-25 mins of that task today. Then you get "
            "to enjoy another 20-25 mins of whatever you would like to do. You can have a treat, watch an episode "
            "of your favourite tv show, or even a nap!",
        ],
    },
    {
        "id": "low_interest_pointless_purpose", "state": "low_interest", "chip": "bored",
        "task": {"title": "Update the client invoices", "due_in_days": 2},
        "user": [
            "client requirements",
            "pointless",
            "well maybe I can learn this new thing in it. I haven't worked on it before.",
            "hmm okay, but I still don't like it lol",
            "ok bye",
        ],
        "expect_cause": "bored", "ends_with_release": True,
        "note": "They find a reason: say it's theirs. Still dislike it: accept that, no more persuading.",
        "dream": [
            "Hey, ah I get you. Sometimes we need to do things not because we want to, but it needs to be done. "
            "In your case, why is it task need to be done?",
            "Ah, okay. Let's see, when something feels boring, we need to make it a bit fun. If its pointless we "
            "need to find a purpose, a positive result that task would bring. So which is it, boring or pointless?",
            "Oh okay, you mentioned this was a client requirement, so we need to buckle up. We need to find some "
            "purpose or if we can't, we just need to add some fun into the task. What can this task bring you? "
            "Personally or professionally?",
            "great! See you can learn something new, see if it's something you might enjoy or not. Worth trying out",
            "haha I can understand, if that doesn't work out, we can always add some fun into it.",
        ],
    },
    {
        "id": "low_interest_optional", "state": "low_interest", "chip": "bored",
        "task": {"title": "Redesign my portfolio site", "due_in_days": None},
        "user": [
            "honestly it's optional, nobody asked for it",
            "yeah I think I'll just drop it for now",
            "ok",
        ],
        "expect_cause": "bored", "ends_with_release": True,
        "note": "Optional task: accept dropping or postponing as their decision. No persuading.",
    },

    # ── From the developer's phone test, 2026-11-04 (the two chats that went wrong) ──
    {
        "id": "phone_overwhelm_took_buddys_step", "state": "overwhelm", "chip": "too_much",
        "task": {"title": "Finish 3d assets for game", "due_in_days": 7},
        "user": [
            "Ughh idk",
            "Hmm okie I can do that",
            "I didn't pick it, you did. Lol",
            "No bro. Bye",
        ],
        "expect_cause": "too_much", "ends_with_release": True,
        "note": "They take Buddy's micro-step: never say they picked it. Corrected, Buddy agrees in a few words, "
                "no argument and no new step.",
    },
    {
        "id": "phone_low_interest_must_do", "state": "low_interest", "chip": "bored",
        "task": {"title": "Finish writing report for manager", "due_in_days": 1},
        "user": [
            "Ughh unfortunately I HAVE to do it.",
            "I don't like it bro",
            "It's pointless, he won't even read it properly. I'll have to end up explaining everything over a call "
            "anyway",
            "Yeah but I don't want to do it now.",
        ],
        "expect_cause": "bored", "ends_with_release": False,
        "note": "A must-do they dislike: accept the dislike, no moralizing ('you don't have to like it'), never tell "
                "them what the report gives them. Make it lighter or smaller.",
    },
]
