"""Conditional, identity-bound project access repair for the installing SDK identity."""

from __future__ import annotations

import base64
import json
import re
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any, TypeVar
from urllib.parse import parse_qs, quote, urlsplit

from azure.core.exceptions import AzureError, HttpResponseError

from .agent import SourcePolicyError
from .installer_messages import InstallerMessageError, InstallerMessages
from .provision import AzureArmClient, ProvisioningError

FOUNDRY_USER_ROLE_ID = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
ARM_SCOPE = "https://management.azure.com/.default"
FOUNDRY_SCOPE = "https://ai.azure.com/.default"
_ARM = "https://management.azure.com"
_ROLE_API = "2022-04-01"
_RESOURCE_API = "2025-06-01"
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_ENDPOINT = re.compile(
    r"https://(?P<account>[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?)"
    r"\.services\.ai\.azure\.com/api/projects/"
    r"(?P<project>[A-Za-z0-9][A-Za-z0-9_-]{0,63})"
)

ACCESS_MESSAGES = (
    "If Foundry denies agent configuration (403), the installer will verify its SDK identity "
    "and grant that identity Foundry User only on this project, then wait up to 10 minutes. "
    "This requires roleAssignments/write (Owner, or User Access Administrator plus resource read). "
    "No broader role or domain-filter fallback will be used.",
    "Foundry returned 403. Verifying the installing SDK identity and exact project before repairing access.",
    "Cannot safely bind the SDK identity, subscription tenant and Foundry project. No role was granted. "
    "Verify the selected subscription, tenant and project endpoint, then retry.",
    "The installer cannot manage project access. Ask an administrator with roleAssignments/write "
    "(Owner, or User Access Administrator plus resource read) to grant this installing identity "
    "Foundry User on the exact project. No broader role was requested.",
    "An existing role assignment is conditional or conflicts with the expected identity, role or scope. "
    "Ask an administrator to review it; the installer did not replace it or broaden access.",
    "Project access could not be confirmed. Check project IAM before retrying; no duplicate assignment was submitted.",
    "Foundry User is confirmed for the installing identity on project {scope}.",
    "Waiting for project access propagation ({elapsed}s elapsed, attempt {attempt}/40); domain restrictions remain enforced.",
    "Foundry still denies configuration after the bounded access wait. Check project IAM and tenant policies, "
    "then resume deployment; no broader role or unfiltered agent was attempted.",
    "Foundry configuration time budget expired; no further request was submitted.",
)

PROJECT_PENDING = (
    "ARM confirms the project, but Foundry reports Project not found (404). "
    "Waiting for project availability; no role is granted for this response."
)
PROJECT_WAIT = (
    "Waiting for Foundry project availability ({elapsed}s elapsed, attempt {attempt}/40); "
    "domain restrictions remain enforced."
)
PROJECT_TIMEOUT = (
    "Foundry still reports Project not found after the bounded wait, although the ARM project was verified. "
    "Check Foundry provisioning and endpoint availability before retrying; nothing was deleted."
)
READINESS_MESSAGES = (PROJECT_PENDING, PROJECT_WAIT, PROJECT_TIMEOUT)


class InstallerAccessError(InstallerMessageError, RuntimeError):
    """Only fixed, localizable diagnostics cross this boundary."""


def _uuid(value: Any) -> str:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise ValueError("Invalid identity")
    return str(uuid.UUID(value))


def _identity(credential: Any, scope: str) -> tuple[str, str]:
    # The credential, not user-supplied JWT text, authenticates these claims.
    token = credential.get_token(scope).token
    if not isinstance(token, str) or len(token) > 16384:
        raise ValueError("Invalid identity")
    parts = token.split(".")
    if len(parts) != 3 or not all(
        re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts
    ):
        raise ValueError("Invalid identity")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Invalid identity")
            result[key] = value
        return result

    payload = json.loads(
        base64.b64decode(parts[1] + "=" * (-len(parts[1]) % 4), altchars=b"-_", validate=True),
        object_pairs_hook=unique_pairs,
    )
    if not isinstance(payload, dict):
        raise ValueError("Invalid identity")
    return _uuid(payload.get("oid")), _uuid(payload.get("tid"))


