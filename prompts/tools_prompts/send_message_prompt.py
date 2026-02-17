"""SendMessage tool prompt."""

send_message_prompt = """
Tool name: SendMessage
Send a message to a teammate inbox inside a team.

Parameters
- team_name (string, required)
- from_member (string, required)
- to_member (string, required)
- text (string, required)

ACK status lifecycle
- pending: message created
- delivered: persisted to inbox
- processed: teammate acknowledged processing
"""

