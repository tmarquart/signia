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


def test_merge_signatures_with_base_method():
    class BaseClass:
        def method(self, value: int, *, flag: bool = False) -> int:
            return value if flag else -value

    def helper(*, audit: list[str]) -> None:
        audit.append("helper-called")

    signature = merge_signatures(BaseClass.method, helper)

    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == [
        "self",
        "value",
        "flag",
        "audit",
    ]
    assert parameters[0].kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[1].kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[2].kind is Parameter.KEYWORD_ONLY
    assert parameters[3].kind is Parameter.KEYWORD_ONLY

    audit: list[str] = []
    bound = signature.bind(BaseClass(), 10, flag=True, audit=audit)

    assert bound.arguments["self"].__class__ is BaseClass
    assert bound.arguments["value"] == 10
    assert bound.arguments["flag"] is True
    assert bound.arguments["audit"] is audit
