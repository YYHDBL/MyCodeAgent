def test_runtime_loop_uses_host_orchestrator_only():
    source = open("runtime/loop.py", encoding="utf-8").read()

    assert "ToolOrchestrator(host).run(" not in source
    assert "from tools.orchestrator import ToolOrchestrator" not in source
