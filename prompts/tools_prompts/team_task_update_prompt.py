"""TeamTaskUpdate tool prompt."""

team_task_update_prompt = """
Tool name: TeamTaskUpdate
Update one task on the team shared task board.

Parameters
- team_name (string, required)
- task_id (string, required)
- status (string, optional): pending|in_progress|completed|canceled
- owner (string, optional)
- subject (string, optional)
- description (string, optional)
- add_blocked_by (array[string], optional)
- add_blocks (array[string], optional)
"""
