import pytest

from eval.fixtures.py.buggy_math import safe_divide


def test_safe_divide_ok():
    assert safe_divide(10, 2) == 5


def test_safe_divide_zero():
    with pytest.raises(ValueError):
        safe_divide(1, 0)
