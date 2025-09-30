"""Tests for :func:`signia.merge_signatures`."""

from __future__ import annotations

import inspect
from inspect import Parameter

import pytest

from signia import SignatureConflictError, merge_signatures


def left(
    a: int,
    /,
    b: str,
    *args: float,
    c: int = 1,
    **kwargs: bool,
) -> str:
    return b


def right(
    a: int,
    /,
    *,
    c: int = 1,
    d: float,
    **kwargs: bool,
) -> str:
    return str(d)


def test_merge_signatures_groups_by_kind():
    signature = merge_signatures(left, right)

    parameters = list(signature.parameters.values())
    expected_order = [
        ("a", Parameter.POSITIONAL_ONLY),
        ("b", Parameter.POSITIONAL_OR_KEYWORD),
        ("args", Parameter.VAR_POSITIONAL),
        ("c", Parameter.KEYWORD_ONLY),
        ("d", Parameter.KEYWORD_ONLY),
        ("kwargs", Parameter.VAR_KEYWORD),
    ]

    assert [(parameter.name, parameter.kind) for parameter in parameters] == expected_order
    assert signature.parameters["c"].default == 1
    assert signature.return_annotation == "str"


def test_merge_signatures_conflicting_defaults_raise():
    def right_conflicting(
        a: int,
        /,
        *,
        c: int = 2,
        d: float,
        **kwargs: bool,
    ) -> str:
        return str(d)

    with pytest.raises(SignatureConflictError) as excinfo:
        merge_signatures(left, right_conflicting, compare_defaults=True)

    assert "default 1 vs 2" in str(excinfo.value)


def test_merge_signatures_custom_resolver():
    def resolver(name, existing, incoming, conflicts):
        assert name == "c"
        assert {kind for kind, *_ in conflicts} == {"default"}
        assert existing.default == 1
        assert incoming.default == 2
        return existing.replace(default=42)

    def right_conflicting(
        a: int,
        /,
        *,
        c: int = 2,
        d: float,
        **kwargs: bool,
    ) -> str:
        return str(d)

    signature = merge_signatures(left, right_conflicting, on_conflict=resolver)
    parameter = signature.parameters["c"]

    assert parameter.default == 42
    assert parameter.kind is Parameter.KEYWORD_ONLY


def test_merge_signatures_policy_prefer_last():
    def right_conflicting(
        a: int,
        /,
        *,
        c: int = 2,
        d: float,
        **kwargs: bool,
    ) -> str:
        return str(d)

    signature = merge_signatures(
        left,
        right_conflicting,
        policy="prefer-last",
        compare_defaults=False,
    )

    assert signature.parameters["c"].default == 2


def test_merge_signatures_prefer_annotated():
    def annotated(a, *, b: int):
        return a

    def unannotated(a, *, b):
        return a

    signature = merge_signatures(unannotated, annotated, on_conflict="prefer-annotated")

    assert signature.parameters["b"].annotation == "int"


def test_merge_signatures_requires_input():
    with pytest.raises(ValueError):
        merge_signatures()
