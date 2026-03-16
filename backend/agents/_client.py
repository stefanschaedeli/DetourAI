"""Shared Anthropic client factory — reads env vars at call time, not import time."""
import os
import anthropic
from utils.settings_store import get_setting


def get_client() -> anthropic.Anthropic:
    """Return an Anthropic client using the current ANTHROPIC_API_KEY env var."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY ist nicht gesetzt. "
            "Bitte backend/.env mit dem API-Key erstellen."
        )
    return anthropic.Anthropic(api_key=api_key)


def get_model(prod_model: str, agent_key: str = None) -> str:
    """Return the appropriate model based on settings or TEST_MODE env var."""
    test_mode = get_setting("system.test_mode")
    if test_mode is None:
        test_mode = os.getenv("TEST_MODE", "true").lower() == "true"
    if test_mode:
        return "claude-haiku-4-5"
    if agent_key:
        return get_setting(f"agent.{agent_key}.model") or prod_model
    return prod_model


def get_max_tokens(agent_key: str, default: int) -> int:
    """Return max_tokens from settings for the given agent."""
    val = get_setting(f"agent.{agent_key}.max_tokens")
    return int(val) if val is not None else default
