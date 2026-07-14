# M4-04 Tool Result Protocol Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `ponytail:ponytail-review`.

**Goal:** Replace per-tool JSON-envelope boilerplate with a small typed internal result serialized once at the model boundary.

**Architecture:** Built-ins return one internal result type; executor/orchestrator preserve it and a single observation adapter serializes it for the model.

**Tech Stack:** Python dataclasses or existing Pydantic, JSON, pytest.

**Dependencies:** M4-02 and M4-03 integrated.

**Files:**

- Modify: `tools/base.py`
- Modify: `tools/executor.py`
- Modify: `tools/registry.py`
- Modify: `tools/orchestrator.py`
- Modify: remaining `tools/builtin/*.py`
- Modify: `tools/observation_store.py`
- Create: `tests/tools/test_result_contract.py`
- Consolidate: `tests/test_protocol_compliance.py` and repeated per-tool protocol assertions

## Internal Contract

A result needs only:

- success/partial/error status;
- model-readable text;
- optional structured data;
- optional error code/message;
- execution metadata such as duration and resolved path.

Serialization to JSON/tool observation occurs in one adapter. The internal Python object should not be repeatedly encoded, parsed, normalized, and re-encoded through the execution path.

## Steps

1. Write one parameterized result-contract suite applied to every registered tool.
2. Introduce the minimal dataclass/model and one serializer.
3. Migrate executor/orchestrator/observation budgeting first, then built-ins.
4. Remove manual `create_*_response` boilerplate and repeated protocol tests.
5. Preserve model-visible error clarity and full-output truncation metadata.
6. Run all tool, registry, protocol, context, trace, and scenario tests.

## Acceptance

- Each tool returns an internal result object, not a JSON string.
- One serializer defines the model-facing envelope.
- Commit: `refactor(M4-04): simplify tool result protocol`.
