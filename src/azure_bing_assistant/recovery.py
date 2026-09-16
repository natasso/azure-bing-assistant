"""Pure recovery guidance: never queries, changes, cancels or deletes Azure resources."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .config import InstallerConfig, KnowledgeMode
from .installer_messages import InstallerMessages

RECOVERY_MESSAGES = (
    "Safe recovery: no recovery commands were executed; nothing was cancelled, deleted or purged.",
    "Validated interactive answers remain local defaults until --reset-wizard. "
    "Bing terms and final approval are always requested again; credentials and consent are not saved.",
    "Provisioning had not started in this attempt. No Azure resources were created by this attempt; "
    "pre-existing resources are unchanged.",
    "Default: keep the resources and diagnose the failure. Remote operations can continue after a local failure "
    "or interruption. Wait until they reach a terminal state before retrying.",
    "A deployment conflict was reported. Inspect the current parent and Foundry deployment operations and "
    "timestamps; wait for the active operation to finish rather than deleting resources or starting another deployment.",
    "A soft-deleted Foundry account may reserve the name. Ask an administrator to inspect and restore the "
    "matching account when appropriate. The installer never purges soft-deleted accounts automatically.",
    "Resolve the reported quota or capacity issue before retrying: request quota, reduce the selected capacity, "
    "or select a supported model/region. Deleting resources is not a general quota fix.",
    "Verify sign-in, subscription tenant and project IAM with an administrator. After access is corrected "
    "and propagated, resume deployment; do not broaden roles or remove domain restrictions.",
    "Infrastructure outputs were confirmed in this attempt. After correcting the failure and checking that "
    "no deployment is still active, resume agent/settings/application deployment without reprovisioning:",
    "Confirmed outputs are not available for a safe deployment-only resume at this phase. Diagnose first, "
    "then rerun the interactive installer using the retained defaults and fresh approval.",
    "Read-only PowerShell diagnostics (not executed). Inventories are evidence, NOT deletion lists:",
    "Resource names not confirmed by current outputs and the installation prefix are unknown; "
    "do not infer ownership from names, tags or the create-resource-group option.",
    "Current confirmed installation resources: web app {web}; Foundry account {account}; project {project}.",
    "Optional clean-slate recovery requires separate explicit approval, backups and verified exclusive ownership. "
    "Only consider the dedicated web app and Foundry resources. Delete the dedicated Foundry project first; "
    "remove the model deployment child if required, then delete the account. "
    "Account deletion must not be assumed to cascade to the project. "
    "Consider the App Service plan only if unused by every other app. Agent, model and plan names require inspection. "
    "Never delete an existing resource group wholesale.",
    "Search/Blob mode only: separately verify the optional Search service {search} and Storage account {storage}. "
    "Deleting them loses indexed content and stored documents; require backups and explicit data-loss approval first.",
    "Unknown",
)
CLEANUP_CANDIDATES = RECOVERY_MESSAGES[13]


def _ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _safe(value: object, pattern: str) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def format_recovery(
    config: InstallerConfig | None,
    stage: str,
    error: BaseException,
    confirmed_outputs: Mapping[str, object] | None = None,
    language: str = "en",
) -> str:
    """Format only caller-confirmed context; untrusted provider prose is never rendered."""
    tr = InstallerMessages(language)
    lines = [tr(RECOVERY_MESSAGES[0]), tr(RECOVERY_MESSAGES[1])]
    if stage in {"Input and discovery", "Saving the environment"}:
        lines.append(tr(RECOVERY_MESSAGES[2]))
        return "\n".join(lines)
    lines.append(tr(RECOVERY_MESSAGES[3]))
    # Classification does not copy provider prose, token contents, or arbitrary codes.
    diagnostic = str(error)[:8192].casefold()
    if re.search(r"\bconflict\b", diagnostic) or any(code in diagnostic for code in (
        "anotheroperationinprogress", "deploymentactive", "operationinprogress",
    )):
        lines.append(tr(RECOVERY_MESSAGES[4]))
    if any(code in diagnostic for code in (
        "softdelete", "soft-delete", "flagmustbesetforrestore", "accountisdeleted",
    )):
        lines.append(tr(RECOVERY_MESSAGES[5]))
    if any(code in diagnostic for code in (
        "quota", "insufficientcapacity", "capacityunavailable",
    )):
        lines.append(tr(RECOVERY_MESSAGES[6]))
    if any(code in diagnostic for code in (
        "403", "401", "authorization", "authentication", "project access", "project iam", "role assignment",
    )):
        lines.append(tr(RECOVERY_MESSAGES[7]))
    outputs = confirmed_outputs or {}
    environment = _safe(getattr(config, "environment_name", None), r"[a-zA-Z0-9][a-zA-Z0-9-]{0,63}")
    subscription = _safe(getattr(config, "subscription_id", None), r"[A-Za-z0-9-]{1,64}")
    group = _safe(getattr(config, "resource_group_name", None), r"[A-Za-z0-9_().-]{1,90}")
    unknown = tr(RECOVERY_MESSAGES[15])
    web = account = project = search = storage = None
    if environment:
        prefix = re.escape(environment)
        web = _safe(outputs.get("SERVICE_WEB_NAME"), rf"app-{prefix}-[a-z0-9]{{1,20}}")
        endpoint = outputs.get("FOUNDRY_PROJECT_ENDPOINT")
        match = re.fullmatch(
            rf"https://(ai-{prefix}-[a-z0-9]{{1,20}})\.services\.ai\.azure\.com/api/projects/(project)",
            endpoint,
        ) if isinstance(endpoint, str) else None
        if match:
            account, project = match.groups()
        endpoint = outputs.get("SEARCH_ENDPOINT")
        match = re.fullmatch(
            rf"https://(srch-{prefix}-[a-z0-9]{{1,20}})\.search\.windows\.net/?",
            endpoint,
        ) if isinstance(endpoint, str) else None
        if match:
            search = match[1]
        storage_prefix = ("st" + environment.replace("-", ""))[:24]
        storage = _safe(outputs.get("STORAGE_ACCOUNT_NAME"), r"[a-z0-9]{3,24}")
        if storage and not storage.startswith(storage_prefix):
            storage = None
    if (
        stage in {"Configuring Foundry and application settings", "Packaging and deploying the application"}
        and environment and web and account and project
    ):
        lines.extend([
            tr(RECOVERY_MESSAGES[8]),
            "azure-bing-assistant deploy --environment " + _ps(environment),
        ])
    else:
        lines.append(tr(RECOVERY_MESSAGES[9]))
    lines.extend([
        tr(RECOVERY_MESSAGES[11]),
        tr(RECOVERY_MESSAGES[12], web=web or unknown, account=account or unknown, project=project or unknown),
        tr(CLEANUP_CANDIDATES),
    ])
    if config is not None and config.knowledge_mode is KnowledgeMode.SEARCH_BLOB:
        lines.append(tr(RECOVERY_MESSAGES[14], search=search or unknown, storage=storage or unknown))
    if subscription and group and environment:
        lines.append(tr(RECOVERY_MESSAGES[10]))
        sub_group = f"--subscription {_ps(subscription)} --resource-group {_ps(group)}"
        parent = f"--subscription {_ps(subscription)} --name {_ps('chatbot-' + environment)}"
        lines.append(
            "az deployment sub show " + parent
            + " --query 'properties.{state:provisioningState,timestamp:timestamp,duration:duration}' --output json"
        )
        projection = "'[].{id:operationId,time:properties.timestamp,state:properties.provisioningState,target:properties.targetResource.id,code:properties.statusMessage.error.code}'"
        lines.append(f"az deployment operation sub list {parent} --query {projection} --output json")
        lines.append(f"az deployment operation group list {sub_group} --name 'foundry' --query {projection} --output json")
        lines.append(
            f"az resource list {sub_group} --query '[].{{name:name,type:type,id:id}}' --output json"
        )
        deleted_query = _ps(
            "[].{id:id,name:name,location:location,deletionDate:properties.deletionDate}"
        )
        lines.append(
            f"az cognitiveservices account list-deleted --subscription {_ps(subscription)} "
            f"--query {deleted_query} --output json"
        )
        if web:
            lines.append(
                f"az webapp log deployment list {sub_group} --name {_ps(web)} --output json"
            )
    return "\n".join(lines)
