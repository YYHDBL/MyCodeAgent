"""TeamApprovePlan tool prompt."""

team_approve_plan_prompt = """
Tool name: TeamApprovePlan
Send an approval decision for a pending teammate plan.

Parameters
- team_name (string, required)
- request_id (string, required)
- approved (boolean, required)
- feedback (string, optional)
- from_member (string, optional, default lead)
"""
