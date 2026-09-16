"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit

from .agent import AgentToolOrchestrator, FoundrySdkWriter
from .azure_cli import AzureCliResolutionError, azure_cli_invocation
from .azd import AppServiceSettingsSynchronizer, AzdError, AzdRunner, redact
from .config import (
    DEFAULT_UI_LANGUAGE,
    ConfigurationError,
    InstallerConfig,
    KnowledgeMode,
    validate_ui_language,
    validate_websites,
)
from .ingestion import document_upload_guidance
from .installer_messages import InstallerMessageError, InstallerMessages
from .install_progress import InstallProgress
from .provision import AzureProvisioner, DeploymentFailedError, ProvisioningError, provision_argv
from .search_blob import AzureRestClient, SearchBlobOrchestrator, SearchBlobSettings
from .wizard import (
    AzureCliDiscovery, CapabilityError, ConsolePrompts, DiscoveryError,
    WizardCancelled, run_wizard,
)
from .wizard_draft import WizardDraft, WizardDraftError

_DEFAULT_AGENT_NAME = "assistant"
_WEB_APP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{1,59}$")
_AZURE_RESOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SEARCH_ARTIFACT_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,127}$")
_STORAGE_ACCOUNT_NAME = re.compile(r"^[a-z0-9]{3,24}$")
_STORAGE_CONTAINER_NAME = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$"
)
_SEARCH_DEPLOYMENT_FIELDS = (
    ("search_endpoint", "SEARCH_ENDPOINT"),
    ("search_index_name", "SEARCH_INDEX_NAME"),
    ("search_indexer_name", "SEARCH_INDEXER_NAME"),
    ("search_data_source_name", "SEARCH_DATA_SOURCE_NAME"),
    ("search_connection_name", "SEARCH_CONNECTION_NAME"),
    ("storage_resource_id", "STORAGE_RESOURCE_ID"),
    ("storage_account_name", "STORAGE_ACCOUNT_NAME"),
    ("storage_container_name", "STORAGE_CONTAINER_NAME"),
)


