"""Tests for :func:`signia.mirror_signature`."""

from __future__ import annotations

import inspect

from signia import mirror_signature


def sample_function(
    x: int,
    /,
    y: str,
    *values: float,
    flag: bool = False,
    **options: str,
) -> str:
    """Example function whose signature we mirror."""

    parts = [y, *(str(value) for value in values)]
    if flag:
        parts.append("!")
    parts.extend(sorted(options))
    return " ".join(parts)


def passthrough(*args, **kwargs):
    """Target callable used for mirroring."""

    return args, kwargs


def test_mirror_signature_metadata():
    decorated = mirror_signature(sample_function)(passthrough)

    assert decorated.__doc__ == sample_function.__doc__
    assert decorated.__name__ == sample_function.__name__
    assert decorated.__wrapped__ is sample_function
    assert inspect.signature(decorated) == inspect.signature(sample_function)


def test_mirrored_callable_invocation():
    decorated = mirror_signature(sample_function)(passthrough)

    result = decorated(1, "two", 3.0, 4.0, flag=True, mode="test")

    assert result == (
        (1, "two", 3.0, 4.0),
        {"flag": True, "mode": "test"},
    )


def test_mirror_signature_on_method():
    class Example:
        @mirror_signature(sample_function)
        def method(self, *args, **kwargs):
            return self, args, kwargs

    instance = Example()

    assert inspect.signature(Example.method) == inspect.signature(sample_function)

    received_self, args, kwargs = instance.method(1, "two", 3.0, flag=True)

    assert received_self is instance
    assert args == (1, "two", 3.0)
    assert kwargs == {"flag": True}


def test_mirror_signature_from_bound_method():
    class Source:
        def method(self, x: int, y: str, *, flag: bool = False) -> tuple[int, str, bool]:
            return x, y, flag

    bound_method = Source().method
    decorated = mirror_signature(bound_method)(passthrough)

    decorated_signature = inspect.signature(decorated)

    assert "self" not in decorated_signature.parameters
    assert decorated_signature == inspect.signature(bound_method)

    result = decorated(5, "value", flag=True)

    assert result == ((5, "value"), {"flag": True})
