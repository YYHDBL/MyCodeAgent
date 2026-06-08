from tools.base import Tool, ToolParameter
from tools.registry import ToolRegistry


class _ToolA(Tool):
    def __init__(self):
        super().__init__(name="BTool", description="tool b")

    def get_parameters(self):
        return [ToolParameter(name="value", type="string", description="value")]

    def run(self, parameters):
        raise NotImplementedError


class _ToolB(Tool):
    def __init__(self):
        super().__init__(name="ATool", description="tool a")

    def get_parameters(self):
        return [ToolParameter(name="count", type="integer", description="count")]

    def run(self, parameters):
        raise NotImplementedError


def test_tool_registry_schema_fingerprint_is_stable_for_same_toolset():
    registry = ToolRegistry()
    registry.register_tool(_ToolA())
    registry.register_tool(_ToolB())

    first = registry.get_openai_tools()
    second = registry.get_openai_tools()
    first_fingerprint = registry.get_openai_tools_fingerprint()
    second_fingerprint = registry.get_openai_tools_fingerprint()

    assert [item["function"]["name"] for item in first] == ["ATool", "BTool"]
    assert first == second
    assert first_fingerprint == second_fingerprint


def test_tool_registry_schema_fingerprint_changes_when_schema_changes():
    registry = ToolRegistry()
    registry.register_tool(_ToolA())
    before = registry.get_openai_tools_fingerprint()

    registry.register_tool(_ToolB())
    after = registry.get_openai_tools_fingerprint()

    assert before != after
