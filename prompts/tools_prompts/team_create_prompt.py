"""TeamCreate tool prompt."""

team_create_prompt = """
Tool name: TeamCreate
Create a persistent AgentTeams team with versioned config.

Parameters
- team_name (string, required)
- members (array, optional): each member can include name, role, tool_policy

Notes
- Members are normalized and must have role/tool_policy fields.
- Team config is persisted under .teams/.
"""

