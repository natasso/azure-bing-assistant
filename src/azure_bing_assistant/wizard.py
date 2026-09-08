"""Interactive discovery over live Azure CLI results."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from .azure_cli import AzureCliResolutionError, azure_cli_invocation
from .config import (
    ConfigurationError,
    InstallerConfig,
    KnowledgeMode,
    validate_ui_language,
    validate_websites,
)


class DiscoveryError(RuntimeError):
    """Raised when Azure cannot provide a required choice."""


class CapabilityError(ConfigurationError):
    """Raised when requested enforcement is unavailable."""


@dataclass(frozen=True)
class SubscriptionChoice:
    name: str
    subscription_id: str
    tenant_id: str


@dataclass(frozen=True)
class RegionChoice:
    name: str
    display_name: str


@dataclass(frozen=True)
class ModelChoice:
    name: str
    version: str
    model_format: str
    sku: str
    minimum_capacity: int | None = None
    maximum_capacity: int | None = None
    default_capacity: int | None = None

    @property
    def label(self) -> str:
        return f"{self.name} / {self.version} / {self.model_format} / {self.sku}"


class Discovery(Protocol):
    def subscriptions(self) -> list[SubscriptionChoice]: ...

    def resource_groups(self, subscription_id: str) -> list[str]: ...

    def regions(self, subscription_id: str) -> list[RegionChoice]: ...

    def models(self, subscription_id: str, location: str) -> list[ModelChoice]: ...

    def role_definition(self, subscription_id: str, accepted_names: Sequence[str]) -> str: ...


class AzureCliDiscovery:
    """Read-only Azure discovery. Every call uses argv and disables the shell."""

    def _json(self, argv: Sequence[str]) -> Any:
        try:
            command, environment = azure_cli_invocation(argv)
            completed = subprocess.run(
                command,
                env=environment,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (AzureCliResolutionError, OSError, subprocess.TimeoutExpired) as exc:
            detail = (
                str(exc)
                if isinstance(exc, AzureCliResolutionError)
                else type(exc).__name__
            )
            raise DiscoveryError(f"Azure discovery failed: {detail}") from exc
        if completed.returncode:
            raise DiscoveryError("Azure CLI could not return the requested choices")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise DiscoveryError("Azure CLI returned invalid JSON") from exc

    def subscriptions(self) -> list[SubscriptionChoice]:
        rows = self._json(["az", "account", "list", "--all", "--output", "json"])
        choices = [
            SubscriptionChoice(
                name=str(row["name"]),
                subscription_id=str(row["id"]),
                tenant_id=str(row["tenantId"]),
            )
            for row in rows
            if row.get("state") == "Enabled"
        ]
        if not choices:
            raise DiscoveryError("No enabled subscriptions are visible; run az login first")
        return choices

    def resource_groups(self, subscription_id: str) -> list[str]:
        rows = self._json(
            [
                "az",
                "group",
                "list",
                "--subscription",
                subscription_id,
                "--output",
                "json",
            ]
        )
        return sorted(str(row["name"]) for row in rows)

    def regions(self, subscription_id: str) -> list[RegionChoice]:
        rows = self._json(
            [
                "az",
                "account",
                "list-locations",
                "--subscription",
                subscription_id,
                "--output",
                "json",
            ]
        )
        choices = [
            RegionChoice(str(row["name"]), str(row.get("displayName") or row["name"]))
            for row in rows
            if row.get("name")
        ]
        if not choices:
            raise DiscoveryError("Azure returned no available regions")
        return sorted(choices, key=lambda item: item.display_name.casefold())

    def models(self, subscription_id: str, location: str) -> list[ModelChoice]:
        rows = self._json(
            [
                "az",
                "cognitiveservices",
                "model",
                "list",
                "--location",
                location,
                "--subscription",
                subscription_id,
                "--output",
                "json",
            ]
        )
        choices: list[ModelChoice] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            account_kind = row.get("kind")
            if account_kind is not None and account_kind != "AIServices":
                continue
            nested_model = row.get("model")
            if nested_model is not None and not isinstance(nested_model, dict):
                continue
            model = nested_model or row
            name = model.get("name")
            version = model.get("version")
            model_format = model.get("format") or row.get("kind")
            skus = model.get("skus") if "skus" in model else row.get("skus")
            if not isinstance(skus, list):
                continue
            for sku in skus:
                if not isinstance(sku, dict):
                    continue
                sku_name = sku.get("name")
                if name and version and model_format and sku_name:
                    capacity = sku.get("capacity") or {}
                    if not isinstance(capacity, dict):
                        continue
                    choices.append(
                        ModelChoice(
                            name,
                            version,
                            model_format,
                            sku_name,
                            (
                                int(capacity["minimum"])
                                if capacity.get("minimum") is not None
                                else None
                            ),
                            (
                                int(capacity["maximum"])
                                if capacity.get("maximum") is not None
                                else None
                            ),
                            (
                                int(capacity["default"])
                                if capacity.get("default") is not None
                                else None
                            ),
                        )
                    )
        if not choices:
            raise DiscoveryError(
                "Azure returned no deployable model/SKU combinations for this region"
            )
        return sorted(choices, key=lambda item: item.label.casefold())

    def role_definition(
        self, subscription_id: str, accepted_names: Sequence[str]
    ) -> str:
        rows = self._json(
            [
                "az",
                "role",
                "definition",
                "list",
                "--subscription",
                subscription_id,
                "--output",
                "json",
            ]
        )
        for preferred_name in accepted_names:
            for row in rows:
                if row.get("roleName") == preferred_name and row.get("id"):
                    return str(row["id"])
        raise DiscoveryError(
            "Azure did not return a required built-in role definition: "
            + " or ".join(accepted_names)
        )


class ConsolePrompts:
    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self.input = input_fn
        self.output = output_fn

    def select(
        self,
        question: str,
        labels: Sequence[str],
        default_index: int | None = None,
    ) -> int:
        if not labels:
            raise DiscoveryError(f"No choices are available for {question}")
        if default_index is not None and not 0 <= default_index < len(labels):
            raise ConfigurationError("Default selection is outside the available choices")
        self.output(question)
        for index, label in enumerate(labels, start=1):
            self.output(f"  {index}. {label}")
        prompt = (
            f"Select a number [{default_index + 1}]: "
            if default_index is not None
            else "Select a number: "
        )
        raw = self.input(prompt).strip()
        if not raw and default_index is not None:
            return default_index
        if not raw.isdigit() or not 1 <= int(raw) <= len(labels):
            raise ConfigurationError("Selection is outside the available choices")
        return int(raw) - 1

    def text(self, question: str) -> str:
        value = self.input(f"{question}: ").strip()
        if not value:
            raise ConfigurationError(f"{question} is required")
        return value

    def yes_no(self, question: str) -> bool:
        value = self.input(f"{question} [y/N]: ").strip().lower()
        if not value:
            return False
        if value not in {"y", "yes", "n", "no"}:
            raise ConfigurationError("Answer yes or no")
        return value in {"y", "yes"}


_RESOURCE_GROUP = re.compile(r"^[A-Za-z0-9._()\-]{1,90}$")


def run_wizard(
    discovery: Discovery,
    prompts: ConsolePrompts,
    ui_language: str | None = None,
) -> InstallerConfig:
    language = (
        validate_ui_language(ui_language)
        if ui_language is not None
        else ("it", "en")[
            prompts.select(
                "Choose the application interface language",
                ("Italiano (default)", "English"),
                default_index=0,
            )
        ]
    )
    subscriptions = discovery.subscriptions()
    subscription = subscriptions[
        prompts.select(
            "Choose a signed-in tenant and subscription",
            [f"{item.name} (tenant {item.tenant_id})" for item in subscriptions],
        )
    ]

    groups = discovery.resource_groups(subscription.subscription_id)
    group_labels = ["Create a new resource group", *groups]
    group_index = prompts.select("Choose an existing or new resource group", group_labels)
    create_group = group_index == 0
    resource_group = prompts.text("New resource group name") if create_group else groups[group_index - 1]
    if not _RESOURCE_GROUP.fullmatch(resource_group):
        raise ConfigurationError("Resource group name is not valid for Azure")

    regions = discovery.regions(subscription.subscription_id)
    region = regions[
        prompts.select(
            "Choose an Azure region returned for this subscription",
            [f"{item.display_name} ({item.name})" for item in regions],
        )
    ]
    models = discovery.models(subscription.subscription_id, region.name)
    model = models[
        prompts.select(
            "Choose a model, version, format, and deployment SKU returned by Azure",
            [item.label for item in models],
        )
    ]
    capacity_detail = (
        f"{model.minimum_capacity}-{model.maximum_capacity}"
        if model.minimum_capacity is not None and model.maximum_capacity is not None
        else "positive integer; quota is validated by Azure at deployment"
    )
    capacity_text = prompts.text(f"Model capacity ({capacity_detail})")
    if not capacity_text.isdigit():
        raise ConfigurationError("Model capacity must be an integer")
    model_capacity = int(capacity_text)
    if (
        model.minimum_capacity is not None
        and model.maximum_capacity is not None
        and not model.minimum_capacity <= model_capacity <= model.maximum_capacity
    ):
        raise ConfigurationError("Model capacity is outside Azure's returned SKU range")

    chatbot_name = prompts.text("Chatbot name")
    environment_name = prompts.text("Deployment environment identifier")
    deployment_name = prompts.text("Model deployment name")

    prompts.output(
        "Chat uses Bing web grounding by default. Document search is optional and off "
        "unless you enable it."
    )
    use_search = prompts.yes_no(
        "Optional: add Blob storage and Azure AI Search for administrator-managed "
        "documents (adds Search and Storage costs)"
    )
    foundry_role_id = discovery.role_definition(
        subscription.subscription_id,
        ("Foundry User", "Azure AI User", "Cognitive Services OpenAI User"),
    )
    storage_role_id = None
    search_role_id = None
    if use_search:
        storage_role_id = discovery.role_definition(
            subscription.subscription_id,
            ("Storage Blob Data Reader",),
        )
        search_role_id = discovery.role_definition(
            subscription.subscription_id,
            ("Search Index Data Reader",),
        )
    websites = validate_websites(
        prompts.text("Preferred public websites/domains for Bing grounding").split(",")
    )
    prompts.output(
        "Standard Grounding with Bing Search searches the public web. These sites are advisory."
    )
    if prompts.yes_no("Require strict enforcement of only those websites"):
        raise CapabilityError(
            "Current Foundry supports strict sites through either a verified Bing Custom "
            "Search configuration or an Azure AI Search Web Knowledge Source with allowedDomains. "
            "The latter requires Search and a separate knowledge-base integration. "
            "This installer implements neither strict path and will not deploy advisory rules as strict"
        )
    if not prompts.yes_no(
        "Accept Bing grounding cost, terms, and data flow outside Azure compliance/Geo boundaries"
    ):
        raise CapabilityError("Bing grounding terms and data-flow acknowledgement is required")

    return InstallerConfig(
        environment_name=environment_name,
        location=region.name,
        knowledge_mode=KnowledgeMode.SEARCH_BLOB if use_search else KnowledgeMode.OFF,
        subscription_id=subscription.subscription_id,
        resource_group_name=resource_group,
        create_resource_group=create_group,
        model_name=model.name,
        model_version=model.version,
        model_format=model.model_format,
        model_sku=model.sku,
        model_capacity=model_capacity,
        model_deployment_name=deployment_name,
        chatbot_name=chatbot_name,
        ui_language=language,
        websites=websites,
        bing_terms_accepted=True,
        foundry_user_role_definition_id=foundry_role_id,
        storage_blob_data_reader_role_definition_id=storage_role_id,
        search_index_data_reader_role_definition_id=search_role_id,
    )
