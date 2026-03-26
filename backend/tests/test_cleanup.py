"""Regression guards for SHR-04 cleanup — output_generator must stay removed."""
import pytest


def test_no_output_generator():
    """Importing agents.output_generator must raise ImportError after SHR-04 cleanup."""
    with pytest.raises(ImportError):
        import agents.output_generator  # noqa: F401
