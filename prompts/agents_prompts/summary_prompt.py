SUMMARY_PROMPT = """
You are tasked with creating an ARCHIVED SESSION SUMMARY for completed work in this conversation.

IMPORTANT:
- Focus ONLY on completed tasks and finalized work
- DO NOT include current in-progress tasks or next steps
- This summary is for HISTORICAL RECORD, not for continuing current work

Analyze the conversation and extract information into the following structure:

##  Archived Session Summary
*(Contains context from [Start Time] to [Cutoff Time])*

###  Objectives & Status
* **Original Goal**: [What the user initially wanted to accomplish]

###  Technical Context (Static)
* **Stack**: [Languages, frameworks, versions used]
* **Environment**: [OS, shell, key environment variables or configuration]

###  Completed Milestones (The "Done" Pile)
* [✓] [Completed task 1] - [Brief result/outcome]
* [✓] [Completed task 2] - [Brief result/outcome]
* [✓] [Completed task 3] - [Brief result/outcome]

###  Key Insights & Decisions (Persistent Memory)
* **Decisions**: [Key technical choices made, or approaches explicitly rejected]
* **Learnings**: [Special configurations, API quirks, gotchas discovered]
* **User Preferences**: [User's emphasized habits, style preferences, or requirements]

###  File System State (Snapshot)
*(Files modified/created in this archived segment)*
* `path/to/file1.ext`: [Brief description of changes]
* `path/to/file2.ext`: [Brief description of changes]

---

GUIDELINES:
1. **Be Specific**: Use actual file names, function names, and technical details from the conversation
2. **Be Concise**: Each bullet point should be 1-2 sentences maximum
3. **Omit Incomplete Work**: If a task was started but not finished, do NOT include it
4. **Omit Current Context**: Do NOT include "what we're working on now" or "next steps"
5. **Capture Trade-offs**: If alternatives were considered, note which was chosen and why
6. **User Voice**: If user expressed strong preferences or corrections, note them under User Preferences

OUTPUT: Provide ONLY the summary in the exact format above, with no additional commentary.
"""