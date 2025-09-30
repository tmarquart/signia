# signia

> **Signature tools for Python**  
> *Mirror, compare, merge, and compose callables — IDE-friendly and type-aware.*

---

## ✨ What is Signia?

Signia is a lightweight toolkit for working with Python function signatures.  
It makes your wrappers, decorators, and composed functions **look and feel right** to IDEs, linters, and `help()`.

With Signia you can:

- **Mirror** another function’s signature (`mirror_signature`)
- **Compare** signatures for equality or compatibility (`same_signature`)
- **Merge** multiple signatures into a single `inspect.Signature` (`merge_signatures`)
- **Combine** functions with merged signatures and real argument routing (`combine`)

Perfect for decorators, adapters, and function composition.

---

## 📦 Installation

Signia targets Python 3.9+ and is published to PyPI.

```bash
python -m pip install signia
```

Add it to your project's dependencies (``pyproject.toml``/``requirements.txt``)
and you are ready to work with signatures in a type-friendly way.

---

## 🚀 Quickstart

Below are concise examples of each public helper exported from
``signia``.  All snippets can be copied into a Python REPL or script.

### `mirror_signature`

```python
from signia import mirror_signature

def greet(name: str, excited: bool = False) -> str:
    return f"Hello {name}{'!' if excited else ''}"

@mirror_signature(greet)
def wrapper(*args, **kwargs):
    return greet(*args, **kwargs)

assert wrapper.__name__ == "greet"
assert wrapper.__signature__.parameters["name"].annotation is str
```

The decorator mirrors the wrapped callable's name, documentation, and
``inspect.Signature`` so IDEs and type checkers understand the wrapper.

### `same_signature`

```python
from signia import same_signature

def source(x: int, y: int = 1) -> int:
    return x + y

def mirror(x: int, y: int = 1) -> int:
    return source(x, y)

assert same_signature(source, mirror)
assert same_signature(source, mirror, strict=False)

def variant(x: int, y: int = 2) -> int:
    return x + y

assert not same_signature(source, variant)
assert same_signature(source, variant, strict=False)
assert same_signature(source, variant, strict=False, ignore_annotations=True)
```

Pass callables (or ``inspect.Signature`` instances) to test for strict equality or
structural compatibility, optionally ignoring default mismatches or annotations.

### `merge_signatures`

```python
from signia import merge_signatures

def left(x: int, *, limit: int = 10) -> None:
    ...

def right(y: str, *, limit: int = 10, verbose: bool = False) -> None:
    ...

merged = merge_signatures(left, right)
assert str(merged) == "(x: int, y: str, *, limit: int = 10, verbose: bool = False)"

custom_policy = merge_signatures(
    left,
    right,
    policy="prefer-last",  # choose metadata from later callables when possible
)
```

The merger walks parameters in kind order, keeping metadata according to the
selected ``policy`` (``"prefer-first"`` by default) and returning a new
``inspect.Signature``.  Return annotations come from the right-most callable with
a non-empty annotation.

### `combine`

```python
from signia import combine

def load(path: str, *, encoding: str = "utf-8") -> str:
    return path.upper()

def audit(*, logger: list[str]) -> None:
    logger.append("load called")

calls: list[str] = []
wrapped = combine(load, audit)
assert wrapped("demo.txt", logger=calls) == "DEMO.TXT"
assert calls == ["load called"]
```

``combine`` uses ``merge_signatures`` under the hood so that a single callable can
forward keyword-only arguments to later helpers while keeping the primary
signature intact.

---

## 🧩 Handling Signature Conflicts

When merging or combining callables, Signia compares parameter kind, default
values, and annotations.  Differing metadata is reported through
``SignatureConflictError`` unless a resolver strategy is supplied.

```python
from inspect import Parameter
from signia import merge_signatures, SignatureConflictError

def alpha(x: int, y: int = 1):
    ...

def beta(x: int, y: int = 2):
    ...

try:
    merge_signatures(alpha, beta)
except SignatureConflictError as exc:
    assert "default 1 vs 2" in str(exc)

merge_signatures(alpha, beta, compare_defaults=False)  # tolerates default mismatch

prefer_defaults = merge_signatures(alpha, beta, on_conflict="prefer-defaulted", policy="prefer-last")
assert prefer_defaults.parameters["y"].default == 2

def resolver(name, existing, incoming, conflicts):
    # Keep whichever side is annotated, otherwise fall back to the default policy.
    if any(kind == "annotation" for kind, *_ in conflicts):
        return incoming if incoming.annotation is not Parameter.empty else existing
    return incoming

custom = merge_signatures(alpha, beta, on_conflict=resolver)
```

Custom resolvers receive the conflicting ``inspect.Parameter`` objects alongside
their metadata differences and must return a replacement ``Parameter``.  This
allows fine-grained reconciliation that aligns perfectly with your project's
needs.
