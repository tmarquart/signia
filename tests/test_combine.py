from __future__ import annotations

"""Tests for :func:`signia.combine`."""

import inspect

import pytest

from signia import combine, merge_signatures


def primary(
    x: int,
    /,
    y: str,
    *numbers: float,
    flag: bool = False,
    **options: str,
) -> tuple[int, str]:
    return x, y


def secondary(*, flag: bool, audit: list[str]) -> None:
    audit.append(f"flag={flag}")


def tertiary(*, trace: dict[str, str]) -> None:
    trace.update({"used": "yes"})


def test_combine_signature_and_routing():
    wrapped = combine(primary, secondary, tertiary)
    signature = inspect.signature(wrapped)
    expected = merge_signatures(primary, secondary, tertiary)

    assert signature == expected

    audit: list[str] = []
    trail: dict[str, str] = {}
    result = wrapped(1, "two", 3.0, flag=True, audit=audit, trace=trail)

    assert result == (1, "two")
    assert audit == ["flag=True"]
    assert trail == {"used": "yes"}


def test_combine_unexpected_keyword_raises():
    wrapped = combine(primary, secondary)

    with pytest.raises(TypeError):
        wrapped(1, "two", unknown=True)


def test_combine_var_keyword_consumption():
    def with_kwargs(x: int, /, **kwargs: int) -> int:
        return x

    def grab(**kwargs: int) -> None:
        assert "extra" in kwargs

    wrapped = combine(with_kwargs, grab)
    wrapped(10, extra=5)


def test_combine_method_behavior():
    class Tool:
        history: list[str]

        def __init__(self) -> None:
            self.history = []

        def action(self, value: int, /, *, flag: bool = False) -> int:
            self.history.append(f"action:{value}:{flag}")
            return value

        def log(self, /, *, note: str) -> None:
            self.history.append(f"log:{note}")

        invoke = combine(action, log)

    tool = Tool()

    result = tool.invoke(5, flag=True, note="done")

    assert result == 5
    assert tool.history == ["action:5:True", "log:done"]