def project_scope(subscription: str, resource_group: str, endpoint: str) -> tuple[str, str, str]:
    subscription = _uuid(subscription)
    if (
        not isinstance(resource_group, str)
        or not re.fullmatch(r"[A-Za-z0-9_().-]{1,90}", resource_group)
        or resource_group.endswith(".")
    ):
        raise ValueError("Invalid resource group")
    match = _ENDPOINT.fullmatch(endpoint) if isinstance(endpoint, str) else None
    if match is None:
        raise ValueError("Invalid project endpoint")
    account = (
        f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{match['account']}"
    )
    return account + "/projects/" + match["project"], account, match["account"]


def _same(value: Any, expected: str) -> bool:
    return isinstance(value, str) and value.casefold() == expected.casefold()


def _remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise InstallerAccessError(ACCESS_MESSAGES[9])
    return remaining


def _request(
    client: AzureArmClient, method: str, url: str, *, deadline: float | None = None, **kwargs: Any,
):
    budget = _remaining(deadline)
    return client._send_json(
        method, url, operation="verify project access", retry_total=0,
        request_timeout=budget, **kwargs,
    )


def _assignment_id(value: Any, collection: str) -> str:
    if not isinstance(value, str) or not _same(value[:len(collection) + 1], collection + "/"):
        raise InstallerAccessError(ACCESS_MESSAGES[5])
    name = value[len(collection) + 1:]
    try:
        _uuid(name)
    except ValueError:
        raise InstallerAccessError(ACCESS_MESSAGES[5]) from None
    return collection + "/" + name


def _grant(
    client: AzureArmClient, subscription: str, scope: str, oid: str, *, deadline: float | None = None,
) -> None:
    def request(method: str, url: str, **kwargs: Any):
        return _request(client, method, url, deadline=deadline, **kwargs)

    collection = scope + "/providers/Microsoft.Authorization/roleAssignments"
    role = f"/subscriptions/{subscription}/providers/Microsoft.Authorization/roleDefinitions/{FOUNDRY_USER_ROLE_ID}"
    assignment = collection + "/" + str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"{scope.lower()}|{oid}|{FOUNDRY_USER_ROLE_ID}",
    ))
    filter_value = f"principalId eq '{oid}'"
    list_url = f"{_ARM}{collection}?api-version={_ROLE_API}&$filter={quote(filter_value, safe='')}"

    def matches(payload: Any) -> bool:
        properties = payload.get("properties") if isinstance(payload, Mapping) else None
        if not isinstance(properties, Mapping):
            return False
        equivalent = (
            _same(properties.get("principalId"), oid)
            and _same(properties.get("scope"), scope)
            and _same(properties.get("roleDefinitionId"), role)
        )
        if equivalent and properties.get("condition") not in (None, ""):
            raise InstallerAccessError(ACCESS_MESSAGES[4])
        return equivalent

    def confirm(identifier: str) -> None:
        identifier = _assignment_id(identifier, collection)
        status, payload, _ = request(
            "GET", f"{_ARM}{identifier}?api-version={_ROLE_API}",
            accepted={200, 403, 404},
        )
        if status == 403:
            raise InstallerAccessError(ACCESS_MESSAGES[3])
        if status != 200 or not _same(payload.get("id"), identifier) or not matches(payload):
            raise InstallerAccessError(ACCESS_MESSAGES[5])

    def existing() -> str | None:
        url = list_url
        found: str | None = None
        visited: set[str] = set()
        for _ in range(5):
            if url in visited:
                raise InstallerAccessError(ACCESS_MESSAGES[5])
            visited.add(url)
            status, payload, _ = request("GET", url, accepted={200, 403})
            if status == 403:
                raise InstallerAccessError(ACCESS_MESSAGES[3])
            entries = payload.get("value")
            if not isinstance(entries, list) or len(entries) > 1000:
                raise InstallerAccessError(ACCESS_MESSAGES[5])
            for entry in entries:
                if matches(entry):
                    found = _assignment_id(entry.get("id"), collection)
                elif isinstance(entry, Mapping) and _same(entry.get("id"), assignment):
                    raise InstallerAccessError(ACCESS_MESSAGES[4])
            next_link = payload.get("nextLink")
            if not next_link:
                return found
            if not isinstance(next_link, str) or len(next_link) > 8192:
                raise InstallerAccessError(ACCESS_MESSAGES[5])
            parsed = urlsplit(next_link)
            query = parse_qs(parsed.query)
            if (
                parsed.scheme != "https" or parsed.netloc != "management.azure.com"
                or parsed.path != collection or parsed.fragment
                or query.get("api-version") != [_ROLE_API]
                or query.get("$filter") != [filter_value]
                or set(query) - {"api-version", "$filter", "$skiptoken", "$skipToken"}
            ):
                raise InstallerAccessError(ACCESS_MESSAGES[5])
            url = next_link
        raise InstallerAccessError(ACCESS_MESSAGES[5])

    identifier = existing()
    if identifier is not None:
        confirm(identifier)
        return
    url = f"{_ARM}{assignment}?api-version={_ROLE_API}"
    status, payload, _ = request("GET", url, accepted={200, 403, 404})
    if status == 403:
        raise InstallerAccessError(ACCESS_MESSAGES[3])
    if status == 200:
        if not _same(payload.get("id"), assignment) or not matches(payload):
            raise InstallerAccessError(ACCESS_MESSAGES[4])
        confirm(assignment)
        return
    try:
        status, _, _ = request(
            "PUT", url, accepted={200, 201, 403, 409},
            body={"properties": {"principalId": oid, "roleDefinitionId": role}},
        )
    except ProvisioningError:
        status = 409
    if status == 403:
        raise InstallerAccessError(ACCESS_MESSAGES[3])
    if status == 409:
        identifier = existing()
        if identifier is None:
            raise InstallerAccessError(ACCESS_MESSAGES[5])
        confirm(identifier)
    else:
        confirm(assignment)


