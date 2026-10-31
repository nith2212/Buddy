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


def test_new_cause_states_have_state_doc_and_find_the_cause():
    for state, heading in [("perfectionism", "State: Fear of Doing It Badly"),
                           ("low_interest", "State: Boring or Pointless")]:
        text = get_playbook(state)
        assert heading in text
        assert "Intervention: Find the Cause" in text
        assert "Intervention: Surface the Smallest Step" in text


def test_find_the_cause_available_for_every_work_state_but_not_recovery():
    for state in ["avoidance", "overwhelm", "fatigue", "ambiguity", "perfectionism", "low_interest"]:
        assert "Intervention: Find the Cause" in get_playbook(state), state
    assert "Intervention: Find the Cause" not in get_playbook("recovery")


def test_affirm_and_release_tagged_for_recovery_and_ambiguity_only():
    assert "Intervention: Affirm and Release" in get_playbook("recovery")
    assert "Intervention: Affirm and Release" in get_playbook("ambiguity")
    assert "Intervention: Affirm and Release" not in get_playbook("avoidance")


def test_writer_text_has_no_quoted_example_lines():
    from brain.playbook import _load_docs, intervention_text
    for d in _load_docs():
        if d.category == "intervention":
            assert "What this looks like" not in intervention_text(d)
