from unittest.mock import patch

from core.team_engine.display_mode import resolve_teammate_mode


def test_in_process_mode_keeps_in_process():
    mode, warning = resolve_teammate_mode("in-process")
    assert mode == "in-process"
    assert warning is None


def test_tmux_mode_falls_back_when_tmux_missing():
    with patch("core.team_engine.display_mode.shutil.which", return_value=None):
        mode, warning = resolve_teammate_mode("tmux")
    assert mode == "in-process"
    assert warning is not None
    assert "tmux" in warning.lower()


def test_auto_mode_prefers_tmux_when_inside_tmux_session():
    with patch.dict("os.environ", {"TMUX": "/tmp/fake"}, clear=True):
        with patch("core.team_engine.display_mode.shutil.which", return_value="/usr/bin/tmux"):
            mode, warning = resolve_teammate_mode("auto")
    assert mode == "tmux"
    assert warning is None


def test_auto_mode_defaults_to_in_process_when_not_in_tmux_session():
    with patch.dict("os.environ", {}, clear=True):
        mode, warning = resolve_teammate_mode("auto")
    assert mode == "in-process"
    assert warning is None


def test_invalid_mode_falls_back_with_warning():
    with patch.dict("os.environ", {}, clear=True):
        mode, warning = resolve_teammate_mode("bad-mode")
    assert mode == "in-process"
    assert warning is not None
