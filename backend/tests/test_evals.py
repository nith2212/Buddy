# The eval harness itself (no Groq calls): scenario data is well-formed and the
# mechanical checks flag what they should.

from brain.state_detection import EMOTION_TO_STATE
from evals.read_cases import READ_CASES
from evals.run import CRITERIA, load_frameworks, mechanical
from evals.scenarios import SCENARIOS

KINDS = {"idk", "answer", "confirm", "reject", "unsure", "own_plan", "wants_move", "ack", "new_cause", "bigger"}


def test_scenarios_are_well_formed():
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids))
    for s in SCENARIOS:
        assert s["chip"] in EMOTION_TO_STATE and EMOTION_TO_STATE[s["chip"]] == s["state"]
        assert s["user"] and s["task"]["title"]
        assert s["expect_cause"] in (None, *EMOTION_TO_STATE)
        assert len(s.get("dream", [])) <= len(s["user"]) + 1


def test_read_cases_are_labeled():
    for state, buddy, user, kind, cause in READ_CASES:
        assert buddy and user and kind in KINDS
        assert (cause is not None) == (kind in ("confirm", "new_cause"))
        assert cause in (None, *EMOTION_TO_STATE)


def test_every_scenario_state_has_a_framework():
    shared, states = load_frameworks()
    assert "Shared skeleton" in shared and "Example conversations" not in "".join(states.values())
    assert {s["state"] for s in SCENARIOS} <= set(states)
    assert CRITERIA


def test_mechanical_flags():
    assert mechanical("Relax, trust me it's easy.", [], False) == ["banned_phrase"]
    assert mechanical("What is it? Why now?", [], False) == ["too_many_questions"]
    assert mechanical("A. B. C. D.", [], False) == ["too_long"]
    assert mechanical("Do it by 9pm.", [], False) == ["clock_time"]
    assert "repeated_opener" in mechanical("You're working on Nixly, so go.", ["You're working on Nixly today."], False)
    assert "repeats_earlier" in mechanical("Open the folder now.", ["Open the folder now!"], False)
    assert mechanical("Love that plan, I'm here.", [], True) == []
    assert mechanical("Love that plan, ready?", [], True) == ["question_in_release"]
    # warm reactions in the owner's voice are fine
    assert mechanical("I get it! A cat sanctuary sounds great.", [], False) == []