def _repair(
    credential: Any, subscription: str, resource_group: str, endpoint: str, *, grant: bool = True,
    deadline: float | None = None,
) -> str:
    if deadline is None:
        deadline = time.monotonic() + 120
    _remaining(deadline)
    try:
        scope, account, domain = project_scope(subscription, resource_group, endpoint)
        subscription = _uuid(subscription)
        oid, tenant = _identity(credential, ARM_SCOPE)
        if _identity(credential, FOUNDRY_SCOPE) != (oid, tenant):
            raise ValueError("Identity mismatch")
    except (AzureError, ValueError, TypeError, AttributeError, RecursionError):
        raise InstallerAccessError(ACCESS_MESSAGES[2]) from None
    try:
        with AzureArmClient(credential=credential) as client:
            _, result, _ = _request(
                client, "GET", f"{_ARM}/subscriptions/{subscription}?api-version=2022-12-01",
                deadline=deadline,
            )
            if not _same(result.get("tenantId"), tenant):
                raise InstallerAccessError(ACCESS_MESSAGES[2])
            _, result, _ = _request(
                client, "GET", f"{_ARM}{scope}?api-version={_RESOURCE_API}", deadline=deadline,
            )
            if not _same(result.get("id"), scope):
                raise InstallerAccessError(ACCESS_MESSAGES[2])
            _, result, _ = _request(
                client, "GET", f"{_ARM}{account}?api-version={_RESOURCE_API}", deadline=deadline,
            )
            properties = result.get("properties")
            if (
                not _same(result.get("id"), account)
                or not isinstance(properties, Mapping)
                or not _same(properties.get("customSubDomainName"), domain)
            ):
                raise InstallerAccessError(ACCESS_MESSAGES[2])
            if grant:
                _grant(client, subscription, scope, oid, deadline=deadline)
    except InstallerAccessError:
        raise
    except (ProvisioningError, AzureError, OSError):
        raise InstallerAccessError(ACCESS_MESSAGES[3] if grant else ACCESS_MESSAGES[2]) from None
    return scope


