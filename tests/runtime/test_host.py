from runtime.host import CodeAgent


class _Function:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, function, call_id="call_1"):
        self.function = function
        self.id = call_id


class _Message:
    def __init__(self, tool_calls=None, function_call=None):
        self.tool_calls = tool_calls
        self.function_call = function_call


class _Choice:
    def __init__(self, message):
        self.message = message


class _Response:
    def __init__(self, message):
        self.choices = [_Choice(message)]


def test_extract_tool_calls_from_modern_response():
    response = _Response(
        _Message(
            tool_calls=[
                _ToolCall(
                    _Function(name="Read", arguments='{"path": "a.py"}'),
                    call_id="call_1",
                )
            ]
        )
    )

    assert CodeAgent._extract_tool_calls(response) == [
        {"id": "call_1", "name": "Read", "arguments": '{"path": "a.py"}'}
    ]


def test_extract_tool_calls_from_legacy_function_call():
    response = _Response(
        _Message(function_call=_Function(name="Search", arguments='{"query": "test"}'))
    )

    assert CodeAgent._extract_tool_calls(response) == [
        {"id": None, "name": "Search", "arguments": '{"query": "test"}'}
    ]
