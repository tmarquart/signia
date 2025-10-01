
"""Tests for the fuse decorator and fused source proxies."""

from __future__ import annotations

import inspect

import pytest

from signia import SigniaWarning, fuse
from signia._core import CallVars, _FusedSourceProxy


def test_proxy_memoizes_zero_arg_calls():
    calls: list[tuple[int, int]] = []

    def target(x: int, *, y: int) -> int:
        calls.append((x, y))
        return x + y

    proxy = _FusedSourceProxy(target, 2, y=3)

    assert proxy() == 5
    assert proxy() == 5
    assert calls == [(2, 3)]


def test_proxy_overrides_bypass_cache():
    calls: list[tuple[int, int]] = []

    def target(x: int, *, y: int) -> int:
        calls.append((x, y))
        return x + y

    proxy = _FusedSourceProxy(target, 4, y=5)

    assert proxy() == 9
    assert proxy(y=7) == 11
    assert calls == [(4, 5), (4, 7)]
    assert proxy() == 9
    assert calls == [(4, 5), (4, 7)]


def test_proxy_defaults_and_signature_snapshot():
    def sample(a: int, b: int = 2, *, c: int = 3, d: int) -> int:
        return a + b + c + d

    proxy = _FusedSourceProxy(sample, 1, d=4)

    assert proxy.args == (1,)
    assert dict(proxy.kw) == {"d": 4}
    assert proxy.signature == inspect.signature(sample)
    assert list(proxy.params) == ["a", "b", "c", "d"]
    assert proxy.defaults == {"b": 2, "c": 3}


def test_fuse_function_auto_publish():
    calls: list[tuple[str, tuple[int, ...]]] = []
    seen_types: list[type[_FusedSourceProxy]] = []

    def load(x: int, *, y: int = 1) -> int:
        calls.append(("load", (x, y)))
        return x + y

    def audit(z: int) -> int:
        calls.append(("audit", (z,)))
        return z * 2

    @fuse(load, audit, on_conflict="left")
    def pipeline(load_proxy, audit_proxy):
        seen_types.append(type(load_proxy))
        seen_types.append(type(audit_proxy))
        first = load_proxy()
        second = audit_proxy()
        return first + second

    result = pipeline(3, 4, y=5)

    assert result == (3 + 5) + (4 * 2)
    assert calls == [("load", (3, 5)), ("audit", (4,))]
    assert all(proxy_type is _FusedSourceProxy for proxy_type in seen_types)

    signature = inspect.signature(pipeline)
    params = list(signature.parameters.values())
    assert [param.name for param in params] == ["x", "z", "y"]
    assert params[2].default == 1


def test_fuse_method_auto_publish():
    history: list[tuple[str, tuple[int, str]]] = []

    class Pipeline:
        def load(self, size: int, *, prefix: str = "") -> str:
            history.append(("load", (size, prefix)))
            return f"{prefix}{size}"

        def audit(self, size: int, *, prefix: str = "") -> None:
            history.append(("audit", (size, prefix)))

        @fuse(load, audit, on_conflict="left")
        def run(self, load_proxy, audit_proxy):
            result = load_proxy()
            audit_proxy()
            return result

    pipeline = Pipeline()
    outcome = pipeline.run(5, prefix="!")

    assert outcome == "!5"
    assert history == [("load", (5, "!")), ("audit", (5, "!"))]

    signature = inspect.signature(Pipeline.run)
    params = list(signature.parameters.values())
    assert [param.name for param in params] == ["self", "size", "prefix"]
    assert params[2].default == ""
    assert not isinstance(Pipeline.__dict__["run"], staticmethod)


def test_fuse_staticmethod_auto_publish():
    def double(value: int) -> int:
        return value * 2

    class Numbers:
        @fuse(double)
        def compute(proxy):
            return proxy()

    descriptor = Numbers.__dict__["compute"]
    assert isinstance(descriptor, staticmethod)
    assert Numbers.compute(4) == 8

    signature = inspect.signature(Numbers.compute)
    assert [param.name for param in signature.parameters.values()] == ["value"]


