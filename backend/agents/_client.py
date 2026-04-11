"""Shared LLM client factory — Anthropic singleton or Ollama adapter based on settings."""
import os
import anthropic
from utils.settings_store import get_setting

# ---------------------------------------------------------------------------
# Anthropic singleton
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic = None


def get_client():
    """Return the appropriate LLM client based on system.use_local_llm setting.

    Returns an Anthropic client or an _OllamaClient adapter depending on settings.
    Both expose a .messages.create() interface with identical signature and response shape.
    """
    use_local = get_setting("system.use_local_llm")
    if use_local:
        return _get_ollama_client()
    return _get_anthropic_client()


def _get_anthropic_client() -> anthropic.Anthropic:
    """Return the shared Anthropic client, creating it on first call."""
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY ist nicht gesetzt. "
                "Bitte backend/.env mit dem API-Key erstellen."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Ollama adapter — wraps OpenAI client to match Anthropic response shape
# ---------------------------------------------------------------------------

_ollama_client: "_OllamaClient" = None
_ollama_endpoint: str = None


def _get_ollama_client() -> "_OllamaClient":
    """Return the shared Ollama client, recreating it if the endpoint changed."""
    global _ollama_client, _ollama_endpoint
    endpoint = get_setting("system.ollama_endpoint") or "http://localhost:11434/v1/"
    if _ollama_client is None or _ollama_endpoint != endpoint:
        _ollama_client = _OllamaClient(base_url=endpoint)
        _ollama_endpoint = endpoint
    return _ollama_client


class _ContentBlock:
    """Mimics anthropic.types.ContentBlock so response.content[0].text works."""

    def __init__(self, text: str):
        self.text = text


class _Usage:
    """Mimics anthropic.types.Usage — maps OpenAI prompt_tokens/completion_tokens."""

    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _OllamaResponse:
    """Wraps an OpenAI ChatCompletion to look like an anthropic.types.Message.

    Provides .content[0].text, .usage.input_tokens, .usage.output_tokens, .model
    so retry_helper.py and all agents work without modification.
    """

    def __init__(self, openai_response):
        choice = openai_response.choices[0]
        self.content = [_ContentBlock(choice.message.content or "")]
        self.model = openai_response.model
        usage = getattr(openai_response, "usage", None)
        self.usage = _Usage(
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class _Messages:
    """Proxy object so client.messages.create(...) resolves to _OllamaClient.create(...)."""

    def __init__(self, create_fn):
        self.create = create_fn


class _OllamaClient:
    """Drop-in replacement for anthropic.Anthropic that proxies to a local Ollama instance.

    Exposes .messages.create(model=, system=, messages=, max_tokens=) matching
    the Anthropic SDK signature so all existing agent call() closures work unchanged.
    """

    def __init__(self, base_url: str):
        from openai import OpenAI
        self._oai = OpenAI(base_url=base_url, api_key="ollama")
        self.messages = _Messages(self._create)

    def _create(self, *, model: str, system: str, messages: list, max_tokens: int, **kwargs):
        """Convert Anthropic-style call to OpenAI chat completions and return adapter response."""
        oai_messages = [{"role": "system", "content": system}]
        oai_messages.extend(messages)
        response = self._oai.chat.completions.create(
            model=model,
            messages=oai_messages,
            max_tokens=max_tokens,
        )
        return _OllamaResponse(response)


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

def get_model(prod_model: str, agent_key: str = None) -> str:
    """Return the appropriate model based on settings or TEST_MODE env var.

    When system.use_local_llm is enabled, returns the configured Ollama model name.
    Otherwise, applies test_mode and per-agent model overrides for Anthropic.
    """
    use_local = get_setting("system.use_local_llm")
    if use_local:
        return get_setting("system.ollama_model") or "qwen3:32b"
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
