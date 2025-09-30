"""Core Signia functionality."""

from __future__ import annotations

from collections import OrderedDict
from functools import update_wrapper, wraps
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


_PARAMETER_KIND_ORDER = (
    Parameter.POSITIONAL_ONLY,
    Parameter.POSITIONAL_OR_KEYWORD,
    Parameter.VAR_POSITIONAL,
    Parameter.KEYWORD_ONLY,
    Parameter.VAR_KEYWORD,
)


ConflictDetail = tuple[str, Any, Any]
ConflictResolver = Callable[[str, Parameter, Parameter, tuple[ConflictDetail, ...]], Parameter]


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


def merge_signatures(
    *callables: Callable[..., Any] | Signature,
    policy: str = "prefer-first",
    on_conflict: str | ConflictResolver | None = None,
    compare_defaults: bool = True,
    compare_annotations: bool = True,
) -> Signature:
    """Merge callables into a single :class:`inspect.Signature`.

    Parameters
    ----------
    *callables:
        Callables or :class:`inspect.Signature` instances to merge.  Parameters
        are grouped by kind (positional-only, positional-or-keyword, variadic
        positional, keyword-only, variadic keyword) to produce a valid merged
        ordering.
    policy:
        Controls which side supplies metadata when no conflict is detected.
        ``"prefer-first"`` (default) keeps the earliest-seen parameter while
        borrowing defaults or annotations from later definitions.  ``"prefer-last"``
        does the opposite.
    on_conflict:
        Strategy invoked when parameters disagree according to the comparison
        rules.  ``None``/``"raise"`` raises :class:`SignatureConflictError`.
        ``"prefer-annotated"`` keeps whichever candidate includes an annotation,
        ``"prefer-defaulted"`` keeps whichever declares a default, and a callable
        may be supplied for custom resolution.  Resolver callables receive
        ``(name, existing, incoming, conflicts)`` where ``conflicts`` is a tuple of
        ``(kind, existing_value, incoming_value)`` triples, and must return an
        :class:`inspect.Parameter`.
    compare_defaults / compare_annotations:
        When ``True`` (default) differing defaults or annotations count as
        conflicts.  Disable these flags to allow the current ``policy`` to decide
        which value to keep instead.

    Notes
    -----
    * Return annotations are always taken from the right-most callable that
      provides a non-empty annotation.
    * Conflicts include the mismatching metadata in their error messages and can
      be resolved with the built-in strategies or a custom resolver.  For example::

          >>> def left(x: int, y: int = 1):
          ...     ...
          >>> def right(x: int, y: int = 2):
          ...     ...
          >>> merge_signatures(left, right)
          Traceback (most recent call last):
          ...
          SignatureConflictError: Parameter 'y' conflict: default 1 vs 2

          >>> merge_signatures(left, right, compare_defaults=False)
          <Signature (x: int, y: int = 1)>

          >>> merge_signatures(left, right, on_conflict="prefer-defaulted", policy="prefer-last")
          <Signature (x: int, y: int = 2)>

    Returns
    -------
    :class:`inspect.Signature`
        Signature comprising the merged parameters and return annotation.
    """

    if not callables:
        raise ValueError("merge_signatures requires at least one callable")

    normalised_policy = _normalise_policy(policy)
    resolver = _normalise_resolver(on_conflict)

    buckets = _initial_parameter_buckets()
    name_to_parameter: dict[str, Parameter] = {}
    name_to_kind: dict[str, Any] = {}

    return_annotation = Signature.empty

    for target in callables:
        signature = _ensure_signature(target)

        for parameter in signature.parameters.values():
            existing = name_to_parameter.get(parameter.name)
            if existing is None:
                _add_parameter_to_buckets(buckets, parameter)
                name_to_parameter[parameter.name] = parameter
                name_to_kind[parameter.name] = parameter.kind
                continue

            merged = _merge_parameter_metadata(
                parameter.name,
                existing,
                parameter,
                normalised_policy,
                resolver,
                compare_defaults,
                compare_annotations,
            )

            previous_kind = name_to_kind[parameter.name]
            if previous_kind is merged.kind:
                buckets[previous_kind][parameter.name] = merged
            else:
                del buckets[previous_kind][parameter.name]
                buckets[merged.kind][parameter.name] = merged
                name_to_kind[parameter.name] = merged.kind

            name_to_parameter[parameter.name] = merged

        if signature.return_annotation is not Signature.empty:
            return_annotation = signature.return_annotation

    merged_parameters = list(_iter_bucketed_parameters(buckets))
    return Signature(parameters=merged_parameters, return_annotation=return_annotation)


