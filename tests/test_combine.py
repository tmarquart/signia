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


def test_combine_exposes_call_vars():
    calls: list[str] = []

    def primary(x: int, y: int = 2, /, *, flag: bool = False) -> int:
        calls.append(f"primary:{flag}")
        return x + y

    def audit(*, flag: bool, tracker: list[str]) -> None:
        tracker.append(f"audit:{flag}")

    tracker: list[str] = []
    wrapped = combine(primary, audit)

    assert not hasattr(primary, "vars")
    result = wrapped(1, flag=True, tracker=tracker)

    assert result == 3
    assert tracker == ["audit:True"]
    assert primary.vars.args == (1, 2)
    assert primary.vars.kwargs == {"flag": True}
    assert list(primary.vars.arguments.items()) == [("x", 1), ("y", 2), ("flag", True)]
    assert primary.vars.result == 3

    assert audit.vars.args == ()
    assert audit.vars.kwargs == {"flag": True, "tracker": tracker}
    assert list(audit.vars.arguments.items()) == [("flag", True), ("tracker", tracker)]
    assert audit.vars.result is None

    # Call again to ensure the snapshots refresh rather than accumulate.
    tracker.clear()
    wrapped(5, 10, tracker=tracker)

    assert tracker == ["audit:False"]
    assert primary.vars.args == (5, 10)
    assert primary.vars.kwargs == {"flag": False}
    assert list(primary.vars.arguments.items())[-1] == ("flag", False)
    assert primary.vars.result == 15


def test_combine_custom_wrapper_allows_manual_result():
    def func_a(a: int, b: int) -> int:
        return a + b

    def func_b(*, scale: int = 1) -> int:
        return scale

    calls: list[tuple[int, int]] = []

    @combine(func_a, func_b)
    def wrapper(a: int, b: int, *, scale: int = 1) -> int:
        calls.append((func_a.vars.result, func_b.vars.result))
        return func_a.vars.result * func_b.vars.result

    assert inspect.signature(wrapper) == merge_signatures(func_a, func_b)

    result = wrapper(2, 3, scale=5)

    assert result == (2 + 3) * 5
    assert calls == [(5, 5)]

    second = wrapper(4, 6)

    assert second == (4 + 6) * 1
    assert calls[-1] == (10, 1)


def test_combine_subclass_override():
    class Base:
        def __init__(self) -> None:
            self.base_calls: list[tuple[int, bool]] = []

        def method(self, value: int, /, *, flag: bool = False) -> str:
            self.base_calls.append((value, flag))
            return f"base:{value}:{flag}"

    def subclass_helper(*, note: str, audit: list[str]) -> None:
        audit.append(note)

    class Sub(Base):
        def __init__(self) -> None:
            super().__init__()
            self.audit: list[str] = []

        method = combine(Base.method, subclass_helper)

    instance = Sub()
    result = instance.method(5, flag=True, note="called", audit=instance.audit)

    assert result == "base:5:True"
    assert instance.base_calls == [(5, True)]
    assert instance.audit == ["called"]
