"""
Backend i18n module for DetourAI.
Provides t(key, lang, **params) for translating error messages and SSE event text.
"""
import json
from pathlib import Path
from typing import Dict, Optional

SUPPORTED_LANGUAGES = {"de", "en", "hi"}
DEFAULT_LANGUAGE = "de"

_cache: Dict[str, Dict[str, str]] = {}
_I18N_DIR = Path(__file__).parent.parent / "i18n"


def _load_language(lang: str) -> Dict[str, str]:
    """Load and cache a translation JSON file."""
    if lang in _cache:
        return _cache[lang]
    path = _I18N_DIR / f"{lang}.json"
    try:
        with open(path, encoding="utf-8") as f:
            _cache[lang] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _cache[lang] = {}
    return _cache[lang]


def t(key: str, lang: str, **params: object) -> str:
    """
    Translate a key for the given language with optional parameter interpolation.
    Falls back to German if key not found, then to the key itself.
    """
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    translations = _load_language(lang)
    val = translations.get(key)
    if val is None and lang != DEFAULT_LANGUAGE:
        val = _load_language(DEFAULT_LANGUAGE).get(key)
    if val is None:
        return key
    if params:
        for k, v in params.items():
            val = val.replace(f"{{{k}}}", str(v))
    return val


def get_request_language(accept_language: Optional[str] = None) -> str:
    """
    Extract language from Accept-Language header value.
    Returns first supported language or default.
    """
    if not accept_language:
        return DEFAULT_LANGUAGE
    # Parse "de, en-US;q=0.9, hi;q=0.8" style headers
    for part in accept_language.split(","):
        lang = part.strip().split("-")[0].split(";")[0].strip().lower()
        if lang in SUPPORTED_LANGUAGES:
            return lang
    return DEFAULT_LANGUAGE


def clear_cache() -> None:
    """Clear translation cache (useful for testing)."""
    _cache.clear()
