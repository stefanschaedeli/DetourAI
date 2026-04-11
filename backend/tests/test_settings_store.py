"""Tests for utils/settings_store.py — validation, defaults, and Ollama settings."""
import sys
import os
import tempfile
import pytest

# Redirect DB to a temp directory so tests never touch the real settings.db
_tmp_data = tempfile.mkdtemp()
os.environ["DATA_DIR"] = _tmp_data

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# validate_setting — Ollama-specific keys
# ---------------------------------------------------------------------------

class TestValidateOllamaModel:
    def test_valid_qwen3_model(self):
        """qwen3:32b is a valid ollama model — any string is accepted."""
        from utils.settings_store import validate_setting
        assert validate_setting("system.ollama_model", "qwen3:32b") is None

    def test_valid_llama_model_with_quantization(self):
        """Any non-empty string is a valid ollama model name."""
        from utils.settings_store import validate_setting
        assert validate_setting("system.ollama_model", "llama3:70b-q4") is None

    def test_valid_arbitrary_string(self):
        """Ollama model name is free-form text, not constrained to Claude allowlist."""
        from utils.settings_store import validate_setting
        assert validate_setting("system.ollama_model", "mistral:7b-instruct") is None

    def test_not_constrained_by_claude_allowlist(self):
        """A non-Claude model name must NOT trigger the allowlist rejection."""
        from utils.settings_store import validate_setting
        # This would fail for agent.*.model but must pass for system.ollama_model
        result = validate_setting("system.ollama_model", "phi3:mini")
        assert result is None


class TestValidateOllamaEndpoint:
    def test_valid_http_ip_endpoint(self):
        """An http:// IP-based endpoint URL is valid."""
        from utils.settings_store import validate_setting
        assert validate_setting("system.ollama_endpoint", "http://192.168.1.5:11434/v1/") is None

    def test_valid_localhost_endpoint(self):
        """The default localhost endpoint is valid."""
        from utils.settings_store import validate_setting
        assert validate_setting("system.ollama_endpoint", "http://localhost:11434/v1/") is None

    def test_valid_https_endpoint(self):
        """An https:// endpoint (e.g. tunnelled Ollama) is valid."""
        from utils.settings_store import validate_setting
        assert validate_setting("system.ollama_endpoint", "https://my-ollama.example.com/v1/") is None

    def test_invalid_no_http_prefix(self):
        """A plain hostname without http:// prefix must be rejected."""
        from utils.settings_store import validate_setting
        result = validate_setting("system.ollama_endpoint", "not-a-url")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_invalid_empty_string(self):
        """An empty string does not start with http and must be rejected."""
        from utils.settings_store import validate_setting
        result = validate_setting("system.ollama_endpoint", "")
        assert result is not None

    def test_invalid_ftp_scheme(self):
        """Non-http scheme must be rejected."""
        from utils.settings_store import validate_setting
        result = validate_setting("system.ollama_endpoint", "ftp://localhost/v1/")
        assert result is not None


class TestValidateUseLocalLlm:
    def test_valid_false(self):
        """Boolean False is a valid value for system.use_local_llm."""
        from utils.settings_store import validate_setting
        assert validate_setting("system.use_local_llm", False) is None

    def test_valid_true(self):
        """Boolean True is a valid value for system.use_local_llm."""
        from utils.settings_store import validate_setting
        assert validate_setting("system.use_local_llm", True) is None

    def test_invalid_string(self):
        """A string like 'true' must be rejected — bool required."""
        from utils.settings_store import validate_setting
        result = validate_setting("system.use_local_llm", "true")
        assert result is not None

    def test_invalid_integer(self):
        """Integer 1 must be rejected — bool required."""
        from utils.settings_store import validate_setting
        result = validate_setting("system.use_local_llm", 1)
        assert result is not None


class TestAgentModelAllowlistStillEnforced:
    def test_ollama_model_name_rejected_for_agent_key(self):
        """agent.*.model keys must still enforce the Claude ALLOWED_MODELS allowlist."""
        from utils.settings_store import validate_setting
        result = validate_setting("agent.route_architect.model", "qwen3:32b")
        assert result is not None
        assert isinstance(result, str)

    def test_unknown_claude_model_rejected(self):
        """An unrecognised Claude model name is rejected for agent keys."""
        from utils.settings_store import validate_setting
        result = validate_setting("agent.route_architect.model", "claude-unknown-99")
        assert result is not None

    def test_valid_claude_model_accepted(self):
        """A recognised Claude model is accepted for agent keys."""
        from utils.settings_store import validate_setting
        assert validate_setting("agent.route_architect.model", "claude-opus-4-5") is None


# ---------------------------------------------------------------------------
# get_setting — Ollama defaults
# ---------------------------------------------------------------------------

class TestGetSettingOllamaDefaults:
    def test_use_local_llm_defaults_false(self):
        """system.use_local_llm must default to False when not overridden."""
        from utils.settings_store import get_setting
        assert get_setting("system.use_local_llm") is False

    def test_ollama_model_defaults_to_qwen3(self):
        """system.ollama_model must default to 'qwen3:32b'."""
        from utils.settings_store import get_setting
        assert get_setting("system.ollama_model") == "qwen3:32b"

    def test_ollama_endpoint_defaults_to_localhost(self):
        """system.ollama_endpoint must default to the local Ollama URL."""
        from utils.settings_store import get_setting
        assert get_setting("system.ollama_endpoint") == "http://localhost:11434/v1/"


# ---------------------------------------------------------------------------
# validate_setting — unknown key
# ---------------------------------------------------------------------------

class TestValidateUnknownKey:
    def test_unknown_key_returns_error(self):
        """An unrecognised key must return an error string, not None."""
        from utils.settings_store import validate_setting
        result = validate_setting("system.nonexistent_key", "value")
        assert result is not None
