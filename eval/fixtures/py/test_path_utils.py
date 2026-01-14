import pytest

from eval.fixtures.py.path_utils import normalize_path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  a//b///c  ", "a/b/c"),
        ("/a/b/", "a/b"),
        ("C\\Users\\Bob\\", "C/Users/Bob"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_path(raw, expected):
    assert normalize_path(raw) == expected
