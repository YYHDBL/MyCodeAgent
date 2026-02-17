"""TeamFanout tool prompt."""

team_fanout_prompt = """
Tool name: TeamFanout
Dispatch parallel work items to teammates.

Parameters
- team_name (string, required)
- tasks (array, required): each item has owner, title, instruction, optional payload

Behavior
- Creates queued work items for owners in the same team.
- Returns dispatch_id and created work_items.
"""

