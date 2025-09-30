"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pathlib
import sys


def _ensure_src_on_path() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    src = root / "src"
    src_path = str(src)
    if src.exists() and src_path not in sys.path:
        sys.path.insert(0, src_path)


_ensure_src_on_path()


__all__ = []
