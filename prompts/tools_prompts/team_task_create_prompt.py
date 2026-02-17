"""TeamTaskCreate tool prompt."""

team_task_create_prompt = """
Tool name: TeamTaskCreate
Create a task on the team shared task board.

Parameters
- team_name (string, required)
- subject (string, required)
- description (string, optional)
- owner (string, optional)
- blocked_by (array[string], optional)
"""
