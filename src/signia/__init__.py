"""Public Signia API."""

from ._core import (
    SignatureConflictError,
    combine,
    merge_signatures,
    mirror_signature,
    same_signature,
)

__all__ = [
    "SignatureConflictError",
    "combine",
    "merge_signatures",
    "mirror_signature",
    "same_signature",
    "__version__",
]

__version__ = "0.1.0"
