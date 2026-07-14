"""Core CI must never silently run a credentialed evaluation."""


def test_credentialed_evaluations_are_an_explicit_pytest_marker(pytestconfig) -> None:
    markers = pytestconfig.getini("markers")

    assert any(marker.startswith("credentialed:") for marker in markers)
