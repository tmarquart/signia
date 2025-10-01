from __future__ import annotations

import pytest

from signia import SignatureConflictError, merge_signatures
from signia._core import _merge_fuse_signatures


def test_merge_fuse_signatures_parameter_collision():
    def left(x: int) -> int:
        return x

    def right(x: int) -> int:
        return x

    with pytest.raises(SignatureConflictError) as excinfo:
        _merge_fuse_signatures([left, right], on_conflict="error")

    message = str(excinfo.value)
    assert "parameter name collision" in message
    assert "left" in message
    assert "right" in message


def test_merge_fuse_signatures_left_default_mismatch():
    def left_default(y: int = 1) -> int:
        return y

    def right_default(y: int = 2) -> int:
        return y

    with pytest.raises(SignatureConflictError) as excinfo:
        _merge_fuse_signatures([left_default, right_default], on_conflict="left")

    message = str(excinfo.value)
    assert "default mismatch" in message
    assert "left_default" in message
    assert "right_default" in message


def test_merge_fuse_signatures_right_annotation_mismatch():
    def left_annotation(z: int) -> int:
        return z

    def right_annotation(z: str) -> str:
        return z

    with pytest.raises(SignatureConflictError) as excinfo:
        _merge_fuse_signatures(
            [left_annotation, right_annotation],
            on_conflict="right",
            compare_annotations=True,
        )

    message = str(excinfo.value)
    assert "annotation mismatch" in message
    assert "left_annotation" in message
    assert "right_annotation" in message


def test_merge_fuse_signatures_custom_resolver_passthrough():
    def left(a: int = 1, *, flag: bool = False) -> int:
        return a

    def right(a: int = 2, *, extra: str = "x") -> int:
        return a

    def resolver(name, existing, incoming, conflicts):  # pragma: no cover - exercised indirectly
        return incoming

    signature, owners, has_varargs, has_kwargs = _merge_fuse_signatures(
        [left, right],
        on_conflict=resolver,
    )

    expected = merge_signatures(left, right, on_conflict=resolver)
    assert signature == expected
    assert owners == {"a": 1, "flag": 0, "extra": 1}
    assert not has_varargs
    assert not has_kwargs


def test_merge_fuse_signatures_metadata_capture():
    def primary(value: int, /, *values: int, **options: int) -> int:
        return value

    def helper(*, toggle: bool = False) -> None:
        return None

    signature, owners, has_varargs, has_kwargs = _merge_fuse_signatures(
        [primary, helper],
        on_conflict="left",
    )

    expected = merge_signatures(primary, helper)
    assert signature == expected
    assert owners == {"value": 0, "values": 0, "options": 0, "toggle": 1}
    assert has_varargs
    assert has_kwargs
