# Task Tool MVP Design

## Purpose
Provide a minimal subagent system so the primary agent can delegate focused work to a subagent. The subagent runs in an isolated session with a filtered toolset and optional model override.

## Scope (MVP)
- Synchronous Task execution only (no background jobs, no TaskOutput).
- Independent subagent session (separate message list and system prompt).
- Tool filtering to prevent recursion and unsafe tools.
- Minimal permission model (hard-coded deny list).
- Two-model routing only: **main** and **light**.

## Non-Goals (deferred)
- Background execution and TaskOutput polling.
- Resume by transcript.
- Forking parent context into subagent (forkContext).
- Event bus for progress streaming.
- Plugin-based agent loading.
- Fine-grained permission prompts (ask/allow/deny UI).

## Core Concepts
### Primary Agent
The main agent that receives user requests and decides when to delegate work via the Task tool.

### Subagent
A secondary agent instance with:
- its own message history
- its own system prompt
- restricted tool access
- optional model override

## Task Tool Interface (MVP)
### Input
```json
{
  "description": "short summary of the task",
  "prompt": "full instructions for the subagent",
  "subagent_type": "general",
  "model": "main" | "light"
}
```

### Output
```json
{
  "status": "success",
  "data": {
    "status": "completed",
    "result": "final text output from subagent",
    "tool_summary": [
      {"tool": "Read", "count": 3},
      {"tool": "Grep", "count": 1}
    ],
    "model_used": "light",
    "subagent_type": "explore"
  },
  "text": "Subagent (explore, light) completed.\n\n<result>",
  "stats": { "time_ms": 1234, "tool_calls": 4, "model": "light" },
  "context": { "cwd": ".", "params_input": { ... } }
}
```

Notes:
- `tool_summary` is optional and can be omitted in MVP if collecting tool stats is too heavy.
- 返回结构仍遵循《通用工具响应协议》（顶层 status/data/text/stats/context）。

## Subagent Types (MVP)
We keep a single subagent structure but allow different **subagent_type** values
to select a role-specific **system prompt**. The execution pipeline stays the same.

Supported types:
- `general`
- `explore`
- `summary`
- `plan`

### Prompt injection rule
- The Task tool chooses a prompt template based on `subagent_type`.
- The subagent **system** prompt is built from:
  - role prompt (by `subagent_type`)
  - the Task `description`
- The Task `prompt` is passed as the **user** message.

Example behavior:
```
subagent_type = "Explore"
subagent_system_prompt = EXPLORE_PROMPT + "\n\n# Task\n" + description
subagent_user_message = prompt
```

If `subagent_type` is unknown, the Task tool returns an error (no fallback).

## Model Selection (Main + Light)
### Goal
Only two selectable models are supported: **main** and **light**.\n
Light should be easy to switch by editing a config file (URL/API key).

### Strategy (MVP)
The main agent chooses the model per Task call:
- Use `model: "light"` for simpler tasks (summaries, quick lookups).
- Use `model: "main"` for complex reasoning or plan-heavy tasks.

### Config (light model switching)
Provide separate config keys for light vs main model endpoints and keys.
Example (format can be TOML/ENV depending on your config loader):

```
LLM_MODEL_ID=...              # main
LLM_API_KEY=...               # main
LLM_BASE_URL=...              # main

LIGHT_LLM_MODEL_ID=...        # light
LIGHT_LLM_API_KEY=...         # light
LIGHT_LLM_BASE_URL=...        # light
```

The Task tool picks main vs light based on the subagent type mapping above.

## Tool Filtering (MVP)
Subagents must not call Task or mutate the workspace unless explicitly allowed.

### Deny list (always blocked)
- `Task`
- `Write`
- `Edit`
- `MultiEdit`
- `Bash`

### Allow list (default)
- `LS`
- `TodoWrite`
- `Glob`
- `Grep`
- `Read`

Note:
- `TodoWrite` is allowed to persist a task list even though other tools are read-only.
- The allow list can be expanded later if more subagent types are added.

## Execution Flow (MVP)
1) Primary agent decides to delegate
2) Task tool validates input
3) Task tool uses the provided `subagent_type`
4) Task tool builds subagent toolset (deny list applied)
5) Task tool uses the model provided by the main agent (main vs light)
6) Task tool runs subagent synchronously
7) Task tool returns result + optional tool summary

## System Prompting
### Primary Agent
Add guidance:
- Use Task for complex or parallelizable work
- Prefer `light` for simpler tasks
- Prefer `main` for complex reasoning or plan-heavy tasks

### Subagent
Use a minimal system prompt:
- Clarify it is a subagent
- Instruct to only use the provided tools
- Instruct to focus on the provided prompt and return concise results

### Prompt Locations
Subagent role prompts (by `subagent_type`) live in:
- `prompts/agents_prompts/subagent_general_prompt.py`
- `prompts/agents_prompts/subagent_explore_prompt.py`
- `prompts/agents_prompts/subagent_plan_prompt.py`
- `prompts/agents_prompts/subagent_summary_prompt.py`

### How Prompts Are Used
At Task execution time:
1) Select the role prompt by `subagent_type`.
2) Build the subagent system prompt as:  
   `<ROLE_PROMPT> + "\\n\\n# Task\\n" + <Task.description>`
3) Send `<Task.prompt>` as the subagent user message.
4) Run the subagent with the selected model (`main` or `light`).


## Error Handling (MVP)
- Missing or invalid `description`/`prompt` → `INVALID_PARAM`
- Unknown `subagent_type` → `INVALID_PARAM`
- Subagent runtime error → `INTERNAL_ERROR` with message

## Logging
- Record a subagent session ID for trace/debugging (optional in MVP)
- Include model choice in trace metadata if available

## Security Notes
- Subagent tool access is restricted by design
- No recursion: Task is not exposed to subagents
