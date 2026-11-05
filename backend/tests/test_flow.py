# The stage machine (brain/flow.py) walked through the developer's dream conversations
# (docs/state_frameworks.md), with the reading each user line should get. No model calls.

import pytest

from brain import flow
from brain.flow import Reading, next_stage
from brain.playbook import framework_section


def walk(state, readings):
    """Run readings through the table from the opener; return the stages Buddy lands on and the saved cause."""
    stage, tries, stages, saved = flow.FRAMEWORKS[state].first, 1, [], []
    for r in readings:
        step = next_stage(state, stage, r, tries)
        tries = tries + 1 if (step.state, step.stage) == (state, stage) else 1
        state, stage = step.state, step.stage
        stages.append(stage)
        if step.save_cause and not saved:  # the agent saves a cause at most once per session
            saved.append(step.save_cause)
    return stages, saved


R = Reading


@pytest.mark.parametrize("state,readings,stages,saved", [
    # Nixly, don't know where to start: goal -> core -> their step -> release
    ("ambiguity", [R("answer"), R("answer"), R("own_plan"), R("ack")],
     ["core", "first_step", "release", "release"], ["unclear"]),
    # scared: idk -> two guesses -> maybe (stay) -> yes -> rough version -> "sounds fun"
    ("perfectionism", [R("idk"), R("unsure"), R("confirm", "afraid"), R("own_plan")],
     ["narrow", "narrow", "reframe", "release"], ["afraid"]),
    # tired: what drained them -> rest -> bye
    ("fatigue", [R("answer"), R("ack")], ["rest", "release"], ["tired"]),
    # tired but wants to: offer -> tiny move -> "okay I'll do that"
    ("fatigue", [R("wants_move"), R("wants_move"), R("own_plan")], ["offer", "move", "release"], ["tired"]),
    # too big: idk -> one micro step -> "that's all?" (stay) -> accept -> thanks
    ("overwhelm", [R("idk"), R("answer"), R("own_plan"), R("ack")],
     ["micro", "micro", "release", "release"], ["too_much"]),
    # boring: why -> boring or pointless -> boring -> lighten -> picks the TV show
    ("low_interest", [R("answer"), R("confirm", "bored", "boring"), R("own_plan")],
     ["narrow", "lighten", "release"], ["bored"]),
    # pointless, no purpose found -> lighten
    ("low_interest", [R("answer"), R("confirm", "bored", "pointless"), R("answer", flavor="none")],
     ["narrow", "purpose", "lighten"], ["bored"]),
    # pointless, purpose found -> theirs -> still dislikes it -> accept and release
    ("low_interest", [R("answer"), R("confirm", "bored", "pointless"), R("answer", flavor="found"), R("answer")],
     ["narrow", "purpose", "own_reason", "release"], ["bored"]),
])
def test_dream_conversations_walk_the_frameworks(state, readings, stages, saved):
    assert walk(state, readings) == (stages, saved)


def test_switching_cause_mid_chat_goes_to_that_framework_and_saves_it():
    step = next_stage("ambiguity", "open", R("new_cause", "tired"), 1)
    assert (step.state, step.stage, step.save_cause) == ("fatigue", "rest", "tired")


def test_naming_the_cause_already_being_discussed_is_a_confirmation_not_a_switch():
    step = next_stage("perfectionism", "narrow", R("new_cause", "afraid"), 1)
    assert (step.state, step.stage, step.save_cause) == ("perfectionism", "reframe", "afraid")


def test_bigger_than_work_is_sticky():
    step = next_stage("overwhelm", "micro", R("bigger"), 1)
    assert step.stage == "step_back"
    assert next_stage("overwhelm", "step_back", R("own_plan"), 1).stage == "step_back"


def test_unclear_reading_stays_and_two_tries_offer_the_choice():
    assert next_stage("ambiguity", "core", R("unclear"), 1) == flow.Step("ambiguity", "core", modifier="unclear")
    assert next_stage("ambiguity", "core", R("unclear"), 2).stage == "offer"


def test_naming_a_part_after_the_offer_asks_for_their_first_step_instead_of_wrapping_up():
    # eval 2026-11-04: "maybe the swipe thing?" after the offer was read as a plan and Buddy wrapped up
    step = next_stage("ambiguity", "offer", R("answer", fact="the swipe thing"), 1)
    assert (step.stage, step.note) == ("first_step", ("core", "the swipe thing"))
    assert next_stage("ambiguity", "offer", R("wants_move"), 1).stage == "suggest"
    assert next_stage("overwhelm", "offer", R("answer"), 1).stage == flow.FRAMEWORKS["overwhelm"].tiny


