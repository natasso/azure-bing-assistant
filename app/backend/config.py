"""Runtime configuration for the web application."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

from azure_bing_assistant.config import WebSearchProvider, parse_web_search_provider, validate_websites
from azure_bing_assistant.agent import SearchDocumentSource
from azure_bing_assistant.bing_binding import BingCustomSearchBinding
from azure_bing_assistant.localization import (
    DEFAULT_UI_LANGUAGE,
    SUPPORTED_UI_LANGUAGES,
    frontend_strings,
)


_UI_DEFAULT_KEYS = {
    "product_name": "productName",
    "organization_name": "organizationName",
    "assistant_name": "assistantName",
    "welcome_title": "welcomeTitle",
    "welcome_subtitle": "welcomeSubtitle",
    "disclaimer": "disclaimer",
    "suggested_questions": "suggestions",
}
LOCALIZED_UI_DEFAULTS = {
    language: {
        name: tuple(strings[key]) if name == "suggested_questions" else strings[key]
        for name, key in _UI_DEFAULT_KEYS.items()
    }
    for language in SUPPORTED_UI_LANGUAGES
    for strings in (frontend_strings(language),)
}


_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _ui_text(name: str, value: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or _CONTROL_CHARACTER.search(normalized):
        raise ValueError(f"{name} must be 1-{maximum} characters without control characters")
    return normalized


def _suggestions(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("UI_SUGGESTED_QUESTIONS must be a JSON array") from exc
    if not isinstance(parsed, list) or len(parsed) > 5:
        raise ValueError("UI_SUGGESTED_QUESTIONS must contain at most 5 strings")
    if not all(isinstance(item, str) for item in parsed):
        raise ValueError("UI_SUGGESTED_QUESTIONS must contain only strings")
    return [_ui_text("UI_SUGGESTED_QUESTIONS item", item, 160) for item in parsed]


@dataclass(frozen=True)
class UIConfig:
    """UI configuration for the chatbot."""
    language: str = DEFAULT_UI_LANGUAGE
    product_name: str | None = None
    organization_name: str | None = None
    assistant_name: str | None = None
    welcome_title: str | None = None
    welcome_subtitle: str | None = None
    disclaimer: str | None = None
    suggested_questions: list[str] | None = None

    def __post_init__(self) -> None:
        if self.language not in SUPPORTED_UI_LANGUAGES:
            raise ValueError(f"UI_LANGUAGE must be one of: {', '.join(SUPPORTED_UI_LANGUAGES)}")
        defaults = LOCALIZED_UI_DEFAULTS[self.language]
        limits = {
            "product_name": 80,
            "organization_name": 80,
            "assistant_name": 80,
            "welcome_title": 120,
            "welcome_subtitle": 240,
            "disclaimer": 320,
        }
        for name, maximum in limits.items():
            value = getattr(self, name)
            if value is None:
                value = defaults[name]
            object.__setattr__(
                self,
                name,
                _ui_text(name, str(value), maximum),
            )
        suggestions = self.suggested_questions
        if suggestions is None:
            suggestions = list(defaults["suggested_questions"])
        if len(suggestions) > 5:
            raise ValueError("suggested_questions must contain at most 5 items")
        if not all(isinstance(item, str) for item in suggestions):
            raise ValueError("suggested_questions must contain only strings")
        object.__setattr__(
            self,
            "suggested_questions",
            [
                _ui_text("suggested_questions item", item, 160)
                for item in suggestions
            ],
        )


@dataclass(frozen=True)
class AppSettings:
    environment: str = "development"
    knowledge_mode: str = "off"
    ui_config: UIConfig | None = None
    foundry_project_endpoint: str | None = None
    chatbot_name: str | None = None
    agent_timeout_seconds: float = 90.0
    allowed_domains: tuple[str, ...] = ()
    document_source: SearchDocumentSource | None = None
    bing_custom_search: BingCustomSearchBinding | None = None

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if self.knowledge_mode not in {"off", "searchBlob"}:
            raise ValueError("KNOWLEDGE_MODE must be off or searchBlob")
        if not 5 <= self.agent_timeout_seconds <= 300:
            raise ValueError("AGENT_TIMEOUT_SECONDS must be between 5 and 300")
        if self.bing_custom_search is not None and not isinstance(
            self.bing_custom_search, BingCustomSearchBinding,
        ):
            raise ValueError("bing_custom_search must be a BingCustomSearchBinding")
        if bool(self.foundry_project_endpoint) != bool(self.chatbot_name):
            raise ValueError(
                "FOUNDRY_PROJECT_ENDPOINT and CHATBOT_NAME must be configured together"
            )
        if self.foundry_project_endpoint:
            parsed = urlsplit(self.foundry_project_endpoint)
            try:
                port = parsed.port
            except ValueError:
                port = -1
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or not parsed.hostname.lower().endswith(".services.ai.azure.com")
                or parsed.username
                or parsed.password
                or port
                or parsed.query
                or parsed.fragment
                or not re.fullmatch(r"/api/projects/[A-Za-z0-9][A-Za-z0-9._-]*/?", parsed.path)
            ):
                raise ValueError("FOUNDRY_PROJECT_ENDPOINT must be a safe HTTPS endpoint")
        if self.chatbot_name and not re.fullmatch(
            r"[a-z][a-z0-9-]{2,63}", self.chatbot_name
        ):
            raise ValueError("CHATBOT_NAME must be a lowercase Azure identifier")
        if self.ui_config is None:
            object.__setattr__(self, "ui_config", UIConfig())
        if self.allowed_domains or self.foundry_project_endpoint:
            object.__setattr__(self, "allowed_domains", validate_websites(self.allowed_domains))

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "AppSettings":
        source = os.environ if environ is None else environ
        ui_config = UIConfig(
            language=source.get("UI_LANGUAGE", DEFAULT_UI_LANGUAGE),
            product_name=source.get("UI_PRODUCT_NAME"),
            organization_name=source.get("UI_ORGANIZATION_NAME"),
            assistant_name=source.get("UI_ASSISTANT_NAME"),
            welcome_title=source.get("UI_WELCOME_TITLE"),
            welcome_subtitle=source.get("UI_WELCOME_SUBTITLE"),
            disclaimer=source.get("UI_DISCLAIMER"),
            suggested_questions=(
                _suggestions(source["UI_SUGGESTED_QUESTIONS"])
                if "UI_SUGGESTED_QUESTIONS" in source
                else None
            ),
        )
        try:
            timeout = float(source.get("AGENT_TIMEOUT_SECONDS", "90"))
        except ValueError as exc:
            raise ValueError("AGENT_TIMEOUT_SECONDS must be a number") from exc
        bing_connection = source.get("BING_CUSTOM_SEARCH_CONNECTION_ID", "")
        bing_instance = source.get("BING_CUSTOM_SEARCH_INSTANCE_NAME", "")
        if bool(bing_connection) != bool(bing_instance):
            raise ValueError(
                "BING_CUSTOM_SEARCH_CONNECTION_ID and BING_CUSTOM_SEARCH_INSTANCE_NAME "
                "must be configured together"
            )
        bing_binding = (
            BingCustomSearchBinding(bing_connection, bing_instance) if bing_connection else None
        )
        if "WEB_SEARCH_PROVIDER" in source:
            provider = parse_web_search_provider(source["WEB_SEARCH_PROVIDER"])
            if (provider == WebSearchProvider.BING_CUSTOM_SEARCH) != (bing_binding is not None):
                raise ValueError("WEB_SEARCH_PROVIDER does not match the Bing Custom Search binding")
        return cls(
            environment=source.get("APP_ENV", "development"),
            knowledge_mode=source.get("KNOWLEDGE_MODE", "off"),
            foundry_project_endpoint=source.get("FOUNDRY_PROJECT_ENDPOINT"),
            chatbot_name=source.get("CHATBOT_NAME"),
            bing_custom_search=bing_binding,
            agent_timeout_seconds=timeout,
            allowed_domains=(
                validate_websites(source["WEB_GROUNDING_SITES"].split(","))
                if "WEB_GROUNDING_SITES" in source else ()
            ),
            document_source=(
                SearchDocumentSource(
                    source.get("STORAGE_ACCOUNT_NAME", ""),
                    source.get("STORAGE_CONTAINER_NAME", ""),
                )
                if source.get("KNOWLEDGE_MODE") == "searchBlob"
                and (source.get("STORAGE_ACCOUNT_NAME") or source.get("STORAGE_CONTAINER_NAME"))
                else None
            ),
            ui_config=ui_config,
        )
