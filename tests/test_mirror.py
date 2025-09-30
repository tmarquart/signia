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
