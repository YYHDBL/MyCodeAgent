"""TeamCollect tool prompt."""

team_collect_prompt = """
Tool name: TeamCollect
Collect and aggregate status/results for parallel work items.

Parameters
- team_name (string, required)
- work_ids (array, optional)

Returns
- total work items
- status counts (queued/running/succeeded/failed/canceled)
- grouped work items by status
"""