def combine(
    *functions: Callable[..., Any],
    name: str | None = None,
    doc: str | None = None,
) -> Callable[..., Any]:
    """Combine callables while routing keyword arguments to later functions.

    Parameters
    ----------
    *functions:
        Callables to combine.  The first callable supplies the public interface
        and its return value becomes the wrapper's result, while later callables
        receive any keyword arguments it does not accept.
    name:
        Optional override for the resulting wrapper's ``__name__`` and
        ``__qualname__``.
    doc:
        Optional override for the resulting wrapper's ``__doc__``.

    Examples
    --------
    Keyword-only arguments can be routed to helper functions while the primary
    callable keeps a clean signature.

    >>> def load(path: str, *, encoding: str = "utf-8") -> str:
    ...     return path.upper()
    >>> def audit(*, logger: list[str]) -> None:
    ...     logger.append("load called")
    >>> calls: list[str] = []
    >>> wrapped = combine(load, audit)
    >>> wrapped("demo.txt", logger=calls)
    'DEMO.TXT'
    >>> calls
    ['load called']

    ``combine`` works for methods as well, keeping ``self`` handling intact
    while forwarding extra keyword arguments to supporting hooks.

    >>> class Greeter:
    ...     def greet(self, name: str) -> str:
    ...         return f"Hello {name}!"
    ...
    ...     def log(self, *, history: list[str]) -> None:
    ...         history.append("greeted")
    ...
    ...     call = combine(greet, log)
    >>> history: list[str] = []
    >>> Greeter().call("Ada", history=history)
    'Hello Ada!'
    >>> history
    ['greeted']
    """

    if not functions:
        raise ValueError("combine requires at least one callable")

    merged_signature = merge_signatures(*functions)
    primary, *secondary = functions
    signatures = [inspect.signature(function) for function in functions]

    def _has_var_keyword(signature: Signature) -> bool:
        return any(parameter.kind is Parameter.VAR_KEYWORD for parameter in signature.parameters.values())

    def _drop_unknown_kwargs(
        signature: Signature, incoming: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not incoming:
            return {}, {}
        if _has_var_keyword(signature):
            return dict(incoming), {}

        accepted = {
            name
            for name, parameter in signature.parameters.items()
            if parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
        }
        known = {name: incoming[name] for name in incoming if name in accepted}
        leftover = {name: value for name, value in incoming.items() if name not in accepted}
        return known, leftover

    def _bind_arguments(signature: Signature, values: OrderedDict[str, Any], extra_kwargs: dict[str, Any]) -> inspect.BoundArguments:
        positional: list[Any] = []
        keywords: dict[str, Any] = dict(extra_kwargs)

        for parameter in signature.parameters.values():
            if parameter.kind is Parameter.POSITIONAL_ONLY:
                if parameter.name in values:
                    positional.append(values[parameter.name])
            elif parameter.kind is Parameter.POSITIONAL_OR_KEYWORD:
                if parameter.name in values and parameter.name not in keywords:
                    positional.append(values[parameter.name])
            elif parameter.kind is Parameter.VAR_POSITIONAL:
                positional.extend(values.get(parameter.name, ()))
            elif parameter.kind is Parameter.KEYWORD_ONLY:
                if parameter.name in values and parameter.name not in keywords:
                    keywords[parameter.name] = values[parameter.name]
            elif parameter.kind is Parameter.VAR_KEYWORD:
                remainder = dict(values.get(parameter.name, {}))
                remainder.update(keywords)
                keywords = remainder

        return signature.bind_partial(*positional, **keywords)

    @wraps(primary)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        bound_all = merged_signature.bind(*args, **kwargs)
        bound_all.apply_defaults()
        arguments = bound_all.arguments

        remaining_kwargs = dict(kwargs)
        known, remaining_kwargs = _drop_unknown_kwargs(signatures[0], remaining_kwargs)
        bound_primary = _bind_arguments(signatures[0], arguments, known)
        result = primary(*bound_primary.args, **bound_primary.kwargs)

        for function, signature in zip(secondary, signatures[1:]):
            known, remaining_kwargs = _drop_unknown_kwargs(signature, remaining_kwargs)
            bound = _bind_arguments(signature, arguments, known)
            function(*bound.args, **bound.kwargs)

        if remaining_kwargs:
            unexpected = next(iter(remaining_kwargs))
            function_name = name or primary.__name__
            raise TypeError(
                f"{function_name}() got an unexpected keyword argument '{unexpected}'"
            )

        return result

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


def _initial_parameter_buckets() -> dict[Any, OrderedDict[str, Parameter]]:
    """Return empty parameter buckets keyed by :class:`inspect._ParameterKind`."""

    return {kind: OrderedDict() for kind in _PARAMETER_KIND_ORDER}


def _add_parameter_to_buckets(
    buckets: dict[Any, OrderedDict[str, Parameter]], parameter: Parameter
) -> None:
    """Add *parameter* to the bucket matching its kind."""

    buckets[parameter.kind][parameter.name] = parameter


def _iter_bucketed_parameters(
    buckets: dict[Any, OrderedDict[str, Parameter]]
):
    """Yield parameters from *buckets* in canonical kind order."""

    for kind in _PARAMETER_KIND_ORDER:
        yield from buckets[kind].values()


def _normalise_policy(policy: str) -> str:
    """Validate and normalise the merge *policy* argument."""

    allowed = {"prefer-first", "prefer-last"}
    if policy not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"Unsupported policy '{policy}'. Choose one of: {choices}.")
    return policy


