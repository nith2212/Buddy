# Labeled single messages for the "read their message" call (PIVOTS.md build plan, step 4).
# The read call does not exist yet; these are written first so its accuracy can be measured the
# moment it does, per field and per model. Each case is what Buddy just said, what the user said
# back, and the one right reading.
#
# kind:
#   idk        doesn't know / no answer to give
#   answer     answers Buddy's question with content, but confirms nothing
#   confirm    agrees with the cause Buddy offered, or clearly names it (cause = the key)
#   reject     says Buddy's read is wrong
#   unsure     half-agrees, "maybe", "kinda", picks both, or hedges
#   own_plan   states what THEY will do, their own idea
#   accept     agrees to the step Buddy just offered ("okay I can do that")
#   wants_move asks Buddy for a step / help choosing
#   ack        a bare thanks / sign-off, nothing to answer
#   new_cause  reveals a different cause than the one being discussed (cause = the key)
#   bigger     distress beyond work: step back, stop probing
#
# Causes: unclear, too_much, afraid, bored, tired.

GUESS_FEAR = "Is it more that you're worried others will see it and think it's not good?"
GUESS_SKILL = "Is it more that you're not sure you know how to build some parts yet?"
ASK_FEAR = "Finish Nixly app is due in about 3 days. What feels risky about it?"
ASK_GOAL = "What would Finish Nixly app look like when it's done?"
ASK_CORE = "What's the one part the rest of the app depends on?"
ASK_STEP = "What's the very first move? Even opening the laptop counts."
ASK_TINY = "What's the smallest, even silliest, first move on Build the game app?"
OFFER_TINY = "What about just opening VS Code and making a folder for it?"
ASK_WHY = "Why does Update the client invoices need doing at all?"
ASK_BORING = "Is it more boring, or more pointless?"
ASK_PURPOSE = "What could it give you, a skill, money, someone's trust?"
OFFER_LIGHTEN = "Want to try 20 minutes then a reward, or put music on while you do it?"
ASK_TIRED = "How was your day?"
RELEASE = "Love that plan. I'm here if you get stuck."
OFFER_CHOICE = "Want a tiny first move, or do you already know what you'll do?"

