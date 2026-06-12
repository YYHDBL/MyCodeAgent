"""Long-term memory tool prompt."""

memory_prompt = """
Tool name: Memory
Tool description:
Manages bounded long-term memory for stable cross-session facts. Memory writes are durable on disk
but do NOT change the current session's frozen snapshot. New writes become visible to the model only
in a future new session.

When to save
- User explicitly asks you to remember something.
- User gives a stable preference, correction, or working habit.
- You confirm a stable project constraint or environment fact.
- You learn a reusable tool quirk or architectural rule that will remain useful later.

Do NOT save
- Current task progress or temporary TODO state.
- One-off errors, raw logs, or code blocks.
- Commit SHAs, PR numbers, issue numbers, or completed-work journals.
- Facts likely to expire within a week.
- Procedural workflows that belong in a Skill instead.

Targets
- target="user": user identity, preferences, communication style, recurring corrections.
- target="memory": stable project/environment facts, architecture decisions, tool experience.

Actions
- add: append a new entry.
- replace: update one entry identified by a unique substring in old_text.
- remove: delete one entry identified by a unique substring in old_text.
- list: inspect the current live state for one target.

Constraints
- Entries are plain text facts, not instructions to yourself.
- Duplicate entries are rejected.
- Ambiguous replace/remove matches are rejected.
- Writes over the character budget are rejected without truncation.
- Unsafe content such as prompt injection or secret-exfiltration text is rejected.
"""