def _normalise_resolver(
    on_conflict: str | ConflictResolver | None,
):
    """Validate and normalise the *on_conflict* argument."""

    if on_conflict is None:
        return None
    if callable(on_conflict):
        return on_conflict
    allowed = {"raise", "prefer-annotated", "prefer-defaulted"}
    if on_conflict not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(
            f"Unsupported on_conflict strategy '{on_conflict}'. Choose one of: {choices}."
        )
    return on_conflict


def _merge_parameter_metadata(
    name: str,
    existing: Parameter,
    incoming: Parameter,
    policy: str,
    resolver: str | ConflictResolver | None,
    compare_defaults: bool,
    compare_annotations: bool,
) -> Parameter:
    """Merge metadata for a parameter encountered multiple times."""

    primary, secondary = _apply_policy(existing, incoming, policy)
    conflicts = _detect_parameter_conflicts(primary, secondary, compare_defaults, compare_annotations)

    if conflicts:
        resolved, source = _resolve_parameter_conflict(
            name,
            existing,
            incoming,
            conflicts,
            policy,
            resolver,
        )
        if resolved is None:
            _raise_parameter_conflict(name, conflicts)
        if resolved.name != name:
            raise SignatureConflictError(
                f"Conflict resolver must keep parameter name '{name}', got '{resolved.name}'."
            )

        counterpart: Parameter | None
        if source == "existing":
            counterpart = incoming
        elif source == "incoming":
            counterpart = existing
        else:
            counterpart = None

        if counterpart is not None:
            resolved = _finalise_resolved_parameter(resolved, counterpart, conflicts)
        return resolved

    default = primary.default
    if default is Parameter.empty and secondary.default is not Parameter.empty:
        default = secondary.default

    annotation = primary.annotation
    if annotation is Parameter.empty and secondary.annotation is not Parameter.empty:
        annotation = secondary.annotation

    return primary.replace(default=default, annotation=annotation)


def _apply_policy(existing: Parameter, incoming: Parameter, policy: str) -> tuple[Parameter, Parameter]:
    """Return the (primary, secondary) parameters according to *policy*."""

    if policy == "prefer-last":
        return incoming, existing
    return existing, incoming


