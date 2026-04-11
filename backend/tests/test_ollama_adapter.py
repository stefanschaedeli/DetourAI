"""Tests for the Ollama LLM adapter in agents/_client.py.

Covers _OllamaResponse field mapping, _OllamaClient message construction,
and get_client() / get_model() branching logic. All external calls are mocked
so no running Ollama server or Anthropic API key is required.
"""
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers — build fake OpenAI response objects
# ---------------------------------------------------------------------------

def _make_openai_response(
    content="Hello world",
    model="qwen3:32b",
    prompt_tokens=10,
    completion_tokens=20,
):
    """Return a MagicMock shaped like an openai ChatCompletion response."""
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.model = model
    response.usage = usage
    return response


# ---------------------------------------------------------------------------
# _OllamaResponse — field mapping
# ---------------------------------------------------------------------------

class TestOllamaResponse:
    def test_content_text_mapped_from_choices(self):
        from agents._client import _OllamaResponse
        raw = _make_openai_response(content="Test response text")
        resp = _OllamaResponse(raw)
        assert resp.content[0].text == "Test response text"

    def test_model_forwarded(self):
        from agents._client import _OllamaResponse
        raw = _make_openai_response(model="llama3:70b")
        resp = _OllamaResponse(raw)
        assert resp.model == "llama3:70b"

    def test_usage_input_tokens_from_prompt_tokens(self):
        from agents._client import _OllamaResponse
        raw = _make_openai_response(prompt_tokens=42, completion_tokens=7)
        resp = _OllamaResponse(raw)
        assert resp.usage.input_tokens == 42

    def test_usage_output_tokens_from_completion_tokens(self):
        from agents._client import _OllamaResponse
        raw = _make_openai_response(prompt_tokens=42, completion_tokens=7)
        resp = _OllamaResponse(raw)
        assert resp.usage.output_tokens == 7

    def test_missing_usage_defaults_to_zero(self):
        """When openai_response.usage is None, tokens should default to 0."""
        from agents._client import _OllamaResponse
        raw = _make_openai_response()
        raw.usage = None
        resp = _OllamaResponse(raw)
        assert resp.usage.input_tokens == 0
        assert resp.usage.output_tokens == 0

    def test_none_token_fields_default_to_zero(self):
        """When usage exists but individual token counts are None, default to 0."""
        from agents._client import _OllamaResponse
        raw = _make_openai_response()
        raw.usage.prompt_tokens = None
        raw.usage.completion_tokens = None
        resp = _OllamaResponse(raw)
        assert resp.usage.input_tokens == 0
        assert resp.usage.output_tokens == 0

    def test_empty_content_becomes_empty_string(self):
        """None message content should become an empty string, not raise."""
        from agents._client import _OllamaResponse
        raw = _make_openai_response(content=None)
        resp = _OllamaResponse(raw)
        assert resp.content[0].text == ""

    def test_content_block_has_text_attribute(self):
        from agents._client import _ContentBlock
        block = _ContentBlock("hello")
        assert block.text == "hello"

    def test_usage_has_token_attributes(self):
        from agents._client import _Usage
        usage = _Usage(input_tokens=5, output_tokens=15)
        assert usage.input_tokens == 5
        assert usage.output_tokens == 15


# ---------------------------------------------------------------------------
# _OllamaClient — message construction
# ---------------------------------------------------------------------------

def _make_oai_mock(content="ok"):
    """Return (mock_openai_cls, mock_instance) ready for patching sys.modules['openai'].OpenAI."""
    fake_response = _make_openai_response(content=content)
    mock_instance = MagicMock()
    mock_instance.chat.completions.create.return_value = fake_response
    mock_cls = MagicMock(return_value=mock_instance)
    return mock_cls, mock_instance


