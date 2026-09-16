"""Shared, packaged language catalogs for the installer and web application."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import TypedDict


SUPPORTED_UI_LANGUAGES = ("it", "en", "fr", "es", "pt", "el", "he", "ar", "tr")
DEFAULT_UI_LANGUAGE = "it"
RTL_UI_LANGUAGES = ("he", "ar")
LANGUAGE_LABELS = (
    "Italiano",
    "English",
    "Français / French",
    "Español / Spanish",
    "Português / Portuguese",
    "Ελληνικά / Greek",
    "עברית / Hebrew",
    "العربية / Arabic",
    "Türkçe / Turkish",
)
YES_WORDS = {
    "it": ("s", "si", "sì", "y", "yes"),
    "en": ("y", "yes"),
    "fr": ("o", "oui", "y", "yes"),
    "es": ("s", "sí", "si", "y", "yes"),
    "pt": ("s", "sim", "y", "yes"),
    "el": ("ν", "ναι", "y", "yes"),
    "he": ("כ", "כן", "y", "yes"),
    "ar": ("ن", "نعم", "y", "yes"),
    "tr": ("e", "evet", "y", "yes"),
}
NO_WORDS = {
    "it": ("n", "no"),
    "en": ("n", "no"),
    "fr": ("n", "non", "no"),
    "es": ("n", "no"),
    "pt": ("n", "não", "nao", "no"),
    "el": ("ο", "όχι", "οχι", "n", "no"),
    "he": ("ל", "לא", "n", "no"),
    "ar": ("ل", "لا", "n", "no"),
    "tr": ("h", "hayır", "hayir", "n", "no"),
}


class LocaleCatalog(TypedDict):
    installer: dict[str, str]
    frontend: dict[str, str | list[str]]
    citations: dict[str, str]


def _string_map(value: object, section: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value or any(
        not isinstance(key, str) or not isinstance(text, str) or not text.strip()
        for key, text in value.items()
    ):
        raise ValueError(f"Invalid {section} locale catalog")
    return dict(value)


@cache
def load_catalog(language: str) -> LocaleCatalog:
    if language not in SUPPORTED_UI_LANGUAGES:
        raise ValueError("Unsupported UI language: " + str(language))
    raw = json.loads(
        files("azure_bing_assistant").joinpath("locales", f"{language}.json").read_text(
            encoding="utf-8",
        )
    )
    if not isinstance(raw, dict) or set(raw) != {"installer", "frontend", "citations"}:
        raise ValueError(f"Invalid locale catalog: {language}")
    frontend = raw["frontend"]
    if not isinstance(frontend, dict) or not frontend:
        raise ValueError(f"Invalid frontend locale catalog: {language}")
    strings: dict[str, str | list[str]] = {}
    for key, value in frontend.items():
        if not isinstance(key, str):
            raise ValueError(f"Invalid frontend locale key: {language}")
        if isinstance(value, str) and value.strip():
            strings[key] = value
        elif isinstance(value, list) and value and all(
            isinstance(item, str) and item.strip() for item in value
        ):
            strings[key] = list(value)
        else:
            raise ValueError(f"Invalid frontend locale value: {language}/{key}")
    catalog: LocaleCatalog = {
        "installer": _string_map(raw["installer"], "installer"),
        "frontend": strings,
        "citations": _string_map(raw["citations"], "citations"),
    }
    if language != "en":
        reference = load_catalog("en")
        for section in ("installer", "frontend", "citations"):
            if catalog[section].keys() != reference[section].keys():
                raise ValueError(f"Incomplete locale catalog: {language}/{section}")
    return catalog


def frontend_strings(language: str) -> dict[str, str | list[str]]:
    return load_catalog(language)["frontend"]
