"""Public Signia API."""

from ._core import (
    CallVars,
    SignatureConflictError,
    combine,
    merge_signatures,
    mirror_signature,
    same_signature,
)

__all__ = [
    "CallVars",
    "SignatureConflictError",
    "combine",
    "merge_signatures",
    "mirror_signature",
    "same_signature",
    "__version__",
]

__version__ = "0.1.0"