def _detect_parameter_conflicts(
    primary: Parameter,
    secondary: Parameter,
    compare_defaults: bool,
    compare_annotations: bool,
) -> list[ConflictDetail]:
    """Return a list of conflict descriptors between two parameters."""

    conflicts: list[ConflictDetail] = []

    if primary.kind is not secondary.kind:
        conflicts.append(("kind", primary.kind, secondary.kind))

    if (
        compare_defaults
        and primary.default is not Parameter.empty
        and secondary.default is not Parameter.empty
        and primary.default != secondary.default
    ):
        conflicts.append(("default", primary.default, secondary.default))

    if (
        compare_annotations
        and primary.annotation is not Parameter.empty
        and secondary.annotation is not Parameter.empty
        and primary.annotation != secondary.annotation
    ):
        conflicts.append(("annotation", primary.annotation, secondary.annotation))

    return conflicts


def _resolve_parameter_conflict(
    name: str,
    existing: Parameter,
    incoming: Parameter,
    conflicts: list[ConflictDetail],
    policy: str,
    resolver: str | ConflictResolver | None,
) -> tuple[Parameter | None, str]:
    """Resolve a parameter conflict according to *resolver* and *policy*."""

    if callable(resolver):
        resolved = resolver(name, existing, incoming, tuple(conflicts))
        if not isinstance(resolved, Parameter):
            raise TypeError("on_conflict callable must return an inspect.Parameter instance")
        return resolved, "custom"

    if resolver in (None, "raise"):
        return None, "unresolved"

    if resolver == "prefer-annotated":
        return _select_parameter_candidate(
            existing,
            incoming,
            policy,
            lambda parameter: parameter.annotation is not Parameter.empty,
        )

    if resolver == "prefer-defaulted":
        return _select_parameter_candidate(
            existing,
            incoming,
            policy,
            lambda parameter: parameter.default is not Parameter.empty,
        )

    raise ValueError(f"Unknown on_conflict strategy: {resolver}")


def _select_parameter_candidate(
    existing: Parameter,
    incoming: Parameter,
    policy: str,
    predicate: Callable[[Parameter], bool],
) -> tuple[Parameter, str]:
    """Select a parameter based on *predicate* and *policy*."""

    candidates: list[tuple[str, Parameter]] = []
    if predicate(existing):
        candidates.append(("existing", existing))
    if predicate(incoming):
        candidates.append(("incoming", incoming))

    if not candidates:
        candidates = [("existing", existing), ("incoming", incoming)]

    if policy == "prefer-last":
        source, parameter = candidates[-1]
    else:
        source, parameter = candidates[0]

    return parameter, source


def _finalise_resolved_parameter(
    resolved: Parameter,
    counterpart: Parameter,
    conflicts: list[ConflictDetail],
) -> Parameter:
    """Fill in missing metadata on *resolved* using *counterpart* when safe."""

    conflict_types = {kind for kind, _, _ in conflicts}
    updated = resolved

    if (
        "default" not in conflict_types
        and updated.default is Parameter.empty
        and counterpart.default is not Parameter.empty
    ):
        updated = updated.replace(default=counterpart.default)

    if (
        "annotation" not in conflict_types
        and updated.annotation is Parameter.empty
        and counterpart.annotation is not Parameter.empty
    ):
        updated = updated.replace(annotation=counterpart.annotation)

    return updated


def _raise_parameter_conflict(name: str, conflicts: list[ConflictDetail]) -> None:
    """Raise :class:`SignatureConflictError` with detailed conflict information."""

    parts: list[str] = []
    for conflict_type, existing_value, incoming_value in conflicts:
        if conflict_type == "kind":
            left = getattr(existing_value, "name", existing_value)
            right = getattr(incoming_value, "name", incoming_value)
            parts.append(f"kind {left} vs {right}")
        elif conflict_type == "default":
            parts.append(f"default {existing_value!r} vs {incoming_value!r}")
        elif conflict_type == "annotation":
            parts.append(f"annotation {existing_value!r} vs {incoming_value!r}")
        else:
            parts.append(conflict_type)

    detail = ", ".join(parts)
    raise SignatureConflictError(f"Parameter '{name}' conflict: {detail}")
