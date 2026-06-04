from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode

from fastapi import Request


DEFAULT_LANGUAGE = "en"
LANGUAGE_COOKIE = "aquaguard_stats_lang"
SUPPORTED_LANGUAGES = ("en", "el")
TRANSLATIONS_PATH = Path(__file__).resolve().parent / "translations.json"

STATUS_LABEL_KEYS = {
    "Ok": "ok",
    "Limit reached": "limit_reached",
    "Near limit": "near_limit",
    "No active limit": "no_active_limit",
    "Stopped": "stopped",
    "Unknown": "unknown",
}


class Translator:
    def __init__(self, translations: dict[str, Any]) -> None:
        self.translations = translations

    def for_language(self, language: str):
        language = normalize_language(language)

        def translate(key: str, **params: object) -> str:
            value = self._lookup(language, key)
            if value is None:
                value = self._lookup(DEFAULT_LANGUAGE, key)
            if value is None:
                return key
            if params:
                return value.format(**params)
            return value

        return translate

    def month_names(self, language: str) -> list[str]:
        months = self._lookup(normalize_language(language), "months")
        if isinstance(months, list):
            return [str(month) for month in months]
        return [str(month) for month in self._lookup(DEFAULT_LANGUAGE, "months")]

    def _lookup(self, language: str, key: str) -> Any:
        value: Any = self.translations.get(language, {})
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value


def load_translator(path: Path = TRANSLATIONS_PATH) -> Translator:
    return Translator(json.loads(path.read_text(encoding="utf-8")))


def normalize_language(language: str | None) -> str:
    if language in SUPPORTED_LANGUAGES:
        return language
    return DEFAULT_LANGUAGE


def resolve_language(request: Request) -> tuple[str, bool]:
    query_language = request.query_params.get("lang")
    if query_language is not None:
        return normalize_language(query_language), True
    return normalize_language(request.cookies.get(LANGUAGE_COOKIE)), False


def language_url(request: Request, language: str) -> str:
    language = normalize_language(language)
    params = [
        (key, value)
        for key, value in parse_qsl(request.url.query, keep_blank_values=True)
        if key != "lang"
    ]
    params.append(("lang", language))
    query = urlencode(params)
    return f"{request.url.path}?{query}"


def localized_url(path: str, language: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}lang={normalize_language(language)}"


def status_label_key(label: str) -> str:
    return STATUS_LABEL_KEYS.get(label, label.lower().replace(" ", "_"))
