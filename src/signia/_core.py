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


def mirror_signature(target: Callable[..., Any], source: Callable[..., Any]) -> Callable[..., Any]:
    """Mirror ``source``'s signature and metadata onto ``target``."""

    update_wrapper(target, source)
    target.__signature__ = inspect.signature(source)
    return target


def same_signature(
    first: Callable[..., Any],
    second: Callable[..., Any],
    *,
    check_parameter_annotations: bool = True,
    check_return_annotation: bool = True,
) -> bool:
    """Return ``True`` when two callables share the same signature."""

    signature_a = inspect.signature(first)
    signature_b = inspect.signature(second)

    if not check_parameter_annotations:
        signature_a = _strip_parameter_annotations(signature_a)
        signature_b = _strip_parameter_annotations(signature_b)

    if not check_return_annotation:
        signature_a = signature_a.replace(return_annotation=Signature.empty)
        signature_b = signature_b.replace(return_annotation=Signature.empty)

    return signature_a == signature_b


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
