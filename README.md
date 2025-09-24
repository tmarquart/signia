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