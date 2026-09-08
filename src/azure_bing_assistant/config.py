"""Validated installer configuration."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from ipaddress import ip_address
from typing import Mapping
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Raised when installer input is unsafe or incomplete."""


class KnowledgeMode(str, Enum):
    OFF = "off"
    SEARCH_BLOB = "searchBlob"


SUPPORTED_UI_LANGUAGES = ("it", "en")
DEFAULT_UI_LANGUAGE = "it"


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{2,23}$")
_LOCATION = re.compile(r"^[a-z][a-z0-9]{2,31}$")
_AZURE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RESOURCE_GROUP = re.compile(r"^[A-Za-z0-9._()\-]{1,90}$")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
def _validate_identifier(name: str, value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ConfigurationError(
            f"{name} must be 3-24 lowercase letters, digits, or hyphens and start with a letter"
        )
    return value


def _environment_boolean(source: Mapping[str, str], name: str, default: bool) -> bool:
    value = source.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ConfigurationError(f"{name} must be true or false")


def _validate_ui_text(name: str, value: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or _CONTROL_CHARACTER.search(normalized):
        raise ConfigurationError(
            f"{name} must be 1-{maximum} characters without control characters"
        )
    return normalized


def validate_ui_language(value: str) -> str:
    if value not in SUPPORTED_UI_LANGUAGES:
        raise ConfigurationError("UI_LANGUAGE must be 'it' or 'en'")
    return value


def parse_suggestions(value: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("UI_SUGGESTED_QUESTIONS must be a JSON array") from exc
    if not isinstance(parsed, list) or len(parsed) > 5:
        raise ConfigurationError("UI_SUGGESTED_QUESTIONS must contain at most 5 strings")
    if not all(isinstance(item, str) for item in parsed):
        raise ConfigurationError("UI_SUGGESTED_QUESTIONS must contain only strings")
    return tuple(
        _validate_ui_text("suggestion", item, 160)
        for item in parsed
    )


def validate_websites(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        candidate = value if "://" in value else f"https://{value}"
        parsed = urlsplit(candidate)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ConfigurationError("website port is invalid") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or port
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError(
                "websites must be public HTTPS domains or paths without credentials, ports, query, or fragment"
            )
        host = parsed.hostname.lower().rstrip(".")
        try:
            ip_address(host)
        except ValueError:
            pass
        else:
            raise ConfigurationError("website IP addresses are not accepted")
        labels = host.split(".")
        if len(labels) < 2 or any(not _DNS_LABEL.fullmatch(label) for label in labels):
            raise ConfigurationError("website must contain a valid public DNS name")
        path = parsed.path.rstrip("/")
        normalized_value = f"https://{host}{path}"
        if normalized_value not in normalized:
            normalized.append(normalized_value)
    if not normalized:
        raise ConfigurationError("at least one preferred website/domain is required")
    return tuple(normalized)


@dataclass(frozen=True)
class InstallerConfig:
    environment_name: str
    location: str
    knowledge_mode: KnowledgeMode | None
    subscription_id: str | None = None
    resource_group_name: str | None = None
    create_resource_group: bool = True
    model_name: str | None = None
    model_version: str | None = None
    model_format: str | None = None
    model_sku: str | None = None
    model_capacity: int = 10
    model_deployment_name: str | None = None
    chatbot_name: str | None = None
    ui_language: str | None = None
    ui_product_name: str | None = None
    ui_organization_name: str | None = None
    ui_assistant_name: str | None = None
    ui_welcome_title: str | None = None
    ui_welcome_subtitle: str | None = None
    ui_disclaimer: str | None = None
    ui_suggestions: tuple[str, ...] | None = None
    websites: tuple[str, ...] = ()
    strict_websites: bool = False
    bing_terms_accepted: bool = False
    foundry_user_role_definition_id: str | None = None
    storage_blob_data_reader_role_definition_id: str | None = None
    search_index_data_reader_role_definition_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier("environment_name", self.environment_name)
        if not _LOCATION.fullmatch(self.location):
            raise ConfigurationError("location must be a lowercase Azure region identifier")
        if self.knowledge_mode is not None and not isinstance(
            self.knowledge_mode, KnowledgeMode
        ):
            raise ConfigurationError("knowledge_mode must be 'off' or 'searchBlob'")
        if self.subscription_id is not None and (
            not self.subscription_id.strip()
            or any(c.isspace() for c in self.subscription_id)
        ):
            raise ConfigurationError(
                "subscription_id must not be blank or contain whitespace"
            )
        for field_name in (
            "foundry_user_role_definition_id",
            "storage_blob_data_reader_role_definition_id",
            "search_index_data_reader_role_definition_id",
        ):
            value = getattr(self, field_name)
            if value is not None and not value.startswith("/subscriptions/"):
                raise ConfigurationError(f"{field_name} must be a full Azure resource ID")
        if self.resource_group_name and not _RESOURCE_GROUP.fullmatch(self.resource_group_name):
            raise ConfigurationError("resource_group_name is not valid for Azure")
        for field_name in (
            "model_name",
            "model_version",
            "model_format",
            "model_sku",
            "model_deployment_name",
        ):
            value = getattr(self, field_name)
            if value is not None and not _AZURE_NAME.fullmatch(value):
                raise ConfigurationError(f"{field_name} contains unsupported characters")
        if self.chatbot_name is not None:
            _validate_identifier("chatbot_name", self.chatbot_name)
        if self.ui_language is not None:
            validate_ui_language(self.ui_language)
        ui_limits = {
            "ui_product_name": 80,
            "ui_organization_name": 80,
            "ui_welcome_title": 120,
            "ui_welcome_subtitle": 240,
            "ui_disclaimer": 320,
        }
        for field_name, maximum in ui_limits.items():
            value = getattr(self, field_name)
            if value is None:
                continue
            object.__setattr__(
                self,
                field_name,
                _validate_ui_text(field_name, value, maximum),
            )
        if self.ui_assistant_name is not None:
            object.__setattr__(
                self,
                "ui_assistant_name",
                _validate_ui_text("ui_assistant_name", self.ui_assistant_name, 80),
            )
        if self.ui_suggestions is not None:
            if len(self.ui_suggestions) > 5:
                raise ConfigurationError("ui_suggestions must contain at most 5 items")
            if not all(isinstance(item, str) for item in self.ui_suggestions):
                raise ConfigurationError("ui_suggestions must contain only strings")
            object.__setattr__(
                self,
                "ui_suggestions",
                tuple(
                    _validate_ui_text("ui_suggestions item", suggestion, 160)
                    for suggestion in self.ui_suggestions
                ),
            )
        if self.model_capacity < 1:
            raise ConfigurationError("model_capacity must be positive")
        if self.websites and validate_websites(self.websites) != self.websites:
            raise ConfigurationError("websites must already be normalized")
        if self.strict_websites:
            raise ConfigurationError(
                "strict website enforcement is not provisioned by this installer; "
                "use a verified Bing Custom Search configuration or an Azure AI Search "
                "Web Knowledge Source with allowedDomains"
            )

    @classmethod
    def from_values(
        cls,
        mode: str | None,
        environment_name: str | None = None,
        location: str | None = None,
        environ: Mapping[str, str] | None = None,
        ui_language: str | None = None,
    ) -> "InstallerConfig":
        source = os.environ if environ is None else environ
        configured_mode = mode if mode is not None else source.get("KNOWLEDGE_MODE")
        try:
            knowledge_mode = (
                KnowledgeMode(configured_mode) if configured_mode is not None else None
            )
        except ValueError as exc:
            raise ConfigurationError("knowledge_mode must be 'off' or 'searchBlob'") from exc
        return cls(
            environment_name=(
                source.get("AZURE_ENV_NAME", "chatbot-dev")
                if environment_name is None
                else environment_name
            ),
            location=source.get("AZURE_LOCATION", "westeurope") if location is None else location,
            knowledge_mode=knowledge_mode,
            subscription_id=source.get("AZURE_SUBSCRIPTION_ID"),
            resource_group_name=source.get("AZURE_RESOURCE_GROUP"),
            create_resource_group=_environment_boolean(
                source, "CREATE_RESOURCE_GROUP", True
            ),
            model_name=source.get("MODEL_NAME"),
            model_version=source.get("MODEL_VERSION"),
            model_format=source.get("MODEL_FORMAT"),
            model_sku=source.get("MODEL_SKU"),
            model_capacity=int(source.get("MODEL_CAPACITY", "10")),
            model_deployment_name=source.get("MODEL_DEPLOYMENT_NAME"),
            chatbot_name=source.get("CHATBOT_NAME"),
            ui_language=(
                ui_language if ui_language is not None else source.get("UI_LANGUAGE")
            ),
            ui_product_name=source.get("UI_PRODUCT_NAME"),
            ui_organization_name=source.get("UI_ORGANIZATION_NAME"),
            ui_assistant_name=source.get("UI_ASSISTANT_NAME"),
            ui_welcome_title=source.get("UI_WELCOME_TITLE"),
            ui_welcome_subtitle=source.get("UI_WELCOME_SUBTITLE"),
            ui_disclaimer=source.get("UI_DISCLAIMER"),
            ui_suggestions=(
                parse_suggestions(source["UI_SUGGESTED_QUESTIONS"])
                if "UI_SUGGESTED_QUESTIONS" in source
                else None
            ),
            websites=(
                validate_websites(source["WEB_GROUNDING_SITES"].split(","))
                if source.get("WEB_GROUNDING_SITES")
                else ()
            ),
            bing_terms_accepted=_environment_boolean(
                source, "BING_TERMS_ACCEPTED", False
            ),
            foundry_user_role_definition_id=source.get("FOUNDRY_USER_ROLE_DEFINITION_ID"),
            storage_blob_data_reader_role_definition_id=source.get(
                "STORAGE_BLOB_DATA_READER_ROLE_DEFINITION_ID"
            ),
            search_index_data_reader_role_definition_id=source.get(
                "SEARCH_INDEX_DATA_READER_ROLE_DEFINITION_ID"
            ),
        )

    def public_parameters(self) -> dict[str, str]:
        if self.knowledge_mode is None:
            raise ConfigurationError("knowledge_mode is required")
        return {
            "environmentName": self.environment_name,
            "location": self.location,
            "knowledgeMode": self.knowledge_mode.value,
            "subscriptionConfigured": str(bool(self.subscription_id)).lower(),
            "resourceGroup": self.resource_group_name or f"rg-{self.environment_name}",
            "createResourceGroup": str(self.create_resource_group).lower(),
            "model": self.model_name or "<configure>",
            "modelVersion": self.model_version or "<configure>",
            "modelFormat": self.model_format or "<configure>",
            "modelSku": self.model_sku or "<configure>",
            "modelDeployment": self.model_deployment_name or "<configure>",
            "chatbotName": self.chatbot_name or self.environment_name,
            "uiLanguage": self.ui_language or DEFAULT_UI_LANGUAGE,
            "uiProductName": self.ui_product_name or "<localized default>",
            "uiOrganizationName": self.ui_organization_name or "<localized default>",
            "uiAssistantName": self.ui_assistant_name or "<localized default>",
            "uiWelcomeTitle": self.ui_welcome_title or "<localized default>",
            "uiWelcomeSubtitle": self.ui_welcome_subtitle or "<localized default>",
            "uiDisclaimer": self.ui_disclaimer or "<localized default>",
            "uiSuggestedQuestions": (
                json.dumps(
                    self.ui_suggestions,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                if self.ui_suggestions is not None
                else "<localized default>"
            ),
            "webGrounding": "bing",
            "websites": ",".join(self.websites) if self.websites else "<configure>",
            "websiteEnforcement": "advisory",
        }

    def require_complete_install(self) -> None:
        if self.knowledge_mode is None:
            raise ConfigurationError("knowledge_mode is required")
        required = {
            "subscription_id": self.subscription_id,
            "resource_group_name": self.resource_group_name,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_format": self.model_format,
            "model_sku": self.model_sku,
            "model_deployment_name": self.model_deployment_name,
            "chatbot_name": self.chatbot_name,
            "websites": self.websites,
            "foundry_user_role_definition_id": self.foundry_user_role_definition_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ConfigurationError(
                "non-interactive install requires: " + ", ".join(sorted(missing))
            )
        if not self.bing_terms_accepted:
            raise ConfigurationError("Bing terms and data-flow acknowledgement is required")
        if self.knowledge_mode is KnowledgeMode.SEARCH_BLOB:
            if not self.storage_blob_data_reader_role_definition_id:
                raise ConfigurationError(
                    "searchBlob requires storage_blob_data_reader_role_definition_id"
                )
            if not self.search_index_data_reader_role_definition_id:
                raise ConfigurationError(
                    "searchBlob requires search_index_data_reader_role_definition_id"
                )

    def azd_environment_values(self) -> dict[str, str]:
        if self.knowledge_mode is None:
            raise ConfigurationError("knowledge_mode is required")
        values = {
            "AZURE_LOCATION": self.location,
            "KNOWLEDGE_MODE": self.knowledge_mode.value,
            "CREATE_RESOURCE_GROUP": str(self.create_resource_group).lower(),
            "AZURE_RESOURCE_GROUP": self.resource_group_name or f"rg-{self.environment_name}",
            "MODEL_NAME": self.model_name or "",
            "MODEL_VERSION": self.model_version or "",
            "MODEL_FORMAT": self.model_format or "",
            "MODEL_SKU": self.model_sku or "",
            "MODEL_CAPACITY": str(self.model_capacity),
            "MODEL_DEPLOYMENT_NAME": self.model_deployment_name or "",
            "CHATBOT_NAME": self.chatbot_name or self.environment_name,
            "UI_LANGUAGE": self.ui_language or DEFAULT_UI_LANGUAGE,
            "WEB_GROUNDING_SITES": ",".join(self.websites),
            "BING_TERMS_ACCEPTED": str(self.bing_terms_accepted).lower(),
            "COGNITIVE_USER_ROLE_DEFINITION_ID": (
                self.foundry_user_role_definition_id or ""
            ),
            "STORAGE_BLOB_DATA_READER_ROLE_DEFINITION_ID": (
                self.storage_blob_data_reader_role_definition_id or ""
            ),
            "SEARCH_INDEX_DATA_READER_ROLE_DEFINITION_ID": (
                self.search_index_data_reader_role_definition_id or ""
            ),
        }
        optional = {
            "AZURE_SUBSCRIPTION_ID": self.subscription_id,
            "UI_PRODUCT_NAME": self.ui_product_name,
            "UI_ORGANIZATION_NAME": self.ui_organization_name,
            "UI_ASSISTANT_NAME": self.ui_assistant_name,
            "UI_WELCOME_TITLE": self.ui_welcome_title,
            "UI_WELCOME_SUBTITLE": self.ui_welcome_subtitle,
            "UI_DISCLAIMER": self.ui_disclaimer,
        }
        values.update({name: value for name, value in optional.items() if value})
        if self.ui_suggestions is not None:
            values["UI_SUGGESTED_QUESTIONS"] = json.dumps(
                self.ui_suggestions,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        return values