def _is_forbidden(error: BaseException) -> bool:
    if not isinstance(error, (SourcePolicyError, HttpResponseError)):
        return False
    seen: set[int] = set()
    while error is not None and id(error) not in seen and len(seen) < 16:
        seen.add(id(error))
        if isinstance(error, HttpResponseError) and error.status_code == 403:
            return True
        error = error.__cause__
    return False


def _is_project_pending(error: BaseException) -> bool:
    if not isinstance(error, (SourcePolicyError, HttpResponseError)):
        return False
    seen: set[int] = set()
    while error is not None and id(error) not in seen and len(seen) < 16:
        seen.add(id(error))
        if isinstance(error, HttpResponseError) and error.status_code == 404:
            detail = getattr(error, "error", None)
            code = getattr(detail, "code", None)
            message = getattr(detail, "message", None)
            return (
                isinstance(code, str) and code.casefold() == "notfound"
                and isinstance(message, str)
                and message.strip().rstrip(".").casefold() == "project not found"
            )
        error = error.__cause__
    return False


_Result = TypeVar("_Result")


def configure_with_project_access(
    configure_callback: Callable[[float], _Result],
    credential: Any,
    subscription: str,
    resource_group: str,
    endpoint: str,
    language: str,
    output_stderr: Callable[[str], Any],
    *,
    probe_access: Callable[[float], None] | None = None,
) -> _Result:
    """Retry explicit readiness/permission rejections only after verifying the target in ARM."""
    try:
        return configure_callback(60)
    except (SourcePolicyError, HttpResponseError) as exc:
        pending = _is_project_pending(exc)
        if not _is_forbidden(exc) and not pending:
            raise
    tr = InstallerMessages(language)
    granted = not pending
    if pending:
        _repair(credential, subscription, resource_group, endpoint, grant=False)
        output_stderr(tr(PROJECT_PENDING))
    else:
        output_stderr(tr(ACCESS_MESSAGES[1]))
        scope = _repair(credential, subscription, resource_group, endpoint)
        output_stderr(tr(ACCESS_MESSAGES[6], scope=scope))
    started = time.monotonic()
    deadline = started + 600
    attempts = 1

    def probe_pending_access() -> None:
        nonlocal granted
        remaining = deadline - time.monotonic()
        if not pending or granted or probe_access is None or remaining <= 0:
            return
        try:
            probe_access(min(60, remaining))
        except (SourcePolicyError, HttpResponseError) as exc:
            if _is_forbidden(exc):
                _remaining(deadline)
                output_stderr(tr(ACCESS_MESSAGES[1]))
                scope = _repair(credential, subscription, resource_group, endpoint, deadline=deadline)
                output_stderr(tr(ACCESS_MESSAGES[6], scope=scope))
                granted = True
            elif not _is_project_pending(exc):
                raise

    probe_pending_access()
    while time.monotonic() < deadline:
        output_stderr(tr(
            PROJECT_WAIT if pending else ACCESS_MESSAGES[7],
            elapsed=int(time.monotonic() - started), attempt=attempts,
        ))
        time.sleep(min(15, max(0, deadline - time.monotonic())))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if attempts >= 40:
            continue
        attempts += 1
        try:
            return configure_callback(min(60, remaining))
        except (SourcePolicyError, HttpResponseError) as exc:
            pending = _is_project_pending(exc)
            if _is_forbidden(exc):
                if not granted:
                    _remaining(deadline)
                    output_stderr(tr(ACCESS_MESSAGES[1]))
                    scope = _repair(credential, subscription, resource_group, endpoint, deadline=deadline)
                    output_stderr(tr(ACCESS_MESSAGES[6], scope=scope))
                    granted = True
            elif not pending:
                raise
            probe_pending_access()
    raise InstallerAccessError(PROJECT_TIMEOUT if pending else ACCESS_MESSAGES[8])