def _doctor() -> int:
    try:
        azure_argv, azure_environment = azure_cli_invocation(
            ["az", "account", "show", "--query", "id", "--output", "tsv"]
        )
    except AzureCliResolutionError:
        azure_argv = []
        azure_environment = {}
    checks = {
        "python": sys.version_info >= (3, 11),
        "azureCli": bool(azure_argv),
        "azureDeveloperCli": shutil.which("azd") is not None,
        "azureAuthenticated": False,
    }
    if checks["azureCli"]:
        try:
            result = subprocess.run(
                azure_argv,
                env=azure_environment,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            checks["azureAuthenticated"] = result.returncode == 0 and bool(result.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            checks["azureAuthenticated"] = False
    print(json.dumps({"command": "doctor", "checks": checks}, sort_keys=True))
    return 0 if all(checks.values()) else 1


def _commands(config: InstallerConfig, action: str) -> list[list[str]]:
    common = ["--environment", config.environment_name, "--no-prompt"]
    setup = [
        ["azd", "env", "set", name, value, *common]
        for name, value in config.azd_environment_values().items()
        if value
    ]
    provision = provision_argv(config, Path("infra") / "main.bicep")
    if action == "provision":
        return [*setup, provision]
    if action == "deploy":
        return [["azd", "deploy", "web", *common]]
    return [*setup, provision, ["azd", "deploy", "web", *common]]


def _plan(config: InstallerConfig) -> int:
    validate_websites(config.websites)
    search_configured = config.knowledge_mode is KnowledgeMode.SEARCH_BLOB
    payload = {
        "command": "plan",
        "dryRun": True,
        "config": config.public_parameters(),
        "commands": _commands(config, "plan"),
        "environment": {
            "probe": ["azd", "env", "list", "--output", "json"],
            "createIfMissing": [
                "azd",
                "env",
                "new",
                config.environment_name,
                "--no-prompt",
            ],
        },
        "infrastructureDeployment": {
            "compile": "Bicep to stdout",
            "transport": "authenticated Azure Resource Manager HTTPS",
            "parameters": "non-secret in-memory request body",
        },
        "postDeploy": {
            "attachFilteredWebSearch": True,
            "websiteEnforcement": "allowed_domains",
            "attachSearchTool": search_configured,
            "configureBlobIndexer": search_configured,
        },
        "userExperience": {
            "label": (
                "Authorized websites + documents (Azure AI Search, optional)"
                if search_configured
                else "Authorized websites (default)"
            ),
            "bingGroundingConfigured": True,
            "documentSearchConfigured": search_configured,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _interactive_plan(config: InstallerConfig, prompts: ConsolePrompts) -> None:
    validate_websites(config.websites)
    tr = prompts.messages
    prompts.output(tr("Installation plan (no changes yet):"))
    rows = (
        ("Subscription", config.subscription_id),
        ("Resource group", config.resource_group_name),
        ("Create resource group", tr("Yes" if config.create_resource_group else "No")),
        ("Installation name", config.environment_name),
        ("Region", config.location),
        ("Model / version / format / SKU", " / ".join((
            config.model_name or "", config.model_version or "",
            config.model_format or "", config.model_sku or "",
        ))),
        ("Model capacity", config.model_capacity),
        ("Model deployment name", config.model_deployment_name),
        ("Chatbot name", config.chatbot_name),
        ("Chatbot / installer language", config.ui_language),
        ("Optional document search", tr("Yes" if config.knowledge_mode is KnowledgeMode.SEARCH_BLOB else "No")),
    )
    for label, value in rows:
        prompts.output(f"  {tr(label)}: {value}")
    prompts.output(tr("Requested domain policies:"))
    for domain in config.websites:
        prompts.output(f"  {domain}: {tr('with subdomains')}")
    prompts.output(tr(
        "Changes after approval: save azd environment, provision Azure resources and roles, "
        "configure filtered web_search and optional document search, synchronize settings, "
        "deploy the application."
    ))


def _required_environment(
    name: str,
    values: Mapping[str, object] | None = None,
) -> str:
    source = os.environ if values is None else values
    value = source.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("{name} is required for post-deploy setup", name=name)
    return value


@dataclass(frozen=True)
class ResolvedDeployConfig:
    config: InstallerConfig
    foundry_project_endpoint: str
    web_app_name: str
    search_endpoint: str | None = None
    search_index_name: str | None = None
    search_indexer_name: str | None = None
    search_data_source_name: str | None = None
    search_connection_name: str | None = None
    storage_resource_id: str | None = None
    storage_account_name: str | None = None
    storage_container_name: str | None = None

    @property
    def app_settings(self) -> dict[str, str]:
        if self.config.knowledge_mode is None:
            raise ConfigurationError("resolved deployment mode is required")
        return {
            "CHATBOT_NAME": self.config.chatbot_name or _DEFAULT_AGENT_NAME,
            "WEB_GROUNDING_SITES": ",".join(self.config.websites),
            "KNOWLEDGE_MODE": self.config.knowledge_mode.value,
            "UI_LANGUAGE": self.config.ui_language or DEFAULT_UI_LANGUAGE,
            **({
                "STORAGE_ACCOUNT_NAME": self.storage_account_name or "",
                "STORAGE_CONTAINER_NAME": self.storage_container_name or "",
            } if self.config.knowledge_mode is KnowledgeMode.SEARCH_BLOB else {}),
        }


def _persisted_websites(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        if not value.strip():
            return ()
        candidates: list[str] | tuple[str, ...] = value.split(",")
    elif isinstance(value, (list, tuple)):
        if not all(isinstance(item, str) for item in value):
            raise ConfigurationError(
                "WEB_GROUNDING_SITES must be a comma-separated string or a list of strings"
            )
        if not any(item.strip() for item in value):
            return ()
        candidates = tuple(value)
    else:
        raise ConfigurationError(
            "WEB_GROUNDING_SITES must be a comma-separated string or a list of strings"
        )
    return validate_websites(candidates)


def _effective_knowledge_mode(
    configured: KnowledgeMode | None,
    persisted: Mapping[str, object],
) -> KnowledgeMode:
    if configured is not None:
        return configured
    if "KNOWLEDGE_MODE" not in persisted:
        return KnowledgeMode.OFF
    stored = persisted["KNOWLEDGE_MODE"]
    if not isinstance(stored, str):
        raise ConfigurationError("KNOWLEDGE_MODE must be 'off' or 'searchBlob'")
    try:
        return KnowledgeMode(stored)
    except ValueError as exc:
        raise ConfigurationError(
            "KNOWLEDGE_MODE must be 'off' or 'searchBlob'"
        ) from exc


def _effective_ui_language(
    configured: str | None,
    persisted: Mapping[str, object],
) -> str:
    if configured is not None:
        return validate_ui_language(configured)
    if "UI_LANGUAGE" not in persisted:
        return DEFAULT_UI_LANGUAGE
    stored = persisted["UI_LANGUAGE"]
    if not isinstance(stored, str):
        raise ConfigurationError("UI_LANGUAGE must be 'it' or 'en'")
    return validate_ui_language(stored)


def _validate_foundry_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError("FOUNDRY_PROJECT_ENDPOINT is invalid") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.lower().endswith(".services.ai.azure.com")
        or parsed.username
        or parsed.password
        or port
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(
            r"/api/projects/[A-Za-z0-9][A-Za-z0-9._-]*/?", parsed.path
        )
    ):
        raise ConfigurationError("FOUNDRY_PROJECT_ENDPOINT is invalid")
    return value


def _validate_search_prerequisites(
    values: Mapping[str, str | None],
    subscription_id: str,
    resource_group: str,
) -> None:
    endpoint = values["search_endpoint"] or ""
    parsed = urlsplit(endpoint)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError("SEARCH_ENDPOINT is invalid") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{1,58}[a-z0-9]\.search\.windows\.net",
            parsed.hostname.lower(),
        )
        or parsed.username
        or parsed.password
        or port
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError("SEARCH_ENDPOINT is invalid")

    for field_name in (
        "search_index_name",
        "search_indexer_name",
        "search_data_source_name",
    ):
        if not _SEARCH_ARTIFACT_NAME.fullmatch(values[field_name] or ""):
            raise ConfigurationError(
                "{name} is invalid", name=dict(_SEARCH_DEPLOYMENT_FIELDS)[field_name],
            )
    if not _AZURE_RESOURCE_NAME.fullmatch(values["search_connection_name"] or ""):
        raise ConfigurationError("SEARCH_CONNECTION_NAME is invalid")

    storage_account = values["storage_account_name"] or ""
    if not _STORAGE_ACCOUNT_NAME.fullmatch(storage_account):
        raise ConfigurationError("STORAGE_ACCOUNT_NAME is invalid")
    if not _STORAGE_CONTAINER_NAME.fullmatch(values["storage_container_name"] or ""):
        raise ConfigurationError("STORAGE_CONTAINER_NAME is invalid")
    resource_id = values["storage_resource_id"] or ""
    match = re.fullmatch(
        r"/subscriptions/([^/\s]+)/resourceGroups/([^/\s]+)/providers/"
        r"Microsoft\.Storage/storageAccounts/([^/\s]+)",
        resource_id,
        flags=re.IGNORECASE,
    )
    if (
        not match
        or match.group(1).lower() != subscription_id.lower()
        or match.group(2).lower() != resource_group.lower()
        or match.group(3).lower() != storage_account
    ):
        raise ConfigurationError(
            "STORAGE_RESOURCE_ID must identify STORAGE_ACCOUNT_NAME in the "
            "target subscription and resource group"
        )


def _resolve_deploy_config(
    config: InstallerConfig,
    deployment_values: Mapping[str, object],
) -> ResolvedDeployConfig:
    persisted = deployment_values or {}
    knowledge_mode = _effective_knowledge_mode(config.knowledge_mode, persisted)
    ui_language = _effective_ui_language(config.ui_language, persisted)
    agent_name = config.chatbot_name
    if agent_name is None:
        stored_agent_name = persisted.get("CHATBOT_NAME")
        if stored_agent_name is None or (
            isinstance(stored_agent_name, str) and not stored_agent_name.strip()
        ):
            agent_name = _DEFAULT_AGENT_NAME
        elif not isinstance(stored_agent_name, str):
            raise ConfigurationError("CHATBOT_NAME must be a string")
        else:
            agent_name = stored_agent_name

    websites = config.websites
    if not websites:
        websites = _persisted_websites(persisted.get("WEB_GROUNDING_SITES"))
    websites = validate_websites(websites)

    model_deployment_name = config.model_deployment_name or _required_environment(
        "MODEL_DEPLOYMENT_NAME", persisted
    )
    subscription_id = _required_environment("AZURE_SUBSCRIPTION_ID", persisted)
    resource_group = _required_environment("AZURE_RESOURCE_GROUP", persisted)
    web_app_name = _required_environment("SERVICE_WEB_NAME", persisted)
    if not _WEB_APP_NAME.fullmatch(web_app_name):
        raise ConfigurationError("SERVICE_WEB_NAME is not a valid App Service name")
    effective = replace(
        config,
        knowledge_mode=knowledge_mode,
        ui_language=ui_language,
        chatbot_name=agent_name,
        websites=websites,
        model_deployment_name=model_deployment_name,
        subscription_id=subscription_id,
        resource_group_name=resource_group,
    )
    search_values: dict[str, str | None] = {
        "search_endpoint": None,
        "search_index_name": None,
        "search_indexer_name": None,
        "search_data_source_name": None,
        "search_connection_name": None,
        "storage_resource_id": None,
        "storage_account_name": None,
        "storage_container_name": None,
    }
    if effective.knowledge_mode is KnowledgeMode.SEARCH_BLOB:
        for field_name, environment_name in _SEARCH_DEPLOYMENT_FIELDS:
            search_values[field_name] = _required_environment(environment_name, persisted)
        _validate_search_prerequisites(
            search_values,
            subscription_id,
            resource_group,
        )
    foundry_project_endpoint = _validate_foundry_endpoint(
        _required_environment("FOUNDRY_PROJECT_ENDPOINT", persisted)
    )
    return ResolvedDeployConfig(
        config=effective,
        foundry_project_endpoint=foundry_project_endpoint,
        web_app_name=web_app_name,
        **search_values,
    )


def _configure_post_deploy(
    resolved: ResolvedDeployConfig,
) -> None:
    config = resolved.config
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise RuntimeError("azure-identity is required for post-deploy setup") from exc

    credential = DefaultAzureCredential()
    with FoundrySdkWriter(
        resolved.foundry_project_endpoint,
        credential,
        config.model_deployment_name or "",
        owns_credential=True,
    ) as foundry_writer:
        search_index = None
        search_connection = None
        if config.knowledge_mode is KnowledgeMode.SEARCH_BLOB:
            search_client = AzureRestClient(
                resolved.search_endpoint or "",
                credential,
                api_version="2024-07-01",
                scope="https://search.azure.com/.default",
            )
            settings = SearchBlobSettings(
                index_name=resolved.search_index_name or "",
                indexer_name=resolved.search_indexer_name or "",
                data_source_name=resolved.search_data_source_name or "",
                storage_resource_id=resolved.storage_resource_id or "",
                container_name=resolved.storage_container_name or "",
            )
            SearchBlobOrchestrator(search_client, settings).configure()
            search_index = settings.index_name
            search_connection = resolved.search_connection_name
        AgentToolOrchestrator(
            foundry_writer,
            agent_name=config.chatbot_name or _DEFAULT_AGENT_NAME,
        ).configure_tools(
            allowed_domains=config.websites,
            search_index_name=search_index,
            search_connection_name=search_connection,
        )
        if config.knowledge_mode is KnowledgeMode.SEARCH_BLOB:
            tr = InstallerMessages(config.ui_language or DEFAULT_UI_LANGUAGE)
            print(
                "\n".join(tr(line) for line in document_upload_guidance(
                    config.resource_group_name or f"rg-{config.environment_name}",
                    resolved.storage_account_name or "",
                    resolved.storage_container_name or "",
                ).splitlines()),
                file=sys.stderr,
            )


def _sync_app_service_settings(resolved: ResolvedDeployConfig, cwd: str) -> bool:
    return AppServiceSettingsSynchronizer(cwd).synchronize(
        resolved.config.subscription_id or "",
        resolved.config.resource_group_name or "",
        resolved.web_app_name,
        resolved.app_settings,
    )


def _deploy_application(
    runner: AzdRunner,
    config: InstallerConfig,
    deployment_values: Mapping[str, object],
    *,
    phase: Callable[[str], AbstractContextManager] = lambda _label: nullcontext(),
) -> ResolvedDeployConfig:
    with phase("Configuring Foundry and application settings"):
        resolved = _resolve_deploy_config(config, deployment_values)
        _configure_post_deploy(resolved)
        try:
            _sync_app_service_settings(resolved, str(Path.cwd()))
        except (AzdError, ValueError) as exc:
            raise AzdError(
                "Foundry configuration succeeded, but App Service settings could not be "
                "updated; the application package was not deployed"
            ) from exc

        persisted_updates = {
            name: value
            for name, value in resolved.app_settings.items()
            if deployment_values.get(name) != value
        }
        if persisted_updates:
            try:
                _save_deployment_outputs(
                    runner,
                    resolved.config.environment_name,
                    persisted_updates,
                )
            except AzdError as exc:
                raise AzdError(
                    "Foundry and App Service settings are valid, but the resolved "
                    "deployment values could not be fully persisted; the azd environment "
                    "may be partially updated and the application package was not deployed"
                ) from exc
    with phase("Packaging and deploying the application"):
        try:
            runner.run(
                [
                    "azd",
                    "deploy",
                    "web",
                    "--environment",
                    resolved.config.environment_name,
                    "--no-prompt",
                ]
            )
        except AzdError as exc:
            raise AzdError(
                "Foundry and App Service settings are valid, but application package "
                "deployment was not confirmed. Azure may still be running the deployment. "
                "Check App Service deployment logs and application health before retrying."
            ) from exc
    return resolved


def _add_install_arguments(parser: argparse.ArgumentParser, language: str = "en") -> None:
    tr = InstallerMessages(language)
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in KnowledgeMode],
        help=tr(
            "off: authorized websites (default); searchBlob: authorized websites plus optional "
            "administrator-managed documents"
        ),
    )
    parser.add_argument("--environment")
    parser.add_argument("--subscription")
    parser.add_argument("--resource-group")
    parser.add_argument(
        "--create-resource-group",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--location")
    parser.add_argument("--model-name")
    parser.add_argument("--model-version")
    parser.add_argument("--model-format")
    parser.add_argument("--model-sku")
    parser.add_argument("--model-capacity", type=int)
    parser.add_argument("--deployment-name")
    parser.add_argument("--chatbot-name")
    parser.add_argument(
        "--ui-language",
        choices=("it", "en"),
        help=tr("chatbot and installer language (default: it)"),
    )
    parser.add_argument("--ui-product-name")
    parser.add_argument("--ui-organization-name")
    parser.add_argument("--ui-assistant-name")
    parser.add_argument("--ui-welcome-title")
    parser.add_argument("--ui-welcome-subtitle")
    parser.add_argument("--ui-disclaimer")
    parser.add_argument(
        "--ui-suggestion",
        action="append",
        dest="ui_suggestions",
        help=tr("suggested question; repeat up to five times"),
    )
    parser.add_argument(
        "--no-ui-suggestions",
        action="store_true",
        help=tr("show no suggested questions"),
    )
    parser.add_argument("--websites", help=tr(
        "required comma-separated authorized domains or root HTTPS URLs (always includes subdomains)"
    ))
    parser.add_argument("--strict-websites", action="store_true",
                        help=tr("compatibility alias; domain restriction is always required"))
    parser.add_argument("--accept-bing-terms", action="store_true")
    parser.add_argument("--foundry-user-role-id")
    parser.add_argument("--storage-blob-data-reader-role-id")
    parser.add_argument("--search-index-data-reader-role-id")


def _noninteractive_config(args: argparse.Namespace) -> InstallerConfig:
    if args.model_capacity is None:
        raise ConfigurationError("non-interactive install requires: {fields}", fields="model_capacity")
    if args.no_ui_suggestions and args.ui_suggestions is not None:
        raise ConfigurationError(
            "--no-ui-suggestions cannot be combined with --ui-suggestion"
        )
    config = InstallerConfig(
        environment_name=args.environment or "",
        location=args.location or "",
        knowledge_mode=KnowledgeMode(args.mode) if args.mode else KnowledgeMode.OFF,
        subscription_id=args.subscription,
        resource_group_name=args.resource_group,
        create_resource_group=(
            args.create_resource_group if args.create_resource_group is not None else True
        ),
        model_name=args.model_name,
        model_version=args.model_version,
        model_format=args.model_format,
        model_sku=args.model_sku,
        model_capacity=args.model_capacity,
        model_deployment_name=args.deployment_name,
        chatbot_name=args.chatbot_name,
        ui_language=args.ui_language or DEFAULT_UI_LANGUAGE,
        ui_product_name=args.ui_product_name,
        ui_organization_name=args.ui_organization_name,
        ui_assistant_name=args.ui_assistant_name,
        ui_welcome_title=args.ui_welcome_title,
        ui_welcome_subtitle=args.ui_welcome_subtitle,
        ui_disclaimer=args.ui_disclaimer,
        ui_suggestions=(
            ()
            if args.no_ui_suggestions
            else (
                tuple(args.ui_suggestions)
                if args.ui_suggestions is not None
                else None
            )
        ),
        websites=validate_websites((args.websites or "").split(",")),
        strict_websites=args.strict_websites,
        bing_terms_accepted=args.accept_bing_terms,
        foundry_user_role_definition_id=args.foundry_user_role_id,
        storage_blob_data_reader_role_definition_id=args.storage_blob_data_reader_role_id,
        search_index_data_reader_role_definition_id=args.search_index_data_reader_role_id,
    )
    config.require_complete_install()
    return config


def _save_deployment_outputs(
    runner: AzdRunner,
    environment_name: str,
    outputs: dict[str, str],
) -> None:
    for name, value in outputs.items():
        runner.run(
            [
                "azd",
                "env",
                "set",
                name,
                value,
                "--environment",
                environment_name,
                "--no-prompt",
            ]
        )


def build_parser(language: str = "en") -> argparse.ArgumentParser:
    tr = InstallerMessages(language)

    class LocalizedParser(argparse.ArgumentParser):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._optionals.title = tr("options")
            self._positionals.title = tr("positional arguments")
            for action in self._actions:
                if isinstance(action, argparse._HelpAction):
                    action.help = tr("show this help message and exit")

        def error(self, message):
            self.print_usage(sys.stderr)
            self.exit(2, f"{self.prog}: {tr('error')}: {message}\n")

    class LocalizedFormatter(argparse.HelpFormatter):
        def _format_usage(self, usage, actions, groups, prefix):
            return super()._format_usage(usage, actions, groups, prefix or tr("usage: "))

    parser = LocalizedParser(
        prog="azure-bing-assistant",
        description=tr("Install and manage Azure Bing Assistant."),
        formatter_class=LocalizedFormatter,
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor", help=tr("check local tools and Azure authentication"))
    install = subcommands.add_parser(
        "install", help=tr("run the guided customer installation"),
        formatter_class=LocalizedFormatter,
    )
    _add_install_arguments(install, language)
    install.add_argument(
        "--reset-wizard", action="store_true",
        help=tr("discard only the local interactive installer draft and start again"),
    )
    for command in ("plan", "provision", "deploy"):
        child = subcommands.add_parser(command)
        child.add_argument(
            "--mode",
            required=command != "deploy",
            choices=[mode.value for mode in KnowledgeMode],
            help=(
                "off: authorized websites (default); searchBlob: authorized websites plus optional "
                "administrator-managed documents"
            ),
        )
        child.add_argument("--environment")
        child.add_argument("--location")
        child.add_argument("--ui-language", choices=("it", "en"))
        child.add_argument("--websites", help="authorized domains or root HTTPS URLs (always includes subdomains)")
        child.add_argument("--strict-websites", action="store_true",
                           help="compatibility alias; domain restriction is always required")
        if command == "plan":
            child.add_argument("--dry-run", required=True, action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    language = DEFAULT_UI_LANGUAGE if arguments[:1] == ["install"] else "en"
    for index, argument in enumerate(arguments):
        if argument == "--ui-language" and index + 1 < len(arguments):
            language = arguments[index + 1]
        elif argument.startswith("--ui-language="):
            language = argument.partition("=")[2]
    args = build_parser(language).parse_args(arguments)
    if args.command == "doctor":
        return _doctor()
    prompts = None
    draft = None
    stage = "Input and discovery"
    try:
        if args.command == "install":
            if args.reset_wizard and (args.non_interactive or args.dry_run):
                raise ConfigurationError("--reset-wizard requires an interactive install without --dry-run")
            if args.dry_run and not args.non_interactive:
                raise ConfigurationError(
                    "offline install dry-run requires --non-interactive and explicit flags"
                )
            if args.non_interactive:
                config = _noninteractive_config(args)
            else:
                prompts = ConsolePrompts(language=language)
                draft = WizardDraft(Path.cwd())
                if args.reset_wizard:
                    draft.clear(reset=True)
                draft.load()
                config = run_wizard(
                    AzureCliDiscovery(),
                    prompts,
                    ui_language=args.ui_language,
                    draft=draft,
                )
            if args.dry_run:
                return _plan(config)
            if prompts is not None:
                _interactive_plan(config, prompts)
                if not prompts.yes_no(prompts.messages("Proceed with provisioning and deployment"), default=False):
                    prompts.output(prompts.messages("Installation cancelled; Azure state was not changed."))
                    return 1
            phase_number = 0

            def phase(label: str) -> InstallProgress:
                nonlocal stage, phase_number
                stage = label
                phase_number += 1
                return InstallProgress(
                    label, phase_number, 5, config.ui_language or language,
                )

            with phase("Saving the environment"):
                runner = AzdRunner(str(Path.cwd()))
                runner.ensure_environment(config.environment_name)
                for command in _commands(config, "provision")[:-1]:
                    runner.run(command)
            with phase("Provisioning Azure resources"):
                deployment_values = AzureProvisioner(Path.cwd()).run(config)
            with phase("Saving confirmed deployment outputs"):
                _save_deployment_outputs(runner, config.environment_name, deployment_values)
                persisted_values = runner.get_environment_values(config.environment_name)
            resolved = _deploy_application(
                runner, config, persisted_values, phase=phase,
            )
            if prompts is not None:
                prompts.output(prompts.messages("Installation completed."))
            if draft is not None:
                try:
                    draft.clear()
                except WizardDraftError as exc:
                    print(prompts.messages(
                        "Deployment succeeded, but the local installer draft could not be removed: {detail}",
                        detail=exc,
                    ), file=sys.stderr)
            print(
                json.dumps(
                    {
                        "command": "install",
                        "environment": config.environment_name,
                        "mode": resolved.config.knowledge_mode.value,
                        "status": "succeeded",
                    },
                    sort_keys=True,
                )
            )
            return 0
        config = InstallerConfig.from_values(
            mode=args.mode,
            environment_name=args.environment,
            location=args.location,
            ui_language=args.ui_language,
        )
        if args.websites is not None:
            config = replace(config, websites=validate_websites(args.websites.split(",")))
        if args.command == "plan":
            return _plan(config)
        runner = AzdRunner(str(Path.cwd()))
        if args.command == "provision":
            config.require_complete_install()
            runner.ensure_environment(config.environment_name)
            for command in _commands(config, "provision")[:-1]:
                runner.run(command)
            deployment_values = AzureProvisioner(Path.cwd()).run(config)
            _save_deployment_outputs(runner, config.environment_name, deployment_values)
        else:
            deployment_values = runner.get_environment_values(config.environment_name)
            resolved = _deploy_application(runner, config, deployment_values)
        print(
            json.dumps(
                {
                    "command": args.command,
                    "environment": config.environment_name,
                    "mode": (
                        resolved.config.knowledge_mode.value
                        if args.command == "deploy"
                        else config.knowledge_mode.value
                    ),
                    "status": "succeeded",
                },
                sort_keys=True,
            )
        )
        return 0
    except KeyboardInterrupt:
        tr = prompts.messages if prompts is not None else InstallerMessages(language)
        print(tr(
            "Local installation interrupted. Remote operations may continue; "
            "nothing was cancelled or deleted in Azure. Check deployment operations before retrying."
        ) if stage != "Input and discovery" or args.command in {"provision", "deploy"} else tr(
            "Input interrupted; installation cancelled."
        ), file=sys.stderr)
        return 130
    except WizardCancelled as exc:
        tr = prompts.messages if prompts is not None else InstallerMessages(language)
        print(exc.render(tr.language), file=sys.stderr)
        if stage == "Input and discovery":
            print(tr("Installation cancelled; Azure state was not changed."), file=sys.stderr)
        return 1
    except (
        CapabilityError,
        ConfigurationError,
        DiscoveryError,
        AzdError,
        ProvisioningError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        tr = prompts.messages if prompts is not None else InstallerMessages(language)
        detail = exc.render(tr.language) if isinstance(
            exc, (InstallerMessageError, DeploymentFailedError)
        ) else tr(str(exc))
        prefix = (
            f"{tr('Installation failed')} ({tr(stage)})"
            if args.command == "install"
            else tr("error")
        )
        print(f"{prefix}: {detail if isinstance(exc, DeploymentFailedError) else redact(detail)}", file=sys.stderr)
        return 2
