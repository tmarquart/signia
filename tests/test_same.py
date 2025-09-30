"""Tests for :func:`signia.same_signature`."""

from __future__ import annotations

import inspect

from signia import same_signature


def _reference(
    a: int,
    /,
    b: str,
    *,
    c: float = 1.0,
    d: int | None = None,
    **extras: bool,
) -> str:
    return f"{a}-{b}-{c}-{d}-{sorted(extras)}"


def _identical(
    a: int,
    /,
    b: str,
    *,
    c: float = 1.0,
    d: int | None = None,
    **extras: bool,
) -> str:
    return _reference(a, b, c=c, d=d, **extras)


def _different_defaults(
    a: int,
    /,
    b: str,
    *,
    c: float = 2.0,
    d: int | None = None,
    **extras: bool,
) -> str:
    return _reference(a, b, c=c, d=d, **extras)


def _different_annotations(
    a,
    /,
    b,
    *,
    c=1.0,
    d=None,
    **extras,
):
    return _reference(a, b, c=c, d=d, **extras)


def _different_return(
    a: int,
    /,
    b: str,
    *,
    c: float = 1.0,
    d: int | None = None,
    **extras: bool,
) -> int:
    return a


def test_same_signature_strict_true():
    assert same_signature(_reference, _identical)


def test_same_signature_default_difference_requires_relaxed():
    assert not same_signature(_reference, _different_defaults)
    assert same_signature(_reference, _different_defaults, strict=False)


def test_same_signature_annotation_controls():
    assert not same_signature(_reference, _different_annotations)
    assert same_signature(
        _reference,
        _different_annotations,
        ignore_annotations=True,
    )


def test_same_signature_return_annotation_controls():
    assert not same_signature(_reference, _different_return)
    assert same_signature(_reference, _different_return, ignore_return=True)


def test_same_signature_signature_objects():
    signature = inspect.signature(_reference)
    altered = signature.replace(return_annotation=int)

    assert not same_signature(signature, altered)
    assert same_signature(signature, altered, ignore_return=True)


def test_same_signature_incompatible_structure():
    def variant(a: int, b: str, *, c: float = 1.0) -> str:
        return b

    assert not same_signature(_reference, variant, strict=False)
