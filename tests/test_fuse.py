
"""Tests for the fuse decorator and fused source proxies."""

from __future__ import annotations

import inspect

import pytest

from signia import SigniaWarning, fuse
from signia._core import _FusedSourceProxy


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

