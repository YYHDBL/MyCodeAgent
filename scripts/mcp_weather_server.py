"""Simple MCP weather server (stdio)."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Weather Server")


_WEATHER_FIXTURES = {
    "beijing": "Sunny, 28°C",
    "shanghai": "Cloudy, 26°C",
    "san francisco": "Foggy, 14°C",
    "new york": "Clear, 20°C",
}


@mcp.tool()
def get_weather(city: str, unit: str = "celsius") -> str:
    """Get a simple weather summary for a city (demo tool)."""
    if not city:
        return "Weather: unknown city"

    key = city.strip().lower()
    summary = _WEATHER_FIXTURES.get(key, f"Weather for {city}: 22°{'C' if unit == 'celsius' else 'F'}")

    if unit.lower().startswith("f"):
        # Rough conversion for demo
        summary = summary.replace("°C", "°F")

    return summary


if __name__ == "__main__":
    mcp.run()
