"""Exceptions used across core boundaries."""


class HelloAgentsException(Exception):
    """Base error exposed by the public core API."""


__all__ = ["HelloAgentsException"]
