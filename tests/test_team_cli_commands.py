import pytest

from core.team_engine.cli_commands import parse_team_message_command


def test_parse_team_message_command_with_auto_summary():
    parsed = parse_team_message_command(
        "/team msg demo dev1 please check task board status",
        from_member="lead",
    )
    assert parsed["team_name"] == "demo"
    assert parsed["from_member"] == "lead"
    assert parsed["to_member"] == "dev1"
    assert parsed["text"] == "please check task board status"
    assert parsed["summary"].startswith("please check task board status")


def test_parse_team_message_command_with_explicit_summary():
    parsed = parse_team_message_command(
        "/team msg demo dev1 sync :: please post latest progress and blockers",
        from_member="lead",
    )
    assert parsed["summary"] == "sync"
    assert parsed["text"] == "please post latest progress and blockers"


def test_parse_team_message_command_missing_arguments_raises():
    with pytest.raises(ValueError):
        parse_team_message_command("/team msg demo", from_member="lead")


def test_parse_team_message_command_empty_text_raises():
    with pytest.raises(ValueError):
        parse_team_message_command("/team msg demo dev1   ", from_member="lead")