def test_reframe_declined_without_their_own_plan_offers_the_choice():
    assert next_stage("perfectionism", "reframe", R("reject"), 1).stage == "offer"
    assert next_stage("perfectionism", "offer", R("wants_move"), 1).stage == "reframe"


@pytest.mark.parametrize("message,kind", [
    ("idk bro", "idk"), ("dunno", "idk"), ("not sure tbh", "idk"), ("hmm", "idk"),
    ("thanks bye", "ack"), ("okay thanks!", "ack"),
    ("honestly it's not the task, I can't stop crying", "bigger"), ("my dad's in the hospital", "bigger"),
])
def test_easy_cases_are_read_without_a_model(message, kind):
    assert flow.pattern_read(message, "What feels risky?").kind == kind


@pytest.mark.parametrize("message", ["okay", "sure", "the latter", "idk, all of it I guess", "kinda?"])
def test_everything_else_goes_to_the_model(message):
    assert flow.pattern_read(message, "Want a tiny first move, or do you know what you'll do?") is None


def test_every_stage_has_wording_in_the_docs():
    for state, fw in flow.FRAMEWORKS.items():
        stages = {fw.first, fw.switch_entry, fw.tiny, *fw.on.values(), *fw.by_flavor.values(),
                  *(s for s, _ in fw.on)} - set(flow.GENERIC)
        for stage in stages:
            assert framework_section(state, stage), f"{state}: no '## {stage}' section"
        assert framework_section(state, "Never")
    for heading in ("Voice", "Release", "Step back", "Offer", "Followup", "If they said idk", "If they were unsure",
                    "If they said no", "If it was unclear", "If they answered but you stay here",
                    "If they took your move", "Ask the reason"):
        assert framework_section("shared", heading), heading


def test_clear_tiredness_switches_without_a_model_but_not_inside_the_tired_framework():
    assert flow.pattern_read("honestly I'm just exhausted today", "What would done look like?", "ambiguity") == \
        Reading("new_cause", "tired", source="pattern")
    assert flow.pattern_read("I'm exhausted", "How was your day?", "fatigue") is None


def test_describing_the_cause_unprompted_is_an_answer_not_a_confirmation():
    step = next_stage("perfectionism", "open", R("new_cause", "afraid"), 1)
    assert (step.stage, step.save_cause) == ("confirm", None)


# ── phone test, 2026-11-04 ────────────────────────────────────────────────────────

def test_taking_buddys_move_wraps_up_without_crediting_them():
    # "Hmm okie I can do that" to Buddy's micro-step: release, cause saved, but no "their plan" note
    # (that note made Buddy say "you picked it yourself!")
    step = next_stage("overwhelm", "micro", R("accept", fact="I can open the 3D file"), 1)
    assert (step.stage, step.modifier, step.save_cause, step.note) == ("release", "accepted", "too_much", None)
    own = next_stage("overwhelm", "micro", R("own_plan", fact="I'll sketch one shape"), 1)
    assert own.note == ("their plan", "I'll sketch one shape") and own.modifier is None


def test_sure_to_the_offer_means_give_me_one_not_goodbye():
    for state in flow.FRAMEWORKS:
        step = next_stage(state, "offer", R("accept"), 1)
        assert step.stage != "release", state


def test_correcting_buddy_after_the_wrap_up_is_a_followup():
    assert next_stage("overwhelm", "release", R("reject"), 1).stage == "followup"
    assert next_stage("overwhelm", "followup", R("accept"), 1).stage == "release"


def test_the_manager_report_chat_never_lands_on_a_persuading_stage():
    # "I HAVE to do it" (a no to "could it be dropped?") -> "I don't like it" -> "it's pointless"
    # -> "just the maintenance report" (a no to "what could it give you?")
    stages, saved = walk("low_interest", [R("reject"), R("confirm", "bored"), R("answer")])
    assert stages == ["narrow", "lighten", "lighten"] and saved == ["bored"]
    stages, _ = walk("low_interest", [R("reject"), R("answer", flavor="pointless"), R("reject")])
    assert stages == ["narrow", "purpose", "lighten"]
