"""Runtime configuration for the web application."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit


DEFAULT_UI_LANGUAGE = "it"
LOCALIZED_UI_DEFAULTS = {
    "it": {
        "product_name": "Azure Bing Assistant",
        "organization_name": "Organizzazione",
        "assistant_name": "Assistente",
        "welcome_title": "Come posso aiutarti?",
        "welcome_subtitle": (
            "Fai una domanda sulle informazioni aggiornate disponibili sul web."
        ),
        "disclaimer": (
            "Questo assistente usa l'AI. Verifica le informazioni importanti "
            "e non condividere dati sensibili."
        ),
        "suggested_questions": (
            "Che cosa puoi aiutarmi a trovare?",
            "Riassumi un argomento attuale",
            "Spiega un concetto in modo semplice",
            "Confronta due opzioni",
            "Dove posso trovare maggiori informazioni?",
        ),
    },
    "en": {
        "product_name": "Azure Bing Assistant",
        "organization_name": "Organization",
        "assistant_name": "Assistant",
        "welcome_title": "How can I help?",
        "welcome_subtitle": "Ask a question about current information from the web.",
        "disclaimer": (
            "This assistant uses AI. Verify important information and do not "
            "share sensitive data."
        ),
        "suggested_questions": (
            "What can you help me find?",
            "Summarize a current topic",
            "Explain a concept in simple terms",
            "Compare two options",
            "Where can I learn more?",
        ),
    },
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
        if self.language not in LOCALIZED_UI_DEFAULTS:
            raise ValueError("UI_LANGUAGE must be 'it' or 'en'")
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

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if self.knowledge_mode not in {"off", "searchBlob"}:
            raise ValueError("KNOWLEDGE_MODE must be off or searchBlob")
        if not 5 <= self.agent_timeout_seconds <= 300:
            raise ValueError("AGENT_TIMEOUT_SECONDS must be between 5 and 300")
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
        return cls(
            environment=source.get("APP_ENV", "development"),
            knowledge_mode=source.get("KNOWLEDGE_MODE", "off"),
            foundry_project_endpoint=source.get("FOUNDRY_PROJECT_ENDPOINT"),
            chatbot_name=source.get("CHATBOT_NAME"),
            agent_timeout_seconds=timeout,
            ui_config=ui_config,
        )