class TestOllamaClientCreate:
    def _fresh_client(self, mock_oai_cls):
        """Instantiate _OllamaClient with a patched openai.OpenAI constructor."""
        sys.modules["openai"].OpenAI = mock_oai_cls
        # Re-import to pick up the patched OpenAI
        import importlib
        import agents._client as _client_mod
        importlib.reload(_client_mod)
        return _client_mod._OllamaClient(base_url="http://localhost:11434/v1/")

    def test_system_prompt_becomes_first_message(self):
        """System prompt must be prepended as {role: system} before user messages."""
        mock_cls, mock_instance = _make_oai_mock()
        client = self._fresh_client(mock_cls)

        client.messages.create(
            model="qwen3:32b",
            system="You are a travel guide.",
            messages=[{"role": "user", "content": "Plan my trip"}],
            max_tokens=512,
        )

        call_kwargs = mock_instance.chat.completions.create.call_args
        oai_messages = call_kwargs.kwargs["messages"]
        assert oai_messages[0] == {"role": "system", "content": "You are a travel guide."}

    def test_user_messages_appended_after_system(self):
        """Original messages list is appended after the system message."""
        mock_cls, mock_instance = _make_oai_mock()
        client = self._fresh_client(mock_cls)

        user_msg = {"role": "user", "content": "Where should I go?"}
        client.messages.create(
            model="qwen3:32b",
            system="You are a guide.",
            messages=[user_msg],
            max_tokens=256,
        )

        call_kwargs = mock_instance.chat.completions.create.call_args
        oai_messages = call_kwargs.kwargs["messages"]
        assert len(oai_messages) == 2
        assert oai_messages[1] == user_msg

    def test_max_tokens_passed_through(self):
        """max_tokens value must be forwarded to the OpenAI call unchanged."""
        mock_cls, mock_instance = _make_oai_mock()
        client = self._fresh_client(mock_cls)

        client.messages.create(
            model="qwen3:32b",
            system="sys",
            messages=[],
            max_tokens=1024,
        )

        call_kwargs = mock_instance.chat.completions.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 1024

    def test_model_passed_through(self):
        """model name must be forwarded to the OpenAI call unchanged."""
        mock_cls, mock_instance = _make_oai_mock()
        client = self._fresh_client(mock_cls)

        client.messages.create(
            model="llama3:70b-q4",
            system="sys",
            messages=[],
            max_tokens=128,
        )

        call_kwargs = mock_instance.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "llama3:70b-q4"

    def test_create_returns_ollama_response(self):
        """Return value of messages.create() must be an _OllamaResponse instance."""
        mock_cls, mock_instance = _make_oai_mock(content="result")
        client = self._fresh_client(mock_cls)

        import agents._client as _client_mod
        result = client.messages.create(
            model="qwen3:32b",
            system="sys",
            messages=[],
            max_tokens=128,
        )

        assert isinstance(result, _client_mod._OllamaResponse)
        assert result.content[0].text == "result"

    def test_multiple_messages_all_appended(self):
        """A multi-turn conversation must have all messages after the system message."""
        mock_cls, mock_instance = _make_oai_mock()
        client = self._fresh_client(mock_cls)

        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        client.messages.create(
            model="qwen3:32b",
            system="sys",
            messages=msgs,
            max_tokens=128,
        )

        call_kwargs = mock_instance.chat.completions.create.call_args
        oai_messages = call_kwargs.kwargs["messages"]
        assert len(oai_messages) == 4  # 1 system + 3 user/assistant
        assert oai_messages[1:] == msgs


# ---------------------------------------------------------------------------
# get_client() — branching
# ---------------------------------------------------------------------------

class TestGetClient:
    def test_returns_ollama_client_when_use_local_llm_true(self):
        """When use_local_llm=True, get_client() must return an _OllamaClient."""
        mock_cls, _ = _make_oai_mock()
        sys.modules["openai"].OpenAI = mock_cls

        import importlib
        import agents._client as _client_mod
        importlib.reload(_client_mod)

        # Reset cached singleton so a new client is always created
        _client_mod._ollama_client = None
        _client_mod._ollama_endpoint = None

        def setting_side_effect(key):
            if key == "system.use_local_llm":
                return True
            if key == "system.ollama_endpoint":
                return "http://localhost:11434/v1/"
            return None

        with patch.object(_client_mod, "get_setting", side_effect=setting_side_effect):
            result = _client_mod.get_client()

        assert isinstance(result, _client_mod._OllamaClient)

    def test_returns_anthropic_client_when_use_local_llm_false(self):
        """When use_local_llm=False, get_client() must return an anthropic.Anthropic."""
        import importlib
        import agents._client as _client_mod
        importlib.reload(_client_mod)

        _client_mod._client = None  # force fresh Anthropic client creation

        with patch.object(_client_mod, "get_setting", return_value=False), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-abc"}):
            result = _client_mod.get_client()

        import anthropic
        assert isinstance(result, anthropic.Anthropic)


