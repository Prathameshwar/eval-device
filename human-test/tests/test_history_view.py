from human_test.history_view import display_record


def test_history_displays_exact_text_without_rewriting():
    value = {
        "input_text": "\u0928\u092e\u0938\u094d\u0924\u0947?",
        "response_text": "Hello\nDoctor.",
        "save_status": "saved_locally",
    }
    result = display_record(value)
    assert "\u0928\u092e\u0938\u094d\u0924\u0947?" in result and "Hello\nDoctor." in result
    assert "upload pending" in result
