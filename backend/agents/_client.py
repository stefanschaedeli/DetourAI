"""Shared Anthropic client factory — reads env vars at call time, not import time."""
import os
import anthropic


def get_client() -> anthropic.Anthropic:
    """Return an Anthropic client using the current ANTHROPIC_API_KEY env var."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY ist nicht gesetzt. "
            "Bitte backend/.env mit dem API-Key erstellen."
        )
    return anthropic.Anthropic(api_key=api_key)


def get_model(prod_model: str) -> str:
    """Return the appropriate model based on TEST_MODE env var."""
    test_mode = os.getenv("TEST_MODE", "true").lower() == "true"
    return "claude-haiku-4-5" if test_mode else prod_model
