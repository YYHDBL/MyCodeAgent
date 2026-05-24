from agents.codeAgent import CodeAgent


def test_parallel_runtime_block_summarizes_progress():
    events = [
        {
            "team": "demo",
            "type": "work_item_failed",
            "payload": {"work_id": "w2", "status": "failed"},
        }
    ]
    runtime_state = {
        "teams": {"demo": {"last_error": "boom"}},
        "work_items": {
            "demo": {
                "queued": 1,
                "running": 2,
                "succeeded": 3,
                "failed": 1,
                "canceled": 0,
            }
        },
    }

    blocks = CodeAgent._format_runtime_system_blocks(
        events=events,
        runtime_state=runtime_state,
        max_lines=12,
    )

    assert blocks
    block = blocks[0]
    assert "[Team Runtime]" in block
    assert "demo work queued=1 running=2 succeeded=3 failed=1" in block
    assert "demo last_error=boom" in block
    assert "work_item_failed" in block


def test_parallel_runtime_block_is_line_capped():
    events = [
        {
            "team": "demo",
            "type": "work_item_assigned",
            "payload": {"work_id": f"w{i}", "status": "queued"},
        }
        for i in range(20)
    ]
    runtime_state = {
        "teams": {f"team{i}": {"last_error": ""} for i in range(8)},
        "work_items": {
            f"team{i}": {
                "queued": i,
                "running": i,
                "succeeded": i,
                "failed": i,
                "canceled": 0,
            }
            for i in range(8)
        },
    }

    blocks = CodeAgent._format_runtime_system_blocks(
        events=events,
        runtime_state=runtime_state,
        max_lines=8,
    )

    assert blocks
    lines = blocks[0].splitlines()
    assert len(lines) <= 8
    assert any("more" in line for line in lines)
