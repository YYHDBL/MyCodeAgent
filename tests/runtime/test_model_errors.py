from runtime.model_errors import ModelErrorKind, classify_model_error


def test_classify_empty_response():
    result = classify_model_error(response_text="", tool_calls=[], response_meta={})

    assert result.kind is ModelErrorKind.EMPTY_RESPONSE
    assert result.recoverable is True


def test_classify_prompt_too_long_from_exception_message():
    result = classify_model_error(error=RuntimeError("prompt too long for model context window"))

    assert result.kind is ModelErrorKind.PROMPT_TOO_LONG
    assert result.recoverable is True


def test_classify_max_output_from_finish_reason():
    result = classify_model_error(
        response_text="partial answer",
        tool_calls=[],
        response_meta={"finish_reason": "length"},
    )

    assert result.kind is ModelErrorKind.MAX_OUTPUT
    assert result.recoverable is True


def test_classify_unknown_model_error_when_inputs_do_not_match_known_shapes():
    result = classify_model_error(error=ValueError("mystery condition"))

    assert result.kind is ModelErrorKind.UNKNOWN_MODEL_ERROR