def test_fuse_wrapper_proxy_memoization():
    calls: list[int] = []

    def base(value: int) -> int:
        calls.append(value)
        return value * 2

    @fuse(base)
    def repeat(proxy):
        return proxy() + proxy()

    assert repeat(3) == 12
    assert calls == [3]


def test_fuse_wrapper_additional_keyword_parameter():
    call_log: list[tuple[tuple[int, ...], dict[str, int]]] = []
    captured: list[int] = []

    def source(value: int) -> int:
        call_log.append(((value,), {}))
        return value

    @fuse(source)
    def ext(proxy, *, new_input: int = 0):
        captured.append(new_input)
        return proxy() + new_input

    signature = inspect.signature(ext)
    params = list(signature.parameters.values())

    assert [param.name for param in params] == ["value", "new_input"]
    assert params[1].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[1].default == 0

    result = ext(5, new_input=7)

    assert result == 12
    assert captured == [7]
    assert call_log == [((5,), {})]


def test_fuse_proxy_call_vars_function_mode():
    calls: list[tuple[int, int]] = []
    snapshots: list[CallVars] = []

    def multiply(value: int, *, factor: int = 1) -> int:
        calls.append((value, factor))
        return value * factor

    @fuse(multiply)
    def wrapper(proxy):
        first = proxy()
        snapshots.append(multiply.vars)
        second = proxy()
        snapshots.append(multiply.vars)
        third = proxy(factor=3)
        snapshots.append(multiply.vars)
        return first + second + third

    assert wrapper(4) == (4 * 1) + (4 * 1) + (4 * 3)
    assert calls == [(4, 1), (4, 3)]

    cached_first, cached_second, override_vars = snapshots
    assert cached_first.args == (4,)
    assert cached_first.kwargs == {"factor": 1}
    assert list(cached_first.arguments.items()) == [
        ("value", 4),
        ("factor", 1),
    ]
    assert cached_first.result == 4
    assert cached_second is cached_first

    assert override_vars.args == (4,)
    assert override_vars.kwargs == {"factor": 3}
    assert list(override_vars.arguments.items()) == [
        ("value", 4),
        ("factor", 3),
    ]
    assert override_vars.result == 12
    assert multiply.vars is override_vars


def test_fuse_proxy_call_vars_method_mode():
    history: list[tuple[int, str]] = []
    snapshots: list[CallVars] = []

    class Greeter:
        def format(self, value: int, *, suffix: str = "!") -> str:
            history.append((value, suffix))
            return f"{value}{suffix}"

        @fuse(format, publish="method")
        def emit(self, proxy):
            first = proxy()
            snapshots.append(Greeter.format.vars)
            second = proxy()
            snapshots.append(Greeter.format.vars)
            third = proxy(suffix="?")
            snapshots.append(Greeter.format.vars)
            return first + second + third

    greeter = Greeter()
    assert greeter.emit(2) == "2!2!2?"
    assert history == [(2, "!"), (2, "?")]

    cached_first, cached_second, override_vars = snapshots
    assert cached_first.args == (greeter, 2)
    assert cached_first.kwargs == {"suffix": "!"}
    assert list(cached_first.arguments.items()) == [
        ("self", greeter),
        ("value", 2),
        ("suffix", "!"),
    ]
    assert cached_first.result == "2!"
    assert cached_second is cached_first

    assert override_vars.args == (greeter, 2)
    assert override_vars.kwargs == {"suffix": "?"}
    assert list(override_vars.arguments.items()) == [
        ("self", greeter),
        ("value", 2),
        ("suffix", "?"),
    ]
    assert override_vars.result == "2?"
    assert Greeter.format.vars is override_vars


