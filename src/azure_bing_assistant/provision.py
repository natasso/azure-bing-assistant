"""Subscription-scope Bicep deployment with in-memory secure parameters."""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from .azd import redact
from .azure_cli import AzureCliResolutionError, azure_cli_invocation
from .config import DEFAULT_UI_LANGUAGE, InstallerConfig


class ProvisioningError(RuntimeError):
    """Raised when Azure rejects or cannot confirm infrastructure deployment."""


_ARM_API_VERSION = "2022-09-01"
_ARM_SCOPE = "https://management.azure.com/.default"
_TERMINAL_STATES = {"Succeeded", "Failed", "Canceled"}
_DEPLOYMENT_OUTPUT_NAMES = (
    "AZURE_RESOURCE_GROUP",
    "SERVICE_WEB_NAME",
    "FOUNDRY_PROJECT_ENDPOINT",
    "BING_CONNECTION_NAME",
    "SEARCH_ENDPOINT",
    "SEARCH_INDEX_NAME",
    "SEARCH_INDEXER_NAME",
    "SEARCH_DATA_SOURCE_NAME",
    "SEARCH_CONNECTION_NAME",
    "STORAGE_RESOURCE_ID",
    "STORAGE_ACCOUNT_NAME",
    "STORAGE_CONTAINER_NAME",
)
_REQUIRED_DEPLOYMENT_OUTPUT_NAMES = (
    "SERVICE_WEB_NAME",
    "FOUNDRY_PROJECT_ENDPOINT",
    "BING_CONNECTION_NAME",
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
    values: dict[str, Any] = {
        "environmentName": config.environment_name,
        "resourceGroupName": config.resource_group_name or "",
        "createResourceGroup": config.create_resource_group,
        "location": config.location,
        "knowledgeMode": config.knowledge_mode.value,
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

    def __init__(self) -> None:
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

        self._credential = DefaultAzureCredential()
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

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._transport.close()
        close = getattr(self._credential, "close", None)
        if callable(close):
            close()

    def _send_json(
        self,
        method: str,
        url: str,
        *,
        body: Mapping[str, Any] | None = None,
        accepted: set[int] | None = None,
        operation: str,
    ) -> tuple[int, dict[str, Any], Mapping[str, str]]:
        from azure.core.pipeline.transport import HttpRequest

        encoded = None
        headers = {"Accept": "application/json"}
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = HttpRequest(method, url, headers=headers, data=encoded)
        try:
            response = self._pipeline.run(request, stream=False).http_response
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

        return self._poll_deployment(url, deadline, payload, headers)

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
    ) -> dict[str, Any]:
        while True:
            properties = payload.get("properties")
            state = (
                properties.get("provisioningState")
                if isinstance(properties, dict)
                else None
            )
            if state in _TERMINAL_STATES:
                if state != "Succeeded":
                    raise ProvisioningError(
                        f"Azure deployment finished with state {state}"
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
            result = arm.deploy(
                config.subscription_id or "",
                f"chatbot-{config.environment_name}",
                config.location,
                template,
                _deployment_parameters(config),
            )
            outputs = _canonical_deployment_outputs(result)
        return outputs