READ_CASES = [
    # idk
    ("perfectionism", ASK_FEAR, "idk bro", "idk", None),
    ("perfectionism", ASK_FEAR, "no idea honestly", "idk", None),
    ("ambiguity", ASK_GOAL, "i dont knowww", "idk", None),
    ("ambiguity", ASK_CORE, "idk, all of it I guess", "idk", None),
    ("ambiguity", ASK_STEP, "not sure tbh", "idk", None),
    ("overwhelm", ASK_TINY, "Umm idk honestly. The app, the game, the code, everything is overwhelming and big",
     "idk", None),
    ("low_interest", ASK_WHY, "dunno", "idk", None),
    ("low_interest", ASK_PURPOSE, "nothing comes to mind", "idk", None),
    ("ambiguity", ASK_CORE, "hmm", "idk", None),

    # answer (content, but no confirmation)
    ("ambiguity", ASK_GOAL, "This app will help me declutter my gallery while swiping. And each save gives me "
     "points. With those points I can build a cat sanctuary!", "answer", None),
    ("ambiguity", ASK_CORE, "Hmmm for this, I need the swipe mechanism. Once that's built, others are additions.",
     "answer", None),
    ("perfectionism", ASK_FEAR, "people will think it's messy and unprofessional", "answer", None),
    ("perfectionism", ASK_FEAR, "my seniors will review it", "answer", None),
    ("low_interest", ASK_WHY, "I need to do this because of client requirements.", "answer", None),
    ("low_interest", ASK_WHY, "client requirements", "answer", None),
    ("low_interest", ASK_PURPOSE, "No I mean I already know everything about this task, which is why ik it's "
     "useless and I am not learning anything new. Ugh", "answer", None),
    ("low_interest", ASK_PURPOSE, "well maybe I can learn this new thing in it. I haven't worked on it before.",
     "answer", None),
    ("fatigue", ASK_TIRED, "Hey I worked so hard and long this day at work", "answer", None),
    ("overwhelm", OFFER_TINY, "That's all?", "answer", None),

    # confirm
    ("perfectionism", GUESS_FEAR, "Yes, I'm worried it won't look good to others", "confirm", "afraid"),
    ("perfectionism", GUESS_FEAR, "yeah that's exactly it", "confirm", "afraid"),
    ("perfectionism", GUESS_FEAR, "yes", "confirm", "afraid"),
    ("perfectionism", GUESS_FEAR, "100%", "confirm", "afraid"),
    ("perfectionism", GUESS_FEAR, "haan exactly", "confirm", "afraid"),
    ("perfectionism", GUESS_SKILL, "yeah I've never done a swipe animation before", "confirm", "unclear"),
    ("low_interest", ASK_BORING, "It's more like boring.", "confirm", "bored"),
    ("low_interest", ASK_BORING, "pointless", "confirm", "bored"),
    ("low_interest", ASK_BORING, "It's more like pointless", "confirm", "bored"),
    ("ambiguity", "Is it more that you're not sure what the first step even is?", "yep thats it", "confirm",
     "unclear"),
    ("overwhelm", "Is it more that there's just so much of it?", "yes way too much", "confirm", "too_much"),
    ("fatigue", "Is it more that you're just drained today?", "yeah totally drained", "confirm", "tired"),

    # reject
    ("perfectionism", GUESS_FEAR, "no, not really", "reject", None),
    ("perfectionism", GUESS_FEAR, "nah it's not that", "reject", None),
    ("perfectionism", GUESS_SKILL, "no I know how to code it", "reject", None),
    ("ambiguity", "Is it more that you're not sure what the first step even is?", "no I know the steps", "reject",
     None),
    ("overwhelm", "Is it more that there's just so much of it?", "not really, it's small actually", "reject", None),

    # unsure
    ("perfectionism", GUESS_SKILL, "Yeah, maybe", "unsure", None),
    ("perfectionism", GUESS_FEAR, "kinda", "unsure", None),
    ("perfectionism", GUESS_FEAR, "kinda?", "unsure", None),
    ("perfectionism", GUESS_FEAR, "Hmm yeah maybe", "unsure", None),
    ("overwhelm", "Is it more that there's just so much of it?", "both I guess", "unsure", None),
    ("perfectionism", "Is it not knowing how, or how others will see it?", "the latter", "confirm", "afraid"),
    ("perfectionism", "Is it not knowing how, or how others will see it?", "both", "unsure", None),
    ("perfectionism", GUESS_FEAR, "yeah but also I'm not sure I can do it", "unsure", None),
    ("perfectionism", GUESS_FEAR, "maybe? idk", "unsure", None),
    ("ambiguity", "Is it more that you're not sure what the first step even is?", "sort of", "unsure", None),

    # own_plan
    ("ambiguity", ASK_STEP, "Hmmm I can start setting up expo on my phone and laptop.", "own_plan", None),
    ("ambiguity", ASK_STEP, "I'll set up expo then", "own_plan", None),
    ("perfectionism", OFFER_CHOICE, "nah I'd rather polish the README first, that's my plan", "own_plan", None),
    ("perfectionism", OFFER_CHOICE, "I'll just work on the RAG documents", "own_plan", None),
    ("overwhelm", ASK_TINY, "I could just open the repo and read my old notes", "own_plan", None),
    ("overwhelm", OFFER_TINY, "Okay, I can do that", "accept", None),
    ("overwhelm", OFFER_TINY, "Hmm okie I can do that", "accept", None),
    ("overwhelm", OFFER_TINY, "fine, I'll make the folder", "own_plan", None),
    ("perfectionism", "Want to try a deliberately rough version no one sees? What do you say?",
     "Haha yeah that sounds fun.", "accept", None),
    ("low_interest", OFFER_LIGHTEN, "Hmm okay I've been meaning to catch up on the TV show I've been watching.",
     "own_plan", None),
    ("low_interest", OFFER_LIGHTEN, "fine whatever, I'll do 20 mins and then watch my show", "own_plan", None),
    ("low_interest", ASK_WHY, "honestly it's optional, I'll just drop it for now", "own_plan", None),
    ("low_interest", ASK_WHY, "Ughh unfortunately I HAVE to do it.", "reject", None),          # phone test
    ("low_interest", ASK_BORING, "I don't like it bro", "confirm", "bored"),
    ("fatigue", OFFER_CHOICE, "I'll just rename the file tonight, that's it", "own_plan", None),

    # wants_move
    ("perfectionism", OFFER_CHOICE, "yeah give me a tiny one", "wants_move", None),
    ("perfectionism", OFFER_CHOICE, "idk, you pick", "wants_move", None),
    ("fatigue", OFFER_CHOICE, "maybe just a tiny thing", "wants_move", None),
    ("ambiguity", OFFER_CHOICE, "tiny move please", "wants_move", None),
    ("ambiguity", OFFER_CHOICE, "maybe the swipe thing?", "answer", None),
    ("overwhelm", ASK_TINY, "can you just tell me what to do first?", "wants_move", None),

    # ack
    ("ambiguity", RELEASE, "okay thanks!", "ack", None),
    ("ambiguity", RELEASE, "thanks bye", "ack", None),
    ("perfectionism", RELEASE, "Okay! I'll try that!", "ack", None),
    ("fatigue", "Rest up, I'm here when you're ready.", "Thanks bye", "ack", None),
    ("overwhelm", RELEASE, "Ohhh okay, thanks!", "ack", None),
    ("low_interest", RELEASE, "ok", "ack", None),
    ("low_interest", RELEASE, "ok bye", "ack", None),
    ("perfectionism", RELEASE, "Fine bro I'll do that. Bye", "ack", None),

    # new_cause
    ("ambiguity", ASK_GOAL, "honestly I'm just exhausted today, I worked all day", "new_cause", "tired"),
    ("ambiguity", ASK_CORE, "tbh I'm scared it'll look amateur", "new_cause", "afraid"),
    ("perfectionism", ASK_FEAR, "it's not fear, it's just so boring", "new_cause", "bored"),
    ("low_interest", ASK_WHY, "I don't even know where I'd begin", "new_cause", "unclear"),
    ("overwhelm", ASK_TINY, "I'm too tired to even think about it", "new_cause", "tired"),
    ("fatigue", ASK_TIRED, "it's fine, I'm just scared of messing it up", "new_cause", "afraid"),

    # bigger than work
    ("perfectionism", ASK_FEAR, "honestly it's not the task. I feel like a failure at everything lately and I "
     "can't stop crying", "bigger", None),
    ("fatigue", ASK_TIRED, "I haven't slept in days, my dad's in the hospital", "bigger", None),
    ("ambiguity", ASK_GOAL, "what's the point of anything anymore", "bigger", None),
    ("low_interest", ASK_WHY, "I just feel numb all the time lately", "bigger", None),

    # tricky: sarcasm, typos, mixed
    ("perfectionism", GUESS_FEAR, "oh sure, totally, as if that's the problem", "reject", None),
    ("ambiguity", ASK_STEP, "i'll opne vscode and make teh folder", "own_plan", None),
    ("perfectionism", GUESS_FEAR, "lol yeah", "confirm", "afraid"),
]
