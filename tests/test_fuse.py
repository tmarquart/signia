
"""Tests for the fused source proxy helpers."""

from __future__ import annotations

import inspect

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

from signia import SigniaWarning


def test_signia_warning_is_warning():
    """Ensure the exported warning derives from :class:`Warning`."""

    assert issubclass(SigniaWarning, Warning)

