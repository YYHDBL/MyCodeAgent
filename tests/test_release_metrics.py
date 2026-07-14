"""Release-budget policy regression tests."""

from scripts.check_release_metrics import (
    MAX_STABLE_PRODUCTION_LINES,
    main,
    python_lines,
)


def test_current_release_tree_satisfies_the_approved_stable_line_budget(capsys):
    assert MAX_STABLE_PRODUCTION_LINES == 15_000
    assert python_lines() <= MAX_STABLE_PRODUCTION_LINES
    assert main() == 0
    assert "release metric failure" not in capsys.readouterr().err
