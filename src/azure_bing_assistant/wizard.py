"""Interactive discovery over live Azure CLI results."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence
from urllib.parse import quote

from .azure_cli import AzureCliResolutionError, azure_cli_invocation
from .config import (
    ConfigurationError,
    InstallerConfig,
    KnowledgeMode,
    validate_azure_name,
    validate_identifier,
    validate_model_capacity,
    validate_resource_group,
    validate_ui_language,
    validate_websites,
)
from .installer_messages import InstallerMessageError, InstallerMessages
from .localization import (
    DEFAULT_UI_LANGUAGE, LANGUAGE_LABELS, NO_WORDS, SUPPORTED_UI_LANGUAGES, YES_WORDS,
)
from .wizard_draft import WizardDraft


class DiscoveryError(InstallerMessageError, RuntimeError):
    """Raised when Azure cannot provide a required choice."""


class CapabilityError(ConfigurationError):
    """Raised when requested enforcement is unavailable."""


class WizardCancelled(InstallerMessageError, RuntimeError):
    """Input ended before the operator completed the wizard."""


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

    def __post_init__(self) -> None:
        for field in ("minimum_capacity", "maximum_capacity", "default_capacity"):
            value = getattr(self, field)
            if value is not None and (type(value) is not int or value < 1):
                raise DiscoveryError(
                    "Azure returned invalid model capacity metadata: {field} "
                    "must be a positive integer", field=field,
                )
        if (
            self.minimum_capacity is not None
            and self.maximum_capacity is not None
            and self.minimum_capacity > self.maximum_capacity
        ):
            raise DiscoveryError(
                "Azure returned invalid model capacity metadata: minimum exceeds maximum"
            )
        if self.default_capacity is not None and (
            (self.minimum_capacity is not None and self.default_capacity < self.minimum_capacity)
            or (self.maximum_capacity is not None and self.default_capacity > self.maximum_capacity)
        ):
            raise DiscoveryError(
                "Azure returned invalid model capacity metadata: default is outside the SKU range"
            )

    @property
    def label(self) -> str:
        return f"{self.name} / {self.version} / {self.model_format} / {self.sku}"


class Discovery(Protocol):
    def subscriptions(self) -> list[SubscriptionChoice]: ...

    def resource_groups(self, subscription_id: str) -> list[str]: ...

    def regions(self, subscription_id: str) -> list[RegionChoice]: ...

    def models(self, subscription_id: str, location: str) -> list[ModelChoice]: ...

    def role_definition(self, subscription_id: str, accepted_names: Sequence[str]) -> str: ...


def _capacity_guidance(
    model: ModelChoice, displayed_capacity: int, prompts: ConsolePrompts,
) -> None:
    tr = prompts.messages
    if model.default_capacity is not None:
        prompts.output(tr("Azure SKU default: {capacity}.", capacity=model.default_capacity))
    prompts.output(tr(
        "Displayed capacity: {capacity}. Enter keeps it; examples never replace a valid "
        "saved value. An Azure default is not a recommendation for your workload.",
        capacity=displayed_capacity,
    ))
    if model.sku not in {"Standard", "GlobalStandard", "DataZoneStandard"}:
        prompts.output(tr(
            "This SKU does not use the Standard PAYG examples. Reserved/provisioned "
            "capacity has different capacity-based charges; Batch uses different quota "
            "semantics. Follow provider bounds and your organization's sizing and pricing "
            "guidance; no arbitrary test/production value is recommended."
        ))
        return
    prompts.output(tr(
        "Model capacity is the initial request throughput quota, not the number of "
        "users, guaranteed performance, or a cost budget. Azure validates quota at deployment."
    ))
    for units, message in (
        (10, "Test/POC example: 10 units for a few manual queries with low concurrency."),
        (100, "Production example: 100 units only as an illustrative starting point, not guaranteed capacity."),
    ):
        if (
            (model.minimum_capacity is None or units >= model.minimum_capacity)
            and (model.maximum_capacity is None or units <= model.maximum_capacity)
        ):
            prompts.output(tr(message))
        else:
            prompts.output(tr(
                "The {units}-unit example is not applicable to the returned SKU range; "
                "it is not a suggested input.", units=units,
            ))
    prompts.output(tr(
        "For Standard/GlobalStandard/DataZoneStandard, capacity allocates throughput quota, "
        "not maximum users, a monthly budget or a fixed PAYG bill. Production sizing needs "
        "peak requests/minute, context size, model TPM/RPM ratios and limited simultaneous work."
    ))
    prompts.output(tr(
        "Conditional example only: IF 1 unit = 1,000 TPM and 1 RPM, 10 requests/minute x "
        "6,000 estimated rate-limit tokens/request require max(60, 10) = 60 units; 25% "
        "margin gives 75, and 100 offers headroom. This is NOT a conversion for the "
        "selected model. Rate-limit estimates differ from billed tokens; verify actual "
        "model ratios, increments and available quota. Apply only within the returned SKU range."
    ))


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
            raise DiscoveryError("Azure discovery failed: {detail}", detail=detail) from exc
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
        try:
            payload = self._json(
                [
                    "az",
                    "rest",
                    "--method",
                    "get",
                    "--subscription",
                    subscription_id,
                    "--url",
                    f"/subscriptions/{quote(subscription_id, safe='')}/locations"
                    "?api-version=2022-12-01",
                    "--output",
                    "json",
                ]
            )
        except DiscoveryError as exc:
            raise DiscoveryError("Azure region discovery failed: {detail}", detail=exc) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise DiscoveryError(
                "Azure returned an invalid regions response: expected a value list"
            )
        rows = payload["value"]
        if any(not isinstance(row, dict) for row in rows):
            raise DiscoveryError(
                "Azure returned an invalid regions response: expected location objects"
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
                    capacity = sku.get("capacity")
                    if capacity is None:
                        capacity = {}
                    if not isinstance(capacity, dict):
                        raise DiscoveryError(
                            "Azure returned invalid model capacity metadata: expected an object"
                        )
                    choices.append(
                        ModelChoice(
                            name,
                            version,
                            model_format,
                            sku_name,
                            capacity.get("minimum"),
                            capacity.get("maximum"),
                            capacity.get("default"),
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
            "Azure did not return a required built-in role definition: {roles}",
            roles=" / ".join(accepted_names),
        )


class ConsolePrompts:
    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
        language: str = "en",
    ) -> None:
        self.input = input_fn
        self.output = output_fn
        self.messages = InstallerMessages(validate_ui_language(language))

    def read(self, question: str) -> str:
        try:
            return self.input(question).strip()
        except (EOFError, StopIteration, KeyboardInterrupt) as exc:
            raise WizardCancelled(
                self.messages("Input interrupted; installation cancelled.")
            ) from exc

    def select(
        self,
        question: str,
        labels: Sequence[str],
        default_index: int | None = None,
        bilingual: bool = False,
    ) -> int:
        if not labels:
            raise DiscoveryError(self.messages("No choices are available for {question}", question=question))
        if default_index is not None and (
            type(default_index) is not int or not 0 <= default_index < len(labels)
        ):
            raise ConfigurationError(self.messages("Default selection is outside the available choices"))
        self.output(question)
        for index, label in enumerate(labels, start=1):
            self.output(f"  {index}. {label}")
        label = "Seleziona un numero / Select a number" if bilingual else self.messages("Select a number")
        suffix = f" [{default_index + 1}]" if default_index is not None else ""
        hint = self.messages("Enter a number from 1 to {maximum}.", maximum=len(labels))
        if bilingual:
            hint = f"Inserisci un numero da 1 a {len(labels)} / Enter a number from 1 to {len(labels)}."
        if default_index is not None:
            hint += (
                f" Invio / Enter = {default_index + 1}."
                if bilingual else self.messages(" Enter = {default}.", default=default_index + 1)
            )
        else:
            hint += self.messages(" Enter has no default.")
        self.output(hint)
        while True:
            raw = self.read(f"{label}{suffix}: ")
            if not raw and default_index is not None:
                return default_index
            try:
                selection = int(raw) if raw.isdecimal() else 0
            except ValueError:
                selection = 0
            if 1 <= selection <= len(labels):
                return selection - 1
            self.output(
                "Selezione non valida / Invalid selection. " + hint
                if bilingual else self.messages("Selection is outside the available choices") + ". " + hint
            )

    def text(
        self,
        question: str,
        default: str | None = None,
        validator: Callable[[str], object] | None = None,
    ) -> str:
        if default is not None:
            default = default.strip()
            if not default:
                raise ConfigurationError(self.messages("Text default must not be empty"))
            if validator is not None:
                validator(default)
        suffix = f" [{default}]" if default is not None else ""
        self.output(self.messages(
            "Press Enter to use the displayed default." if default is not None
            else "Required; Enter has no default."
        ))
        while True:
            value = self.read(f"{question}{suffix}: ")
            if not value and default is not None:
                value = default
            if not value:
                self.output(self.messages("{question} is required", question=question))
                continue
            try:
                if validator is not None:
                    validator(value)
            except ConfigurationError as exc:
                self.output(exc.render(self.messages.language))
                continue
            return value

    def yes_no(self, question: str, default: bool = False) -> bool:
        if type(default) is not bool:
            raise ConfigurationError("Yes/no default must be a boolean")
        affirmative = YES_WORDS[self.messages.language]
        negative = NO_WORDS[self.messages.language]
        yes, no = affirmative[0], negative[0]
        suffix = f"[{yes.upper()}/{no}]" if default else f"[{yes}/{no.upper()}]"
        self.output(self.messages(
            "Yes: {yes}; No: {no}; Enter = {default}.",
            yes="/".join(affirmative), no="/".join(negative),
            default=self.messages("Yes" if default else "No"),
        ))
        while True:
            value = self.read(f"{question} {suffix}: ").casefold()
            if not value:
                return default
            if value in negative:
                return False
            if value in affirmative:
                return True
            self.output(self.messages("Answer yes or no"))


def parse_model_capacity(value: str, model: ModelChoice) -> int:
    try:
        if not re.fullmatch(r"[0-9]+", value):
            raise ConfigurationError("Model capacity must be a positive integer")
        capacity = validate_model_capacity(int(value))
    except ValueError as exc:
        raise ConfigurationError("Model capacity must be a positive integer") from exc
    if (
        (model.minimum_capacity is not None and capacity < model.minimum_capacity)
        or (model.maximum_capacity is not None and capacity > model.maximum_capacity)
    ):
        raise ConfigurationError("Model capacity is outside Azure's returned SKU range")
    return capacity


def collect_websites(
    prompts: ConsolePrompts, draft: WizardDraft | None = None,
) -> tuple[str, ...]:
    """Collect intent without ever converting a host-only request to descendants."""
    tr = prompts.messages
    policies: dict[str, bool] = {}
    remembered = draft.get("domains", []) if draft is not None else []
    more = draft.get("domain_more", False) if draft is not None else False
    prompts.output(tr(
        "Native search always includes subdomains. Only Yes is supported; choosing No "
        "blocks installation without broadening your policy. Saved policies apply only "
        "to the same domain; new domains default to No."
        if remembered else
        "Native search always includes subdomains. Only Yes is supported; choosing No "
        "blocks installation without broadening your policy. No is the default."
    ))
    prompts.output(tr(
        "Enter one public domain (example.org) or root HTTPS URL (https://example.org/). "
        "At least one is required, up to 100 distinct domains; no paths, wildcards, "
        "credentials, ports, query, fragment, or IP addresses."
    ))
    while True:
        index = len(policies)
        previous = remembered[index] if index < len(remembered) else {}
        try:
            raw = prompts.text(
                tr("Authorized public domain or root HTTPS URL"),
                default=previous.get("domain"),
            )
            domain = validate_websites([raw])[0]
        except ConfigurationError as exc:
            prompts.output(tr("Invalid domain: {reason}", reason=exc))
            continue
        if domain in policies:
            policy = tr("with subdomains" if policies[domain] else "only this host")
            prompts.output(tr(
                "{domain} was already entered ({policy}). Enter a different domain; "
                "cancel and restart to change its policy.",
                domain=domain, policy=policy,
            ))
            continue
        if any(rule["domain"] == domain for rule in remembered[index + 1:]):
            prompts.output(tr("Domain {domain} is already in the remaining saved rules. Enter a different domain.", domain=domain))
            continue
        rule = dict(previous) if previous.get("domain") == domain else {"domain": domain}
        if index < len(remembered):
            remembered[index] = rule
        else:
            remembered.append(rule)
            more = False
        if draft is not None:
            draft.update(domains=remembered, domain_more=more)
        policies[domain] = prompts.yes_no(
            tr("Include subdomains of {domain}?", domain=domain),
            default=rule.get("include_subdomains", False),
        )
        rule["include_subdomains"] = policies[domain]
        if draft is not None:
            draft.update(domains=remembered)
        if not policies[domain]:
            prompts.output(tr(
                "Host-only policy for {domain} is unsupported; this choice will block installation.",
                domain=domain,
            ))
        if len(policies) == 100:
            prompts.output(tr("Maximum of 100 distinct domains reached."))
            if draft is not None:
                draft.update(domains=remembered[:100], domain_more=False)
            break
        add_another = prompts.yes_no(
            tr("Add another domain?"), default=index + 1 < len(remembered) or more,
        )
        if not add_another:
            if draft is not None:
                draft.update(domains=remembered[:index + 1], domain_more=False)
            break
        if draft is not None and index + 1 == len(remembered):
            draft.update(domain_more=True)
    prompts.output(tr("Requested domain policies:"))
    for domain, include_subdomains in policies.items():
        policy = tr("with subdomains" if include_subdomains else "only this host")
        prompts.output(f"  {domain}: {policy}")
    unsupported = [domain for domain, include in policies.items() if not include]
    if unsupported:
        raise CapabilityError(tr(
            "Unsupported host-only policies: {domains}. Native web_search.filters.allowed_domains "
            "always includes descendants and cannot honor these choices. Installation stopped "
            "before terms or provisioning; no resources were created by this installer.",
            domains=", ".join(unsupported),
        ))
    prompts.output(tr(
        "Native Bing-backed web_search is restricted to these domains, including all their "
        "subdomains; a subdomain does not authorize its parent. Model/region acceptance and "
        "source metadata require manual live verification."
    ))
    return tuple(policies)


def run_wizard(
    discovery: Discovery,
    prompts: ConsolePrompts,
    ui_language: str | None = None,
    draft: WizardDraft | None = None,
) -> InstallerConfig:
    prior_language = (
        draft.get("language", DEFAULT_UI_LANGUAGE) if draft is not None else DEFAULT_UI_LANGUAGE
    )
    if draft is not None and draft.has_answers:
        prompts.messages = InstallerMessages(ui_language or prior_language)
        prompts.output(prompts.messages(
            "Resuming local installer answers. Enter accepts displayed defaults after validation. "
            "Bing terms and final approval always require a fresh Yes. Reset: install --reset-wizard."
        ))
    language = (
        validate_ui_language(ui_language)
        if ui_language is not None
        else SUPPORTED_UI_LANGUAGES[
            prompts.select(
                "Lingua del chatbot e dell'installer / Chatbot and installer language",
                tuple(
                    label + (" (predefinito / default)" if code == prior_language else "")
                    for code, label in zip(SUPPORTED_UI_LANGUAGES, LANGUAGE_LABELS)
                ),
                default_index=SUPPORTED_UI_LANGUAGES.index(prior_language),
                bilingual=True,
            )
        ]
    )
    prompts.messages = InstallerMessages(language)
    if draft is not None:
        draft.update(language=language)
    try:
        return _run_wizard(discovery, prompts, language, draft)
    except (ConfigurationError, DiscoveryError) as exc:
        raise type(exc)(exc.render(language)) from exc


def _run_wizard(
    discovery: Discovery, prompts: ConsolePrompts, language: str,
    draft: WizardDraft | None = None,
) -> InstallerConfig:
    tr = prompts.messages

    def saved(name, default=None):
        return draft.get(name, default) if draft is not None else default

    def remember(*, remove=(), **values):
        if draft is not None:
            draft.update(remove=remove, **values)

    def changed(remove, **values):
        invalidated = remove if any(saved(key) != value for key, value in values.items()) else ()
        if any(saved(key) is not None for key in invalidated):
            prompts.output(tr("Selection changed; dependent resource/model defaults were cleared."))
        remember(remove=invalidated, **values)

    def default_index(prior, choices):
        if prior is None:
            return None
        if prior in choices:
            return choices.index(prior)
        prompts.output(tr(
            "Saved selection is no longer available in the current discovery: {value}. Choose an available option.",
            value=prior,
        ))
        return None

    subscriptions = discovery.subscriptions()
    prior_subscription = (
        (saved("tenant_id"), saved("subscription_id")) if saved("subscription_id") else None
    )
    subscription = subscriptions[
        prompts.select(
            tr("Choose a signed-in tenant and subscription"),
            [f"{item.name} (tenant {item.tenant_id}; {item.subscription_id})" for item in subscriptions],
            default_index=default_index(
                prior_subscription,
                [(item.tenant_id, item.subscription_id) for item in subscriptions],
            ),
        )
    ]
    changed(
        ("resource_group", "create_group", "location", "model", "capacity",
         "environment_name", "deployment_name"),
        tenant_id=subscription.tenant_id, subscription_id=subscription.subscription_id,
    )

    groups = discovery.resource_groups(subscription.subscription_id)
    group_labels = [tr("Create a new resource group"), *groups]
    prior_group = (
        0 if saved("create_group") is True
        else default_index(saved("resource_group"), groups)
    )
    if saved("create_group") is not True and prior_group is not None:
        prior_group += 1
    group_index = prompts.select(
        tr("Choose an existing or new resource group"), group_labels, default_index=prior_group,
    )
    create_group = group_index == 0
    changed(
        ("resource_group", "environment_name", "deployment_name"),
        create_group=create_group,
    )
    if create_group:
        prompts.output(tr(
            "Use 1-90 ASCII letters, digits, periods, underscores, parentheses or hyphens "
            "(e.g. rg-assistant). Azure checks existence and permissions later."
        ))
        resource_group = prompts.text(
            tr("New resource group name"),
            default=saved("resource_group"),
            validator=lambda value: validate_resource_group(value, tr("Resource group name")),
        )
    else:
        resource_group = validate_resource_group(groups[group_index - 1], tr("Resource group name"))
    changed(("environment_name", "deployment_name"), resource_group=resource_group)

    regions = discovery.regions(subscription.subscription_id)
    region = regions[
        prompts.select(
            tr("Choose an Azure region returned for this subscription"),
            [f"{item.display_name} ({item.name})" for item in regions],
            default_index=default_index(saved("location"), [item.name for item in regions]),
        )
    ]
    changed(("model", "capacity"), location=region.name)
    models = discovery.models(subscription.subscription_id, region.name)
    identities = [
        {"name": item.name, "version": item.version, "format": item.model_format, "sku": item.sku}
        for item in models
    ]
    model = models[
        prompts.select(
            tr("Choose a model, version, format, and deployment SKU returned by Azure"),
            [item.label for item in models],
            default_index=default_index(saved("model"), identities),
        )
    ]
    changed(
        ("capacity",),
        model={"name": model.name, "version": model.version, "format": model.model_format, "sku": model.sku},
    )
    default_capacity = model.default_capacity
    if default_capacity is None:
        default_capacity = InstallerConfig.model_capacity
        if model.minimum_capacity is not None:
            default_capacity = max(default_capacity, model.minimum_capacity)
        if model.maximum_capacity is not None:
            default_capacity = min(default_capacity, model.maximum_capacity)
    if saved("capacity") is not None:
        try:
            default_capacity = parse_model_capacity(str(saved("capacity")), model)
        except ConfigurationError:
            prompts.output(tr(
                "Saved capacity {capacity} is outside the current model/SKU bounds; offering the valid model default instead.",
                capacity=saved("capacity"),
            ))
            remember(remove=("capacity",))
    _capacity_guidance(model, default_capacity, prompts)
    capacity_question = tr("Model capacity")
    minimum_label, maximum_label = tr("minimum"), tr("maximum")
    prompts.output(tr(
        "Press Enter to keep this value, or enter another value (positive integer)."
    ))
    capacity_bounds = []
    if model.minimum_capacity is not None:
        capacity_bounds.append(f"{minimum_label} {model.minimum_capacity}")
    if model.maximum_capacity is not None:
        capacity_bounds.append(f"{maximum_label} {model.maximum_capacity}")
    if capacity_bounds:
        capacity_question += f" ({'; '.join(capacity_bounds)})"
    capacity_text = prompts.text(
        capacity_question, default=str(default_capacity),
        validator=lambda value: parse_model_capacity(value, model),
    )
    model_capacity = parse_model_capacity(capacity_text, model)
    remember(capacity=model_capacity)

    prompts.output(tr(
        "Technical ID, not the public chat label: use 3-24 lowercase letters, digits or "
        "hyphens, starting with a letter (e.g. assistente-demo). "
        "Public UI labels can contain spaces and are configured separately."
    ))
    chatbot_name = prompts.text(
        tr("Chatbot technical name"),
        default=saved("chatbot_name"),
        validator=lambda value: validate_identifier(tr("Chatbot technical name"), value),
    )
    remember(chatbot_name=chatbot_name)
    environment_question = tr("Short installation name (e.g. assistant-demo)")
    prompts.output(tr(
        "This is an internal name used to save the installer configuration and derive "
        "Azure resource names."
    ))
    prompts.output(tr(
        "It can differ from the resource-group name already chosen; "
        "it is not the chat title visitors see."
    ))
    prompts.output(tr(
        "Use 3–24 lowercase letters, digits or hyphens, starting with a letter."
    ))
    prompts.output(tr(
        "Reuse this name for updates: changing it can generate a separate set of resources."
    ))
    environment_name = prompts.text(
        environment_question,
        default=saved("environment_name"),
        validator=lambda value: validate_identifier(tr("Installation name"), value),
    )
    remember(environment_name=environment_name)
    prompts.output(tr(
        "The deployment name identifies the model route on the endpoint, not the model "
        "catalog name. Use 1-128 ASCII letters, digits, periods, underscores or hyphens, "
        "starting with a letter or digit (e.g. chat-model)."
    ))
    deployment_name = prompts.text(
        tr("Model deployment name"),
        default=saved("deployment_name"),
        validator=lambda value: validate_azure_name(tr("Model deployment name"), value),
    )
    remember(deployment_name=deployment_name)

    prompts.output(tr(
        "Chat uses Bing web grounding by default, restricted to authorized domains. "
        "Document search is optional and off "
        "unless you enable it."
    ))
    use_search = prompts.yes_no(tr(
        "Optional: add Blob storage and Azure AI Search for administrator-managed "
        "documents (adds Search and Storage costs)"
    ), default=saved("use_search", False))
    remember(use_search=use_search)
    websites = collect_websites(prompts, draft)
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
    if not prompts.yes_no(tr(
        "Accept Bing grounding cost, terms, and data flow outside Azure compliance/Geo boundaries"
    ), default=False):
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
