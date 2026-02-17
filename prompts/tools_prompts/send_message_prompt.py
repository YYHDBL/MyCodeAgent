"""SendMessage tool prompt."""

send_message_prompt = """
Tool name: SendMessage
Send a message to a teammate inbox inside a team.

Parameters
- team_name (string, required)
- from_member (string, required)
- to_member (string, required; ignored by broadcast routing)
- text (string, required)
- type (string, optional)
  message | broadcast | shutdown_request | shutdown_response | plan_approval_response
- summary (string, optional)
  Required when type=broadcast.
- request_id (string, optional)
  Required for shutdown_response and plan_approval_response.

ACK status lifecycle
- pending: message created
- delivered: persisted to inbox
- processed: teammate acknowledged processing
"""