def test_fuse_proxy_call_vars_staticmethod_mode():
    calls: list[tuple[int, int]] = []
    snapshots: list[CallVars] = []

    def adjust(value: int, *, offset: int = 0) -> int:
        calls.append((value, offset))
        return value + offset

    class Calculator:
        @fuse(adjust, publish="staticmethod")
        def process(proxy):
            first = proxy()
            snapshots.append(adjust.vars)
            second = proxy()
            snapshots.append(adjust.vars)
            third = proxy(offset=5)
            snapshots.append(adjust.vars)
            return first + second + third

    assert Calculator.process(3) == (3 + 0) + (3 + 0) + (3 + 5)
    assert calls == [(3, 0), (3, 5)]

    cached_first, cached_second, override_vars = snapshots
    assert cached_first.args == (3,)
    assert cached_first.kwargs == {"offset": 0}
    assert list(cached_first.arguments.items()) == [
        ("value", 3),
        ("offset", 0),
    ]
    assert cached_first.result == 3
    assert cached_second is cached_first

    assert override_vars.args == (3,)
    assert override_vars.kwargs == {"offset": 5}
    assert list(override_vars.arguments.items()) == [
        ("value", 3),
        ("offset", 5),
    ]
    assert override_vars.result == 8
    assert adjust.vars is override_vars


def test_fuse_bound_method_warning():
    class Example:
        def method(self, value: int) -> int:
            return value * 3

    instance = Example()

    with pytest.warns(SigniaWarning, match="bound method"):
        @fuse(instance.method)
        def wrapped(proxy):
            return proxy()

    assert wrapped(4) == 12


def test_fuse_varargs_collapse_warning():
    calls: list[tuple[str, tuple[int, ...]]] = []

    def left(*values: int) -> tuple[int, ...]:
        calls.append(("left", values))
        return values

    def right(*values: int) -> tuple[int, ...]:
        calls.append(("right", values))
        return values

    with pytest.warns(SigniaWarning, match="\\*args"):
        @fuse(left, right, on_conflict="left")
        def merged(left_proxy, right_proxy):
            left_proxy()
            right_proxy()

    merged(1, 2, 3)
    assert calls == [("left", (1, 2, 3)), ("right", (1, 2, 3))]


def test_fuse_publish_validation_error():
    with pytest.raises(ValueError):
        fuse(lambda: None, publish="invalid")


def test_fuse_on_conflict_validation_error():
    with pytest.raises(ValueError):
        fuse(lambda: None, on_conflict="invalid")


def test_fuse_suspicious_method_binding_warning():
    def identity(value: int) -> int:
        return value

    with pytest.warns(SigniaWarning, match="method"):
        class Example:
            @fuse(identity, publish="method")
            def compute(proxy):
                return proxy()

    assert Example().compute(3) == 3


def test_fuse_static_reference_warning():
    def identity(value: int) -> int:
        return value

    with pytest.warns(SigniaWarning, match="staticmethod"):
        class Example:
            @fuse(identity, publish="staticmethod")
            def compute(proxy):
                self = "shadow"
                return proxy()

    assert Example.compute(4) == 4


def test_fuse_composed_usage():
    calls: list[str] = []

    def double(value: int) -> int:
        calls.append("double")
        return value * 2

    def triple(value: int) -> int:
        calls.append("triple")
        return value * 3

    @fuse(double)
    def stage(proxy):
        return proxy()

    @fuse(stage, triple, on_conflict="left")
    def pipeline(stage_proxy, triple_proxy):
        stage_value = stage_proxy()
        triple_value = triple_proxy()
        return stage_value + triple_value

    assert pipeline(2) == (2 * 2) + (2 * 3)
    assert calls.count("double") == 1
    assert calls.count("triple") == 1


def test_signia_warning_is_warning():
    """Ensure the exported warning derives from :class:`Warning`."""

    assert issubclass(SigniaWarning, Warning)