# ---------------------------------------------------------------------------
# get_model() — branching
# ---------------------------------------------------------------------------

class TestGetModel:
    def _reload(self):
        import importlib
        import agents._client as _client_mod
        importlib.reload(_client_mod)
        return _client_mod

    def test_returns_ollama_model_when_use_local_llm(self):
        """When use_local_llm=True, get_model() returns the configured ollama model."""
        mod = self._reload()

        def side_effect(key):
            if key == "system.use_local_llm":
                return True
            if key == "system.ollama_model":
                return "qwen3:32b"
            return None

        with patch.object(mod, "get_setting", side_effect=side_effect):
            result = mod.get_model("claude-opus-4-5", "route_architect")

        assert result == "qwen3:32b"

    def test_returns_haiku_in_test_mode(self):
        """When use_local_llm=False and test_mode=True, returns claude-haiku-4-5."""
        mod = self._reload()

        def side_effect(key):
            if key == "system.use_local_llm":
                return False
            if key == "system.test_mode":
                return True
            return None

        with patch.object(mod, "get_setting", side_effect=side_effect):
            result = mod.get_model("claude-opus-4-5", "route_architect")

        assert result == "claude-haiku-4-5"

    def test_returns_prod_model_when_not_test_mode(self):
        """When use_local_llm=False and test_mode=False, returns the prod_model."""
        mod = self._reload()

        def side_effect(key):
            if key == "system.use_local_llm":
                return False
            if key == "system.test_mode":
                return False
            return None  # no per-agent override

        # Also neutralise the TEST_MODE env var to avoid the fallback path
        with patch.object(mod, "get_setting", side_effect=side_effect), \
             patch.dict(os.environ, {"TEST_MODE": "false"}):
            result = mod.get_model("claude-opus-4-5")

        assert result == "claude-opus-4-5"

    def test_returns_prod_model_with_agent_key_no_override(self):
        """With agent_key but no stored override, returns prod_model."""
        mod = self._reload()

        def side_effect(key):
            if key == "system.use_local_llm":
                return False
            if key == "system.test_mode":
                return False
            return None  # no agent-specific override

        with patch.object(mod, "get_setting", side_effect=side_effect), \
             patch.dict(os.environ, {"TEST_MODE": "false"}):
            result = mod.get_model("claude-sonnet-4-5", "travel_guide")

        assert result == "claude-sonnet-4-5"

    def test_env_var_test_mode_fallback(self):
        """When system.test_mode setting is None, falls back to TEST_MODE env var."""
        mod = self._reload()

        def side_effect(key):
            if key == "system.use_local_llm":
                return False
            if key == "system.test_mode":
                return None  # triggers env var fallback
            return None

        with patch.object(mod, "get_setting", side_effect=side_effect), \
             patch.dict(os.environ, {"TEST_MODE": "false"}):
            result = mod.get_model("claude-opus-4-5")

        assert result == "claude-opus-4-5"

    def test_env_var_test_mode_fallback_true(self):
        """When system.test_mode is None and TEST_MODE env var is true, returns haiku."""
        mod = self._reload()

        def side_effect(key):
            if key == "system.use_local_llm":
                return False
            if key == "system.test_mode":
                return None
            return None

        with patch.object(mod, "get_setting", side_effect=side_effect), \
             patch.dict(os.environ, {"TEST_MODE": "true"}):
            result = mod.get_model("claude-opus-4-5")

        assert result == "claude-haiku-4-5"

    def test_ollama_model_default_when_not_configured(self):
        """When ollama_model setting is None, get_model() falls back to qwen3:32b."""
        mod = self._reload()

        def side_effect(key):
            if key == "system.use_local_llm":
                return True
            if key == "system.ollama_model":
                return None  # not configured — should trigger hardcoded fallback
            return None

        with patch.object(mod, "get_setting", side_effect=side_effect):
            result = mod.get_model("claude-opus-4-5")

        assert result == "qwen3:32b"
