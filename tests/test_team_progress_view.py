from core.team_engine.progress_view import build_team_progress_rows


def test_build_team_progress_rows_basic():
    state = {
        "work_items": {
            "demo": {"queued": 1, "running": 2, "succeeded": 3, "failed": 0},
        },
        "teams": {
            "demo": {"active_teammates": ["dev1", "dev2"], "idle_teammates": ["dev3"]}
        },
        "approvals": {"demo": {"pending": 1, "approved": 0, "rejected": 0}},
        "task_board": {"demo": {"blocked": 2}},
    }

    rows = build_team_progress_rows(state)
    assert len(rows) == 1
    row = rows[0]
    assert row["team"] == "demo"
    assert row["running"] == 2
    assert row["active"] == 2
    assert row["idle"] == 1
    assert row["approvals_pending"] == 1
    assert row["blocked"] == 2


def test_build_team_progress_rows_filters_by_team_name():
    state = {
        "work_items": {
            "demo": {"queued": 0, "running": 1, "succeeded": 0, "failed": 0},
            "demo2": {"queued": 0, "running": 0, "succeeded": 1, "failed": 0},
        },
        "teams": {},
        "approvals": {},
        "task_board": {},
    }

    rows = build_team_progress_rows(state, team_name="demo2")
    assert len(rows) == 1
    assert rows[0]["team"] == "demo2"
