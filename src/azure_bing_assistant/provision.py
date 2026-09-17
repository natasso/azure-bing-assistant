"""Subscription-scope Bicep deployment with in-memory secure parameters."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .azd import redact
from .azure_cli import AzureCliResolutionError, azure_cli_invocation
from .config import DEFAULT_UI_LANGUAGE, InstallerConfig, WebSearchProvider
from .installer_messages import InstallerMessages


class ProvisioningError(RuntimeError):
    """Raised when Azure rejects or cannot confirm infrastructure deployment."""


_DEPLOYMENT_ID = re.compile(
    r"/subscriptions/(?P<subscription>[A-Za-z0-9-]{1,64})"
    r"(?:/resourceGroups/(?P<group>[A-Za-z0-9_().-]{1,90}))?"
    r"/providers/Microsoft\.Resources/deployments/(?P<name>[A-Za-z0-9_.-]{1,64})",
    re.IGNORECASE,
)
_ERROR_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}")
_QUOTA_NUMBERS = (
    ("Required capacity", r"\brequires? ([0-9]{1,9}) new capacity\b"),
    ("Available capacity", r"\bcurrent available capacity(?: is)?[ :]+([0-9]{1,9})\b"),
    ("Current usage", r"\bcurrent (?:quota )?usage(?:(?: of| is))?[ :]+([0-9]{1,9})\b"),
    ("Current limit", r"\b(?:current (?:quota )?limit|quota limit)(?:(?: of| is))?[ :]+([0-9]{1,9})\b"),
)
_ACCOUNT_ID = re.compile(
    r"/subscriptions/(?P<subscription>[A-Za-z0-9-]{1,64})"
    r"/resourceGroups/(?P<group>[A-Za-z0-9_().-]{1,90})"
    r"/providers/Microsoft\.CognitiveServices/accounts/"
    r"(?P<account>[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?)", re.IGNORECASE,
)
_ATTEMPT_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
RESUME_MESSAGES = (
    "Checking the previous Azure deployment before provisioning.",
    "No previous deployment was found; starting an incremental deployment.",
    "An Azure deployment is still running; waiting without submitting another deployment.",
    "The running deployment changed during inspection; no saved outputs were accepted.",
    "Inspecting existing resources with Azure what-if (no resource changes).",
    "Azure resource comparison: unchanged {unchanged}, to create {create}, to update {modify}, unresolved {unresolved}.",
    "Azure could not fully compare existing resources; continuing with incremental reconciliation, not assuming they are complete.",
    "Infrastructure is already complete and unchanged; reusing confirmed Azure outputs.",
    "Continuing incremental reconciliation with the saved resource names; no cleanup or automatic recreation.",
    "Azure proposed resource deletion; provisioning stopped without changing resources.",
    "Azure resource: {resource_id} ({state}).",
)


def _utc_timestamp(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|[+-]\d{2}:\d{2})", value,
    ):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        ).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


def _attempt_metadata(payload: Mapping[str, Any]) -> tuple[str | None, str | None, str | None] | None:
    properties = payload.get("properties")
    if not isinstance(properties, Mapping):
        return None
    parameters = properties.get("parameters", {})
    if not isinstance(parameters, Mapping):
        return None
    marker = parameters.get("provisioningOperationId", {})
    if not isinstance(marker, Mapping):
        return None
    marker_id = marker.get("value")
    correlation = properties.get("correlationId")
    timestamp = properties.get("timestamp")
    for value in (marker_id, correlation):
        if value is not None and (not isinstance(value, str) or not _ATTEMPT_UUID.fullmatch(value)):
            return None
    if timestamp is not None and _utc_timestamp(timestamp) is None:
        return None
    if marker_id is None and (correlation is None or timestamp is None):
        return None
    # Keep the original timestamp precision for revision comparisons.
    return marker_id, correlation, timestamp


def _deployment_diagnostic(resource_id: str) -> str | None:
    match = _DEPLOYMENT_ID.fullmatch(resource_id)
    if match is None:
        return None
    subscription, group, name = match.group("subscription", "group", "name")
    scope = "group" if group else "sub"
    command = f"az deployment operation {scope} list --subscription '{subscription}'"
    if group:
        command += f" --resource-group '{group}'"
    return command + f" --name '{name}' --output json"


class DeploymentFailedError(ProvisioningError):
    """Bounded safe context from a terminal ARM response, not a root-cause diagnosis."""

    def __init__(
        self, state: str, url: str, error: object, *,
        timestamp: object = None, additional_errors: Sequence[object] = (),
        attempt_verified: bool = False, operations_read: bool = False,
        details_unverified: bool = False,
    ) -> None:
        self.state = state
        self.timestamp = _utc_timestamp(timestamp)
        self.attempt_verified = attempt_verified
        self.operations_read = operations_read
        self.details_unverified = details_unverified
        self.deleted_account_targets: set[str] = set()
        self._complete = True
        self.codes: list[str] = []
        self.numbers: list[tuple[str, str]] = []
        self.commands: list[str] = []
        current_id = unquote(urlsplit(url).path)
        current = _DEPLOYMENT_ID.fullmatch(current_id)
        self._deployment = current
        command = _deployment_diagnostic(current_id)
        if command:
            self.commands.append(command)
        pending = list(reversed([error, *additional_errors[:16]]))
        if len(additional_errors) > 16:
            self._complete = False
        visited = 0
        while pending and visited < 16:
            node = pending.pop()
            visited += 1
            if not isinstance(node, Mapping):
                self._complete = False
                continue
            code = node.get("code")
            if (
                isinstance(code, str) and _ERROR_CODE.fullmatch(code)
                and redact(code) == code
            ):
                if code not in self.codes:
                    self.codes.append(code)
            else:
                self._complete = False
            # Only literal numeric quota phrases and deployment IDs survive. Never
            # copy arbitrary provider prose, inner JSON, headers or parameters.
            message = node.get("message")
            if message is not None and (not isinstance(message, str) or len(message) > 8192):
                self._complete = False
            message = message[:8192] if isinstance(message, str) else ""
            if code in {"InsufficientQuota", "QuotaExceeded", "SpecialFeatureOrQuotaIdRequired"}:
                for label, pattern in _QUOTA_NUMBERS:
                    match = re.search(pattern, message, re.IGNORECASE)
                    if match and (label, match[1]) not in self.numbers:
                        self.numbers.append((label, match[1]))
            target = node.get("target")
            targets = [target] if isinstance(target, str) else []
            targets.extend(
                match[1] for match in re.finditer(
                    r"""['"](/subscriptions/[^'"\s?#]{1,512})['"]""", message,
                )
            )
            for target in targets:
                nested = _DEPLOYMENT_ID.fullmatch(target)
                if current and nested and (
                    nested["subscription"].lower() == current["subscription"].lower()
                ):
                    command = _deployment_diagnostic(target)
                    if command and command not in self.commands and len(self.commands) < 5:
                        self.commands.append(command)
            if code == "FlagMustBeSetForRestore":
                flag_targets = re.findall(r"""['"](/subscriptions/[^'"]*)['"]""", message)
                if node.get("target") is not None:
                    flag_targets.append(node["target"])
                if not flag_targets:
                    self._complete = False
                for candidate in flag_targets:
                    if not isinstance(candidate, str) or not _ACCOUNT_ID.fullmatch(candidate):
                        self._complete = False
                    else:
                        self.deleted_account_targets.add(candidate.lower())
            details = node.get("details")
            if isinstance(details, list):
                if len(details) > 16:
                    self._complete = False
                pending.extend(reversed(details[:16]))
            elif details is not None:
                self._complete = False
            for name in ("innererror", "innerError"):
                inner = node.get(name)
                if isinstance(inner, Mapping):
                    pending.append(inner)
                elif inner is not None:
                    self._complete = False
            if node.get("additionalInfo"):
                self._complete = False
        if pending:
            self._complete = False
        super().__init__(self.render("en"))

    def can_retry_with_new_foundry_account(self, config: InstallerConfig) -> bool:
        allowed_codes = {
            "DeploymentFailed", "InvalidTemplateDeployment", "ResourceDeploymentFailure",
            "FlagMustBeSetForRestore",
        }
        if (
            self.state != "Failed" or not self.attempt_verified or self.details_unverified
            or not self._complete or "FlagMustBeSetForRestore" not in self.codes
            or set(self.codes) - allowed_codes or len(self.deleted_account_targets) != 1
            or self._deployment is None
        ):
            return False
        account = _ACCOUNT_ID.fullmatch(next(iter(self.deleted_account_targets)))
        return bool(
            account
            and account["subscription"].lower() == (config.subscription_id or "").lower()
            and account["group"].lower() == (config.resource_group_name or "").lower()
            and account["account"].lower().startswith(f"ai-{config.environment_name}-")
            and self._deployment["subscription"].lower() == (config.subscription_id or "").lower()
            and self._deployment["name"] == f"chatbot-{config.environment_name}"
            and (
                self._deployment["group"] is None
                or self._deployment["group"].lower() == (config.resource_group_name or "").lower()
            )
        )

    def render(self, language: str) -> str:
        tr = InstallerMessages(language)
        lines = [tr("Azure deployment finished with state {state}", state=self.state)]
        if self.timestamp:
            lines.append(tr("Azure deployment timestamp (UTC): {timestamp}", timestamp=self.timestamp))
        if self.codes:
            lines.append(tr("Reported error codes: {codes}", codes=" -> ".join(self.codes)))
        lines.extend(f"{tr(label)}: {value}" for label, value in self.numbers)
        if self.operations_read:
            lines.append(tr("Failure details were read automatically from this deployment's Azure operations."))
        if self.details_unverified:
            lines.append(tr("Additional failure details could not be verified for this attempt; the original error is preserved."))
        lines.append(tr(
            "This is limited context, not a confirmed root cause. Read the deployment "
            "operation details with these read-only commands; no diagnostic command was executed:"
        ))
        lines.extend(self.commands)
        return "\n".join(lines)

_ARM_API_VERSION = "2022-09-01"
_ARM_SCOPE = "https://management.azure.com/.default"
_TERMINAL_STATES = {"Succeeded", "Failed", "Canceled"}
_DEPLOYMENT_OUTPUT_NAMES = (
    "AZURE_RESOURCE_GROUP",
    "SERVICE_WEB_NAME",
    "FOUNDRY_PROJECT_ENDPOINT",
    "SEARCH_ENDPOINT",
    "SEARCH_INDEX_NAME",
    "SEARCH_INDEXER_NAME",
    "SEARCH_DATA_SOURCE_NAME",
    "SEARCH_CONNECTION_NAME",
    "STORAGE_RESOURCE_ID",
    "STORAGE_ACCOUNT_NAME",
    "STORAGE_CONTAINER_NAME",
    "BING_CUSTOM_SEARCH_RESOURCE_ID",
    "BING_CUSTOM_SEARCH_CONNECTION_ID",
    "BING_CUSTOM_SEARCH_INSTANCE_NAME",
    "WEB_SEARCH_PROVIDER",
)
_REQUIRED_DEPLOYMENT_OUTPUT_NAMES = (
    "SERVICE_WEB_NAME",
    "FOUNDRY_PROJECT_ENDPOINT",
)
_DEPLOYMENT_OUTPUT_BY_CASEFOLD = {
    name.casefold(): name for name in _DEPLOYMENT_OUTPUT_NAMES
}


def provision_argv(config: InstallerConfig, template_file: Path) -> list[str]:
    """Return the only infrastructure subprocess: local Bicep compilation."""
    del config
    return [
        "az",
        "bicep",
        "build",
        "--file",
        str(template_file),
        "--stdout",
    ]


def _deployment_parameters(config: InstallerConfig) -> dict[str, dict[str, Any]]:
    from .config import validate_websites

    validate_websites(config.websites)
    values: dict[str, Any] = {
        "environmentName": config.environment_name,
        "foundryNameSalt": config.foundry_name_salt,
        "resourceGroupName": config.resource_group_name or "",
        "createResourceGroup": config.create_resource_group,
        "location": config.location,
        "knowledgeMode": config.knowledge_mode.value,
        "webSearchProvider": (
            config.web_search_provider or WebSearchProvider.FILTERED_WEB_SEARCH
        ).value,
        "cognitiveUserRoleDefinitionId": config.foundry_user_role_definition_id or "",
        "storageBlobDataReaderRoleDefinitionId": (
            config.storage_blob_data_reader_role_definition_id or ""
        ),
        "searchIndexDataReaderRoleDefinitionId": (
            config.search_index_data_reader_role_definition_id or ""
        ),
        "modelName": config.model_name or "",
        "modelVersion": config.model_version or "",
        "modelFormat": config.model_format or "",
        "modelSku": config.model_sku or "",
        "modelCapacity": config.model_capacity,
        "modelDeploymentName": config.model_deployment_name or "",
        "chatbotName": config.chatbot_name or "",
        "uiLanguage": config.ui_language or DEFAULT_UI_LANGUAGE,
        "uiProductName": config.ui_product_name or "",
        "uiOrganizationName": config.ui_organization_name or "",
        "uiAssistantName": config.ui_assistant_name or "",
        "uiWelcomeTitle": config.ui_welcome_title or "",
        "uiWelcomeSubtitle": config.ui_welcome_subtitle or "",
        "uiDisclaimer": config.ui_disclaimer or "",
        "uiSuggestedQuestions": (
            json.dumps(
                config.ui_suggestions,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if config.ui_suggestions is not None
            else ""
        ),
        "bingTermsAccepted": config.bing_terms_accepted,
        "webGroundingSites": ",".join(config.websites),
    }
    return {name: {"value": value} for name, value in values.items()}


def _canonical_deployment_outputs(result: Mapping[str, Any]) -> dict[str, str]:
    try:
        properties = result["properties"]
        raw_outputs = properties["outputs"]
    except (KeyError, TypeError):
        raise ProvisioningError(
            "Azure did not return confirmed deployment outputs"
        ) from None
    if not isinstance(properties, Mapping) or not isinstance(raw_outputs, Mapping):
        raise ProvisioningError("Azure did not return confirmed deployment outputs")

    outputs: dict[str, str] = {}
    seen: set[str] = set()
    for raw_name, envelope in raw_outputs.items():
        if not isinstance(raw_name, str):
            continue
        canonical_name = _DEPLOYMENT_OUTPUT_BY_CASEFOLD.get(raw_name.casefold())
        if canonical_name is None:
            continue
        if canonical_name in seen:
            raise ProvisioningError(
                f"Azure returned ambiguous deployment output names for {canonical_name}"
            )
        seen.add(canonical_name)
        if not isinstance(envelope, Mapping) or "value" not in envelope:
            raise ProvisioningError(
                f"Azure returned an invalid deployment output for {canonical_name}"
            )
        value = envelope["value"]
        if value is None:
            continue
        if not isinstance(value, str):
            raise ProvisioningError(
                f"Azure returned an invalid deployment output type for {canonical_name}"
            )
        outputs[canonical_name] = value

    missing = [
        name for name in _REQUIRED_DEPLOYMENT_OUTPUT_NAMES if not outputs.get(name)
    ]
    if missing:
        raise ProvisioningError(
            "Azure deployment omitted required outputs: " + ", ".join(missing)
        )
    return outputs


class AzureArmClient:
    """Authenticated Azure Resource Manager transport without request logging."""

    def __init__(self, credential: Any | None = None) -> None:
        try:
            from azure.core.pipeline import Pipeline
            from azure.core.pipeline.policies import (
                BearerTokenCredentialPolicy,
                RetryPolicy,
                UserAgentPolicy,
            )
            from azure.core.pipeline.transport import RequestsTransport
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise ProvisioningError(
                "azure-identity and azure-core are required for provisioning"
            ) from exc

        self._owns_credential = credential is None
        self._credential = DefaultAzureCredential() if credential is None else credential
        self._transport = RequestsTransport(
            connection_timeout=30,
            read_timeout=120,
        )
        self._pipeline = Pipeline(
            transport=self._transport,
            policies=[
                UserAgentPolicy(user_agent="azure-bing-assistant/0.1.0"),
                RetryPolicy(retry_total=5),
                BearerTokenCredentialPolicy(self._credential, _ARM_SCOPE),
            ],
        )

    def __enter__(self) -> AzureArmClient:
        return self

    def __exit__(self, exc_type: object, *_args: object) -> None:
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise

    def close(self) -> None:
        try:
            self._transport.close()
        finally:
            close = getattr(self._credential, "close", None)
            if self._owns_credential and callable(close):
                close()

    def _send_json(
        self,
        method: str,
        url: str,
        *,
        body: Mapping[str, Any] | None = None,
        accepted: set[int] | None = None,
        operation: str,
        retry_total: int | None = None,
        request_timeout: float | None = None,
    ) -> tuple[int, dict[str, Any], Mapping[str, str]]:
        from azure.core.pipeline.transport import HttpRequest

        encoded = None
        headers = {"Accept": "application/json"}
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = HttpRequest(method, url, headers=headers, data=encoded)
        try:
            options = {} if retry_total is None else {"retry_total": retry_total}
            if request_timeout is not None:
                if request_timeout <= 0:
                    raise ProvisioningError("The Azure request time budget expired before submission")
                options.update(
                    connection_timeout=min(30, request_timeout / 2),
                    read_timeout=min(60, request_timeout / 2),
                )
            response = self._pipeline.run(request, stream=False, **options).http_response
            status = response.status_code
            raw = response.text()
        except Exception:
            raise ProvisioningError(
                f"Azure could not {operation}; no deployment state was accepted"
            ) from None
        expected = accepted or {200}
        if status not in expected:
            raise ProvisioningError(
                f"Azure could not {operation} (HTTP {status}); "
                "no deployment state was accepted"
            )
        if not raw.strip():
            return status, {}, response.headers
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise ProvisioningError(
                f"Azure returned an invalid response while attempting to {operation}"
            ) from None
        if not isinstance(payload, dict):
            raise ProvisioningError(
                f"Azure returned an invalid response while attempting to {operation}"
            )
        return status, payload, response.headers

    def read_resource(self, resource_id: str, api_version: str) -> dict[str, Any]:
        if (
            not isinstance(resource_id, str)
            or not re.fullmatch(
                r"/subscriptions/[A-Za-z0-9-]+/resourceGroups/[A-Za-z0-9_().-]+"
                r"/providers/[A-Za-z0-9.]+(?:/[A-Za-z0-9_.-]+){2,}",
                resource_id, re.ASCII | re.IGNORECASE,
            )
            or any(part in {".", ".."} for part in resource_id.split("/"))
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-preview)?", api_version)
        ):
            raise ValueError("An ARM resource ID and API version are required")
        _, payload, _ = self._send_json(
            "GET", "https://management.azure.com" + quote(resource_id, safe="/")
            + "?api-version=" + api_version,
            operation="read resource configuration", retry_total=0, request_timeout=30,
        )
        return payload

    def deploy(
        self,
        subscription_id: str,
        deployment_name: str,
        location: str,
        template: Mapping[str, Any],
        parameters: Mapping[str, Any],
        *,
        timeout: int = 1800,
    ) -> dict[str, Any]:
        url = (
            "https://management.azure.com/subscriptions/"
            f"{quote(subscription_id, safe='')}/providers/Microsoft.Resources/"
            f"deployments/{quote(deployment_name, safe='')}"
            f"?api-version={_ARM_API_VERSION}"
        )
        operation_id = str(uuid.uuid4())
        request_parameters = dict(parameters)
        template_parameters = template.get("parameters")
        if isinstance(template_parameters, Mapping) and (
            "provisioningOperationId" in template_parameters
        ):
            request_parameters["provisioningOperationId"] = {"value": operation_id}
        body = {
            "location": location,
            "properties": {
                "mode": "Incremental",
                "template": template,
                "parameters": request_parameters,
            },
        }
        deadline = time.monotonic() + timeout
        payload: dict[str, Any] = {}
        headers: Mapping[str, str] = {}
        start_attempts = 0
        while True:
            try:
                status, payload, headers = self._send_json(
                    "PUT",
                    url,
                    body=body,
                    accepted={200, 201, 409},
                    operation="start the infrastructure deployment",
                )
            except ProvisioningError as start_error:
                try:
                    get_status, current, current_headers = self._send_json(
                        "GET",
                        url,
                        accepted={200, 404},
                        operation="reconcile the infrastructure deployment",
                    )
                except ProvisioningError:
                    raise start_error from None
                if get_status == 404 or not self._deployment_matches(
                    current, operation_id
                ):
                    raise start_error from None
                payload, headers = current, current_headers
                break
            if status != 409:
                break
            payload, headers = self._wait_for_existing_deployment(
                url, deadline, payload, headers
            )
            if self._deployment_matches(payload, operation_id):
                break
            start_attempts += 1
            if start_attempts >= 3 or time.monotonic() >= deadline:
                raise ProvisioningError(
                    "Azure provisioning conflict did not clear before timeout"
                )

        return self._poll_deployment(
            url, deadline, payload, headers,
            expected_marker=operation_id if "provisioningOperationId" in request_parameters else None,
        )

    def inspect_existing(
        self, config: InstallerConfig, template: Mapping[str, Any],
        parameters: Mapping[str, Any], report: Callable[..., None],
    ) -> dict[str, Any] | None:
        report(RESUME_MESSAGES[0])
        subscription = quote(config.subscription_id or "", safe="")
        url = (
            f"https://management.azure.com/subscriptions/{subscription}/providers/"
            f"Microsoft.Resources/deployments/chatbot-{config.environment_name}"
            f"?api-version={_ARM_API_VERSION}"
        )
        status, current, headers = self._send_json(
            "GET", url, accepted={200, 404},
            operation="inspect the previous infrastructure deployment",
            retry_total=0, request_timeout=60,
        )
        if status == 404:
            report(RESUME_MESSAGES[1])
            return None
        properties = current.get("properties")
        if not isinstance(properties, dict) or not isinstance(
            properties.get("provisioningState"), str,
        ):
            raise ProvisioningError("Azure did not return a valid deployment provisioning state")

        def matches(payload: Mapping[str, Any]) -> bool:
            props = payload.get("properties")
            actual = props.get("parameters") if isinstance(props, Mapping) else None
            return (
                "provisioningConfigHash" in parameters and isinstance(actual, Mapping)
                and all(
                    isinstance(actual.get(key), Mapping)
                    and type(actual[key].get("value")) is type(value["value"])
                    and actual[key].get("value") == value["value"]
                    for key, value in parameters.items()
                )
            )

        if properties["provisioningState"] not in _TERMINAL_STATES:
            report(RESUME_MESSAGES[2])
            metadata = _attempt_metadata(current)
            if matches(current) and metadata is not None and metadata[0] is not None:
                marker = metadata[0]
                current = self._poll_deployment(
                    url, time.monotonic() + 1800, current, headers, expected_marker=marker,
                )
                if not matches(current) or not self._deployment_matches(current, marker):
                    raise ProvisioningError(RESUME_MESSAGES[3])
            else:
                # A different/legacy attempt must finish before incremental reconciliation.
                current, _ = self._wait_for_existing_deployment(
                    url, time.monotonic() + 1800, current, headers,
                )
            properties = current["properties"]
        report(RESUME_MESSAGES[4])
        try:
            changes = self._compare_resources(url, config, template, parameters)
        except ProvisioningError:
            report(RESUME_MESSAGES[6])
            report(RESUME_MESSAGES[8])
            return None
        counts = {name: 0 for name in ("NoChange", "Create", "Modify", "Delete", "unresolved")}
        for change in changes:
            kind = change["changeType"]
            counts[kind if kind in counts else "unresolved"] += 1
            report(RESUME_MESSAGES[10], resource_id=change["resourceId"], state=kind)
        report(
            RESUME_MESSAGES[5], unchanged=counts["NoChange"], create=counts["Create"],
            modify=counts["Modify"], unresolved=counts["unresolved"],
        )
        if counts["Delete"]:
            raise ProvisioningError(RESUME_MESSAGES[9])
        recorded = properties.get("outputResources")
        compared_ids = {change["resourceId"].casefold() for change in changes}
        coverage_complete = (
            isinstance(recorded, list) and 0 < len(recorded) <= 200
            and all(
                isinstance(resource, dict) and isinstance(resource.get("id"), str)
                and resource["id"].casefold() in compared_ids
                for resource in recorded
            )
        )
        if (
            changes and coverage_complete and counts["NoChange"] == len(changes)
            and properties.get("provisioningState") == "Succeeded" and matches(current)
        ):
            _, confirmed, _ = self._send_json(
                "GET", url, operation="confirm the unchanged infrastructure deployment",
                retry_total=0, request_timeout=60,
            )
            confirmed_properties = confirmed.get("properties")
            if (
                not isinstance(confirmed_properties, dict)
                or confirmed_properties.get("provisioningState") != "Succeeded"
                or not matches(confirmed)
                or _attempt_metadata(confirmed) is None
                or _attempt_metadata(confirmed) != _attempt_metadata(current)
            ):
                raise ProvisioningError(RESUME_MESSAGES[3])
            _canonical_deployment_outputs(confirmed)
            report(RESUME_MESSAGES[7])
            return confirmed
        report(RESUME_MESSAGES[8])
        return None

    def _compare_resources(
        self, deployment_url: str, config: InstallerConfig,
        template: Mapping[str, Any], parameters: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        url = deployment_url.replace("?", "/whatIf?", 1)
        request_parameters = dict(parameters)
        if "provisioningOperationId" in template.get("parameters", {}):
            request_parameters["provisioningOperationId"] = {"value": str(uuid.uuid4())}
        body = {"location": config.location, "properties": {
            "mode": "Incremental", "template": template, "parameters": request_parameters,
            "whatIfSettings": {"resultFormat": "FullResourcePayloads"},
        }}
        deadline = time.monotonic() + 120
        status, payload, headers = self._send_json(
            "POST", url, body=body, accepted={200, 202},
            operation="compare existing infrastructure", retry_total=0, request_timeout=60,
        )
        poll_url = None
        for _ in range(20):
            if status == 200 and payload.get("status") == "Succeeded":
                break
            if payload.get("status") in {"Failed", "Canceled"} or time.monotonic() >= deadline:
                raise ProvisioningError("Azure could not complete the resource comparison")
            location = next(
                (value for key, value in headers.items() if key.lower() == "location"), None,
            )
            if location is not None:
                if (
                    not isinstance(location, str) or len(location) > 8192
                    or not location.isascii() or not location.isprintable()
                    or location != location.strip()
                ):
                    raise ProvisioningError("Azure returned an invalid resource comparison URL")
                try:
                    parsed = urlsplit(location)
                    query = parse_qs(parsed.query, keep_blank_values=True)
                except ValueError:
                    raise ProvisioningError("Azure returned an invalid resource comparison URL") from None
                prefix = f"/subscriptions/{quote(config.subscription_id or '', safe='')}/"
                operation_path = parsed.path[len(prefix):]
                if (
                    parsed.scheme != "https" or parsed.netloc != "management.azure.com"
                    or not parsed.path.casefold().startswith(prefix.casefold())
                    or not re.fullmatch(
                        r"(?:operationresults|providers/Microsoft\.Resources/"
                        r"(?:locations/[A-Za-z0-9-]+/)?(?:operationresults|operations))/"
                        r"[A-Za-z0-9._~%+=-]+", operation_path, re.IGNORECASE,
                    )
                    or any(part in {".", ".."} for part in unquote(parsed.path).split("/"))
                    or parsed.fragment
                    or not {"api-version"} <= set(query) <= {"api-version", "t", "c", "s", "h"}
                    or any(len(values) != 1 or not values[0] for values in query.values())
                ):
                    raise ProvisioningError("Azure returned an invalid resource comparison URL")
                poll_url = location
            if poll_url is None:
                raise ProvisioningError("Azure omitted the resource comparison URL")
            self._deployment_pause(headers)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProvisioningError("Azure could not complete the resource comparison")
            status, payload, headers = self._send_json(
                "GET", poll_url, accepted={200, 202},
                operation="wait for the resource comparison", retry_total=0,
                request_timeout=remaining,
            )
        else:
            raise ProvisioningError("Azure could not complete the resource comparison")
        properties = payload.get("properties")
        changes = properties.get("changes") if isinstance(properties, dict) else None
        if (
            not isinstance(changes, list) or len(changes) > 200
            or payload.get("error") or payload.get("diagnostics") or properties.get("diagnostics")
        ):
            raise ProvisioningError("Azure returned an incomplete resource comparison")
        group_id = f"/subscriptions/{config.subscription_id}/resourceGroups/{config.resource_group_name}"
        seen = set()
        for index, change in enumerate(changes):
            if not isinstance(change, dict):
                raise ProvisioningError("Azure returned an invalid resource comparison")
            resource_id = change.get("resourceId")
            kind = change.get("changeType")
            if (
                not isinstance(resource_id, str) or not re.fullmatch(r"/[A-Za-z0-9_()./-]+", resource_id)
                or not (
                    resource_id.casefold() == group_id.casefold()
                    or resource_id.casefold().startswith(group_id.casefold() + "/providers/")
                )
                or resource_id.casefold() in seen
                or kind not in {"NoChange", "Create", "Modify", "Delete", "Ignore", "Deploy", "Unsupported"}
            ):
                raise ProvisioningError("Azure returned an invalid resource comparison")
            seen.add(resource_id.casefold())
            before = change.get("before")
            if kind == "NoChange":
                before_properties = before.get("properties", {}) if isinstance(before, dict) else None
                if (
                    not isinstance(before_properties, dict)
                    or before_properties.get("provisioningState", "Succeeded") != "Succeeded"
                ):
                    changes[index] = dict(change, changeType="Unsupported")
        return changes

    @staticmethod
    def _deployment_matches(payload: Mapping[str, Any], operation_id: str) -> bool:
        properties = payload.get("properties")
        parameters = (
            properties.get("parameters") if isinstance(properties, Mapping) else None
        )
        marker = (
            parameters.get("provisioningOperationId")
            if isinstance(parameters, Mapping)
            else None
        )
        return isinstance(marker, Mapping) and marker.get("value") == operation_id

    def _wait_for_existing_deployment(
        self,
        url: str,
        deadline: float,
        payload: dict[str, Any],
        headers: Mapping[str, str],
    ) -> tuple[dict[str, Any], Mapping[str, str]]:
        while True:
            properties = payload.get("properties")
            state = (
                properties.get("provisioningState")
                if isinstance(properties, dict)
                else None
            )
            if state in _TERMINAL_STATES:
                return payload, headers
            if time.monotonic() >= deadline:
                raise ProvisioningError(
                    "Azure provisioning conflict did not clear before timeout"
                )
            self._deployment_pause(headers)
            _, payload, headers = self._send_json(
                "GET",
                url,
                operation="wait for the concurrent infrastructure deployment",
            )

    @staticmethod
    def _deployment_pause(headers: Mapping[str, str]) -> None:
        retry_after = headers.get("Retry-After", "5")
        delay = int(retry_after) if str(retry_after).isdigit() else 5
        time.sleep(max(1, min(delay, 30)))

    def _poll_deployment(
        self,
        url: str,
        deadline: float,
        payload: dict[str, Any],
        headers: Mapping[str, str],
        *,
        expected_marker: str | None = None,
    ) -> dict[str, Any]:
        initial_properties = payload.get("properties")
        initial_correlation = (
            initial_properties.get("correlationId") if isinstance(initial_properties, Mapping) else None
        )
        if not isinstance(initial_correlation, str) or not _ATTEMPT_UUID.fullmatch(initial_correlation):
            initial_correlation = None
        while True:
            properties = payload.get("properties")
            state = (
                properties.get("provisioningState")
                if isinstance(properties, dict)
                else None
            )
            if state in _TERMINAL_STATES:
                if state != "Succeeded":
                    raise self._deployment_failure(
                        url, deadline, payload, expected_marker, initial_correlation,
                    )
                return payload
            if payload and not isinstance(state, str):
                raise ProvisioningError(
                    "Azure did not return a valid deployment provisioning state"
                )
            if time.monotonic() >= deadline:
                raise ProvisioningError(
                    "Azure deployment did not reach a terminal state before timeout"
                )
            self._deployment_pause(headers)
            _, payload, headers = self._send_json(
                "GET",
                url,
                operation="poll the infrastructure deployment",
            )

    def _deployment_failure(
        self, url: str, deadline: float, payload: dict[str, Any], expected_marker: str | None,
        initial_correlation: str | None = None,
    ) -> DeploymentFailedError:
        properties = payload["properties"]
        original = DeploymentFailedError(
            properties["provisioningState"], url, properties.get("error"),
            timestamp=properties.get("timestamp"), details_unverified=True,
        )
        metadata = _attempt_metadata(payload)
        parsed = urlsplit(url)
        budget = min(deadline, time.monotonic() + 30)
        if (
            original.state != "Failed" or budget <= time.monotonic() or metadata is None
            or parsed.scheme != "https" or parsed.netloc != "management.azure.com"
            or parsed.fragment or parsed.query != f"api-version={_ARM_API_VERSION}"
            or _DEPLOYMENT_ID.fullmatch(unquote(parsed.path)) is None
            or (
                payload.get("id") is not None
                and (not isinstance(payload["id"], str) or payload["id"].lower() != unquote(parsed.path).lower())
            )
            or (
                expected_marker is not None and metadata[0] != expected_marker
                and (
                    metadata[0] is not None or initial_correlation is None
                    or metadata[1] != initial_correlation
                )
            )
        ):
            return original

        def read(target: str) -> dict[str, Any]:
            remaining = budget - time.monotonic()
            if remaining <= 0:
                raise ProvisioningError("Diagnostic time budget expired")
            _, result, _ = self._send_json(
                "GET", target, operation="read deployment failure diagnostics",
                request_timeout=remaining, retry_total=0,
            )
            if time.monotonic() >= budget:
                raise ProvisioningError("Diagnostic time budget expired")
            return result

        try:
            operations = read(parsed._replace(path=parsed.path + "/operations").geturl())
            rows = operations.get("value")
            if not isinstance(rows, list) or len(rows) > 64 or operations.get("nextLink"):
                return original
            errors = []
            for row in rows:
                details = row.get("properties") if isinstance(row, Mapping) else None
                if not isinstance(details, Mapping):
                    return original
                if details.get("provisioningState") == "Succeeded":
                    continue
                if details.get("provisioningState") != "Failed":
                    return original
                message = details.get("statusMessage")
                error = message.get("error") if isinstance(message, Mapping) else None
                if not isinstance(error, Mapping) or len(errors) >= 16:
                    return original
                errors.append(error)
            current = read(url)
            current_properties = current.get("properties")
            if (
                _attempt_metadata(current) != metadata
                or not isinstance(current_properties, Mapping)
                or current_properties.get("provisioningState") != original.state
                or (
                    current.get("id") is not None
                    and (not isinstance(current["id"], str) or current["id"].lower() != unquote(parsed.path).lower())
                )
            ):
                return original
        except (ProvisioningError, KeyError, TypeError, ValueError):
            return original
        enriched = DeploymentFailedError(
            original.state, url, properties.get("error"), timestamp=properties.get("timestamp"),
            additional_errors=errors, attempt_verified=True, operations_read=bool(errors),
        )
        return enriched if enriched._complete else original


class AzureProvisioner:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd

    def _compile_template(
        self,
        config: InstallerConfig,
        template_file: Path,
    ) -> dict[str, Any]:
        try:
            argv, environment = azure_cli_invocation(
                provision_argv(config, template_file)
            )
            completed = subprocess.run(
                argv,
                cwd=self.cwd,
                env=environment,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (AzureCliResolutionError, OSError, subprocess.TimeoutExpired) as exc:
            detail = (
                str(exc)
                if isinstance(exc, AzureCliResolutionError)
                else type(exc).__name__
            )
            raise ProvisioningError(
                f"Bicep compilation could not run: {detail}"
            ) from exc
        if completed.returncode:
            detail = redact((completed.stderr or "Bicep compilation failed").strip())
            raise ProvisioningError(detail)
        try:
            template = json.loads(completed.stdout)
        except json.JSONDecodeError:
            raise ProvisioningError("Bicep did not return a valid ARM template") from None
        if not isinstance(template, dict):
            raise ProvisioningError("Bicep did not return a valid ARM template")
        return template

    def run(self, config: InstallerConfig) -> dict[str, str]:
        config.require_complete_install()
        with AzureArmClient() as arm:
            template = self._compile_template(
                config, self.cwd / "infra" / "main.bicep"
            )
            parameters = _deployment_parameters(config)
            if "provisioningConfigHash" in template.get("parameters", {}):
                parameters["provisioningConfigHash"] = {"value": hashlib.sha256(
                    json.dumps(
                        {"template": template, "parameters": parameters},
                        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                    ).encode("utf-8")
                ).hexdigest()}
            tr = InstallerMessages(config.ui_language or DEFAULT_UI_LANGUAGE)

            def report(message: str, **values: object) -> None:
                print(tr(message, **values), file=sys.stderr)

            result = arm.inspect_existing(config, template, parameters, report)
            if result is None:
                result = arm.deploy(
                    config.subscription_id or "",
                    f"chatbot-{config.environment_name}",
                    config.location,
                    template,
                    parameters,
                )
            outputs = _canonical_deployment_outputs(result)
            if config.web_search_provider is WebSearchProvider.BING_CUSTOM_SEARCH:
                missing = [
                    name for name in (
                        "BING_CUSTOM_SEARCH_RESOURCE_ID", "BING_CUSTOM_SEARCH_CONNECTION_ID",
                        "BING_CUSTOM_SEARCH_INSTANCE_NAME",
                    ) if not outputs.get(name)
                ]
                if missing:
                    raise ProvisioningError(
                        "Azure deployment omitted required Bing Custom Search outputs: " + ", ".join(missing)
                    )
        return outputs
