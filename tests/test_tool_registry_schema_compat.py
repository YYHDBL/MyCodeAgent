from tools.base import Tool, ToolParameter
from tools.registry import ToolRegistry


class ArrayTool(Tool):
    def __init__(self):
        super().__init__(name="ArrayTool", description="array test")

    def get_parameters(self):
        return [
            ToolParameter(name="values", type="array", description="List of values", required=False),
        ]

    def run(self, parameters):  # pragma: no cover
        return "{}"


def test_array_parameter_schema_includes_items():
    registry = ToolRegistry()
    registry.register_tool(ArrayTool())

    tools = registry.get_openai_tools()
    schema = next(t for t in tools if t.get("function", {}).get("name") == "ArrayTool")
    values_schema = schema["function"]["parameters"]["properties"]["values"]

    assert values_schema["type"] == "array"
    assert "items" in values_schema
