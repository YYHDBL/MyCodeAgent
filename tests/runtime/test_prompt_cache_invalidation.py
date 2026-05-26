"""测试 ContextBuilder 在熔断器状态变化时的缓存失效行为。

Bug 复现 --> 当工具被熔断禁用后, _get_system_messages() 返回缓存中的旧内容;
            system prompt仍然描述该工具可用, 而get_openai_tools()已正确将其从 schema 移除;
            两者不一致导致模型在已禁用的工具上浪费多轮调用;

修复验证 --> 熔断器状态变化后缓存自动失效, system prompt重建并包含
"""

import pytest
from tools.base import Tool, ToolParameter, ErrorCode
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from runtime.prompt_builder import ContextBuilder


class _CircuitTestTool(Tool):
    """每次调用返回错误的工具，用于触发熔断器。"""

    def __init__(self, name: str = "TestTool"):
        super().__init__(name=name, description=f"{name} - a test tool that always fails")

    def get_parameters(self):
        return [ToolParameter(name="input", type="string", description="input value")]

    def run(self, parameters):
        return self.create_error_response(
            error_code=ErrorCode.EXECUTION_ERROR,
            message="Simulated failure",
            params_input=parameters,
        )


def _setup_prompt_dirs(tmp_path):
    """创建最小 prompt 目录结构供 ContextBuilder 加载。"""
    agents_dir = tmp_path / "prompts" / "agents_prompts"
    tools_dir = tmp_path / "prompts" / "tools_prompts"
    agents_dir.mkdir(parents=True)
    tools_dir.mkdir(parents=True)

    (agents_dir / "L1_system_prompt.py").write_text(
        'system_prompt = "You are a coding agent.\\n{tools}"', encoding="utf-8"
    )
    (tools_dir / "test_tool.py").write_text(
        'test_prompt = "TestTool: a test tool that always fails"', encoding="utf-8"
    )


class TestCacheInvalidationOnCircuitOpen:
    """验证熔断器打开时缓存失效。"""

    def test_disabled_tools_section_appears_after_circuit_opens(self, tmp_path):
        """复现 Bug：熔断后 system prompt 未更新，缺少 Disabled Tools 段。

        修复后：第二次调用 get_system_messages() 应包含 "Disabled Tools" 段。
        """
        _setup_prompt_dirs(tmp_path)

        registry = ToolRegistry()
        registry.register_tool(_CircuitTestTool("TestTool"))
        executor = ToolExecutor(registry)

        builder = ContextBuilder(
            tool_registry=registry,
            project_root=str(tmp_path),
        )

        # 首次构建：缓存 system messages，TestTool 未被禁用
        messages_before = builder.get_system_messages()
        content_before = messages_before[0]["content"]
        assert "TestTool" in content_before
        assert "Disabled Tools" not in content_before
        assert builder._cached_disabled_tools == frozenset()

        # 触发熔断：连续 3 次失败
        for _ in range(3):
            executor.execute("TestTool", {"input": "x"})

        assert not registry.is_available("TestTool")
        assert "TestTool" in registry.get_disabled_tools()

        # 再次获取 system messages ,修复后缓存因熔断状态变化而失效
        messages_after = builder.get_system_messages()
        content_after = messages_after[0]["content"]

        assert "Disabled Tools (temporary)" in content_after, (
            "Bug: system prompt cache not invalidated when circuit breaker opens. "
            "Expected 'Disabled Tools (temporary)' section in rebuilt prompt."
        )
        assert "TestTool" in content_after

    def test_cache_reused_when_disabled_tools_unchanged(self, tmp_path):
        """缓存命中：熔断器状态未变化时，缓存应被复用。"""
        _setup_prompt_dirs(tmp_path)

        registry = ToolRegistry()
        registry.register_tool(_CircuitTestTool("TestTool"))

        builder = ContextBuilder(
            tool_registry=registry,
            project_root=str(tmp_path),
        )

        # 首次调用建立缓存
        messages_1 = builder.get_system_messages()
        disabled_1 = builder._cached_disabled_tools

        # 再次调用，无任何变化，应命中缓存
        messages_2 = builder.get_system_messages()
        disabled_2 = builder._cached_disabled_tools

        assert messages_1[0]["content"] == messages_2[0]["content"]
        assert disabled_1 == disabled_2 == frozenset()

    def test_cache_invalidates_when_tool_recovers(self, tmp_path):
        """缓存失效：工具从禁用恢复到可用时，缓存也应失效。"""
        _setup_prompt_dirs(tmp_path)

        registry = ToolRegistry()
        registry.register_tool(_CircuitTestTool("TestTool"))
        executor = ToolExecutor(registry)

        builder = ContextBuilder(
            tool_registry=registry,
            project_root=str(tmp_path),
        )

        # 触发熔断
        for _ in range(3):
            executor.execute("TestTool", {"input": "x"})

        # 获取带 Disabled Tools 的 system messages
        messages_disabled = builder.get_system_messages()
        content_disabled = messages_disabled[0]["content"]
        assert "Disabled Tools" in content_disabled
        disabled_frozenset = builder._cached_disabled_tools
        assert "TestTool" in disabled_frozenset

        # 模拟恢复：记录一次成功执行
        registry._circuit_breaker.record_success("TestTool")
        assert registry.is_available("TestTool")
        assert "TestTool" not in registry.get_disabled_tools()

        # 再次获取 ,缓存应因 disabled 集合变化而失效
        messages_recovered = builder.get_system_messages()
        content_recovered = messages_recovered[0]["content"]

        assert "Disabled Tools" not in content_recovered, (
            "Bug: cache not invalidated when tool recovers from circuit-open. "
            "Expected 'Disabled Tools' section to disappear."
        )

    def test_set_skills_prompt_clears_cache(self, tmp_path):
        """set_skills_prompt 和 set_mcp_tools_prompt 仍按原有逻辑清空缓存。"""
        _setup_prompt_dirs(tmp_path)

        registry = ToolRegistry()
        registry.register_tool(_CircuitTestTool("TestTool"))

        builder = ContextBuilder(
            tool_registry=registry,
            project_root=str(tmp_path),
        )

        builder.get_system_messages()  # 建立缓存
        assert builder._cached_system_messages is not None

        builder.set_skills_prompt("new skill")
        assert builder._cached_system_messages is None, (
            "set_skills_prompt should clear the cache"
        )


class TestNoRegistryGraceful:
    """无 ToolRegistry 时的兼容性。"""

    def test_builder_without_get_disabled_tools(self, tmp_path):
        """tool_registry 没有 get_disabled_tools 方法时不应崩溃。"""
        _setup_prompt_dirs(tmp_path)

        class MinimalRegistry:
            pass

        builder = ContextBuilder(
            tool_registry=MinimalRegistry(),
            project_root=str(tmp_path),
        )

        messages = builder.get_system_messages()
        assert len(messages) > 0
        assert builder._cached_disabled_tools == frozenset()

    def test_builder_with_get_disabled_tools_that_raises(self, tmp_path):
        """get_disabled_tools 抛异常时不应崩溃。"""
        _setup_prompt_dirs(tmp_path)

        class FailingRegistry:
            def get_disabled_tools(self):
                raise RuntimeError("oops")

        builder = ContextBuilder(
            tool_registry=FailingRegistry(),
            project_root=str(tmp_path),
        )

        messages = builder.get_system_messages()
        assert len(messages) > 0
        assert builder._cached_disabled_tools == frozenset()
