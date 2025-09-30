"""Core Signia functionality."""

from __future__ import annotations

from collections import OrderedDict
from functools import update_wrapper
import inspect
from inspect import Parameter, Signature
from typing import Any, Callable

__all__ = [
    "SignatureConflictError",
    "combine",
    "merge_signatures",
    "mirror_signature",
    "same_signature",
]


class SignatureConflictError(ValueError):
    """Raised when merging callables hits conflicting signature metadata."""


def mirror_signature(src: Callable[..., Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mirror a callable's signature and metadata onto another.

    Example
    -------
    >>> def greet(name: str, excited: bool = False) -> str:
    ...     return f"Hello {name}{'!' if excited else ''}"
    >>> @mirror_signature(greet)
    ... def wrapper(*args: Any, **kwargs: Any) -> str:
    ...     return greet(*args, **kwargs)
    >>> import inspect
    >>> str(inspect.signature(wrapper))
    "(name: str, excited: bool = False) -> str"
    """

    signature = inspect.signature(src)

    def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
        update_wrapper(target, src)
        target.__wrapped__ = src
        target.__doc__ = src.__doc__
        target.__name__ = src.__name__
        target.__signature__ = signature
        return target

    return decorator


def same_signature(
    first: Callable[..., Any] | Signature,
    second: Callable[..., Any] | Signature,
    *,
    strict: bool = True,
    ignore_return: bool = False,
    ignore_annotations: bool = False,
) -> bool:
    """Compare two callables or :class:`inspect.Signature` objects.

    The function defaults to a *strict* comparison, requiring parameters,
    defaults, annotations, and the return annotation to match exactly.
    Relaxed comparisons can be performed by setting ``strict=False`` (ignores
    differences in default *values*, but not whether defaults exist),
    ``ignore_return=True`` (ignores mismatched return annotations), and
    ``ignore_annotations=True`` (ignores both parameter and return
    annotations).

    Examples
    --------
    >>> def original(x: int, /, y: str, *, z: float = 1.0) -> str:
    ...     return y * int(z)
    >>> def mirror(x: int, /, y: str, *, z: float = 1.0) -> str:
    ...     return original(x, y=y, z=z)
    >>> same_signature(original, mirror)
    True

    ``strict=False`` tolerates different default *values* so long as optional
    and required parameters align.

    >>> def configurable(x: int, y: int = 0) -> int:
    ...     return x + y
    >>> def different_default(x: int, y: int = 1) -> int:
    ...     return x + y
    >>> same_signature(configurable, different_default)
    False
    >>> same_signature(configurable, different_default, strict=False)
    True

    Annotations can be ignored selectively.

    >>> def annotated(x: int) -> int:
    ...     return x
    >>> def unannotated(x):
    ...     return x
    >>> same_signature(annotated, unannotated)
    False
    >>> same_signature(annotated, unannotated, ignore_annotations=True)
    True

    Return annotations may also be ignored while retaining strict parameter
    comparisons.

    >>> def returns_int(x: int) -> int:
    ...     return x
    >>> def returns_str(x: int) -> str:
    ...     return str(x)
    >>> same_signature(returns_int, returns_str)
    False
    >>> same_signature(returns_int, returns_str, ignore_return=True)
    True
    """

    signature_a = _ensure_signature(first)
    signature_b = _ensure_signature(second)

    if ignore_annotations:
        signature_a = _strip_parameter_annotations(signature_a)
        signature_b = _strip_parameter_annotations(signature_b)

    if ignore_return or ignore_annotations:
        signature_a = signature_a.replace(return_annotation=Signature.empty)
        signature_b = signature_b.replace(return_annotation=Signature.empty)

    if strict:
        return signature_a == signature_b

    return _compatible_signatures(signature_a, signature_b)


def _ensure_signature(target: Callable[..., Any] | Signature) -> Signature:
    """Return a concrete :class:`inspect.Signature` for *target*."""

    if isinstance(target, Signature):
        return target
    return inspect.signature(target)


def _compatible_signatures(left: Signature, right: Signature) -> bool:
    """Return ``True`` when two signatures are structurally compatible."""

    parameters_left = list(left.parameters.values())
    parameters_right = list(right.parameters.values())

    if len(parameters_left) != len(parameters_right):
        return False

    for parameter_left, parameter_right in zip(parameters_left, parameters_right):
        if parameter_left.kind is not parameter_right.kind:
            return False
        if parameter_left.name != parameter_right.name:
            return False

        has_default_left = parameter_left.default is not Parameter.empty
        has_default_right = parameter_right.default is not Parameter.empty
        if has_default_left != has_default_right:
            return False

        if parameter_left.annotation != parameter_right.annotation:
            return False

    return left.return_annotation == right.return_annotation


def merge_signatures(*callables: Callable[..., Any]) -> Signature:
    """Merge multiple callables into a single :class:`inspect.Signature`."""

    if not callables:
        raise ValueError("merge_signatures requires at least one callable")

    merged_parameters: OrderedDict[str, Parameter] = OrderedDict()
    return_annotation = Signature.empty

    for function in callables:
        signature = inspect.signature(function)

        for parameter in signature.parameters.values():
            existing = merged_parameters.get(parameter.name)
            if existing is None:
                merged_parameters[parameter.name] = parameter
                continue

            merged_parameters[parameter.name] = _merge_parameter(existing, parameter)

        return_annotation = _merge_return_annotation(return_annotation, signature.return_annotation)

    return Signature(parameters=list(merged_parameters.values()), return_annotation=return_annotation)


def combine(
    *functions: Callable[..., Any],
    name: str | None = None,
    doc: str | None = None,
) -> Callable[..., Any]:
    """Combine multiple callables into a wrapper with a merged signature."""

    if not functions:
        raise ValueError("combine requires at least one callable")

    merged_signature = merge_signatures(*functions)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        bound = merged_signature.bind(*args, **kwargs)
        bound.apply_defaults()

        results = []
        for function in functions:
            function_signature = inspect.signature(function)
            positional: list[Any] = []
            keywords: dict[str, Any] = {}

            for parameter in function_signature.parameters.values():
                if parameter.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD):
                    positional.append(bound.arguments[parameter.name])
                elif parameter.kind is Parameter.VAR_POSITIONAL:
                    positional.extend(bound.arguments.get(parameter.name, ()))
                elif parameter.kind is Parameter.KEYWORD_ONLY:
                    keywords[parameter.name] = bound.arguments[parameter.name]
                elif parameter.kind is Parameter.VAR_KEYWORD:
                    keywords.update(bound.arguments.get(parameter.name, {}))

            results.append(function(*positional, **keywords))

        if len(results) == 1:
            return results[0]
        return tuple(results)

    update_wrapper(wrapper, functions[-1])
    wrapper.__signature__ = merged_signature

    if name:
        wrapper.__name__ = name
        wrapper.__qualname__ = name
    if doc is not None:
        wrapper.__doc__ = doc

    return wrapper


def _strip_parameter_annotations(signature: Signature) -> Signature:
    """Return a signature with parameter annotations removed."""

    parameters = [parameter.replace(annotation=Parameter.empty) for parameter in signature.parameters.values()]
    return signature.replace(parameters=parameters)


def _merge_parameter(existing: Parameter, new: Parameter) -> Parameter:
    """Merge parameter metadata, preferring previously established values."""

    if existing.kind is not new.kind:
        raise SignatureConflictError(f"Parameter '{existing.name}' kind conflict: {existing.kind} vs {new.kind}")

    default = existing.default
    if default is Parameter.empty:
        default = new.default
    elif new.default is not Parameter.empty and new.default != default:
        raise SignatureConflictError(f"Parameter '{existing.name}' default conflict")

    annotation = existing.annotation
    if annotation is Parameter.empty:
        annotation = new.annotation
    elif new.annotation is not Parameter.empty and new.annotation != annotation:
        raise SignatureConflictError(f"Parameter '{existing.name}' annotation conflict")

    return existing.replace(default=default, annotation=annotation)


def _merge_return_annotation(current: Any, new: Any) -> Any:
    """Merge return annotations, preferring previously established values."""

    if current is Signature.empty:
        return new
    if new is Signature.empty or new == current:
        return current
    raise SignatureConflictError("Return annotation conflict")
