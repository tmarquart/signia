"""Public surface guardrails for Signia."""

from signia import SigniaWarning


def test_signia_warning_is_warning():
    """Ensure the exported warning derives from :class:`Warning`."""

    assert issubclass(SigniaWarning, Warning)
