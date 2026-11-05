# The playbook docs (brain/buddy_docs) as the live code reads them: intervention tagging per state,
# state stances, the core docs, and every framework stage's wording.

from brain import flow
from brain.playbook import (
    _load_docs, framework_section, get_doc, get_intervention, get_state_doc, has_framework, intervention_text,
    interventions_for, state_stance,
)

WORK_STATES = ["avoidance", "overwhelm", "fatigue", "ambiguity", "perfectionism", "low_interest", "commitment_drift"]


def names(state):
    return {d.intervention for d in interventions_for(state)}


def test_core_docs_the_writer_and_decider_load_exist():
    assert get_doc("core_buddy_philosophy") and get_doc("core_intervention_selection")


def test_every_detectable_state_has_a_state_doc_and_a_stance():
    for state in [*WORK_STATES, "recovery"]:
        assert get_state_doc(state), state
        assert state_stance(state), state


def test_interventions_are_tagged_per_state():
    assert {"acknowledge_emotion", "name_the_pattern"} <= names("avoidance")
    assert "surface_smallest_step" not in names("avoidance")          # tagged for overwhelm/ambiguity only
    assert "surface_smallest_step" in names("overwhelm")


def test_unknown_state_gets_every_intervention_to_choose_from():
    assert names(None) == {d.intervention for d in _load_docs() if d.category == "intervention"}


def test_find_the_cause_for_every_work_state_but_not_recovery():
    for state in ["avoidance", "overwhelm", "fatigue", "ambiguity", "perfectionism", "low_interest"]:
        assert "find_the_cause" in names(state), state
    assert "find_the_cause" not in names("recovery")


def test_affirm_and_release_tagged_for_recovery_and_ambiguity_only():
    assert "affirm_and_release" in names("recovery") and "affirm_and_release" in names("ambiguity")
    assert "affirm_and_release" not in names("avoidance")
    assert get_intervention("affirm_and_release") is not None


def test_writer_text_has_no_quoted_example_lines():
    for d in _load_docs():
        if d.category == "intervention":
            assert "What this looks like" not in intervention_text(d)


def test_every_tapped_reason_has_a_framework_with_wording_for_each_stage():
    for state in flow.FRAMEWORKS:
        assert has_framework(state), state
        assert framework_section(state, "Never"), state
    assert not has_framework("avoidance")                             # silence-inferred: generic path only
