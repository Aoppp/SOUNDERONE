from app.agent.responses import OUT_OF_SCOPE_RESPONSES, stable_out_of_scope_response


def test_out_of_scope_copy_has_twenty_sounderone_only_variants():
    assert len(OUT_OF_SCOPE_RESPONSES) == 20
    assert len(set(OUT_OF_SCOPE_RESPONSES)) == 20
    assert all("SOUNDERONE" in response for response in OUT_OF_SCOPE_RESPONSES)
    assert all("王叔" not in response for response in OUT_OF_SCOPE_RESPONSES)


def test_out_of_scope_selection_is_stable_but_varied():
    first = stable_out_of_scope_response("conversation-1", "message-1")
    assert first == stable_out_of_scope_response("conversation-1", "message-1")
    selected = {
        stable_out_of_scope_response("conversation-1", f"message-{index}")
        for index in range(100)
    }
    assert len(selected) > 10
