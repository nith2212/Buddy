from brain.playbook import get_playbook


def test_known_state_includes_core_state_and_matching_interventions():
    text = get_playbook("avoidance")
    assert "Core Principle: Buddy's Philosophy" in text
    assert "Core Principle: Intervention Selection Logic" in text
    assert "State: Avoidance" in text
    assert "Intervention: Acknowledge the Emotion First" in text  # designed_for_states includes avoidance
    assert "Intervention: Name the Pattern" in text  # also tagged for avoidance


def test_intervention_not_tagged_for_state_is_excluded():
    text = get_playbook("avoidance")
    # designed_for_states: [overwhelm, ambiguity] — must not leak into avoidance's playbook
    assert "Intervention: Surface the Smallest Step" not in text


def test_unknown_state_falls_back_to_core_only():
    text = get_playbook("totally_made_up_state")
    assert "Core Principle: Buddy's Philosophy" in text
    assert "State:" not in text


def test_each_real_state_returns_nonempty_playbook():
    for state in ["ambiguity", "avoidance", "commitment_drift", "fatigue", "overwhelm", "recovery"]:
        text = get_playbook(state)
        assert text.strip(), f"empty playbook for state={state}"
        assert f"State: {state.replace('_', ' ').title()}" in text or "State:" in text
