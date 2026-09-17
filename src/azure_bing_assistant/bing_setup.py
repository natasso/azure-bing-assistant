"""Keyless ARM verification of the native Bing Custom Search configuration."""

from __future__ import annotations

import re
from typing import Any, Mapping, Protocol, Sequence

from .bing_binding import BingCustomSearchBinding
from .config import ConfigurationError, validate_resource_group, validate_websites


_ACCOUNT_TYPE = "Microsoft.Bing/accounts"
_CONFIGURATION_TYPE = _ACCOUNT_TYPE + "/customSearchConfigurations"
_CONNECTION_TYPE = "Microsoft.CognitiveServices/accounts/projects/connections"
_ACCOUNT_ID = re.compile(
    r"/subscriptions/(?P<subscription>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})"
    r"/resourceGroups/(?P<group>[^/]+)/providers/Microsoft\.Bing/accounts/"
    r"(?P<account>[A-Za-z0-9][A-Za-z0-9._-]{0,127})",
    re.IGNORECASE | re.ASCII,
)


class ResourceReader(Protocol):
    def read_resource(self, resource_id: str, api_version: str) -> Mapping[str, Any]: ...


def validate_bing_resource_id(resource_id: str, binding: BingCustomSearchBinding) -> str:
    match = _ACCOUNT_ID.fullmatch(resource_id) if isinstance(resource_id, str) else None
    if (
        match is None
        or "/".join(resource_id.split("/")[:5]).casefold()
        != "/".join(binding.connection_id.split("/")[:5]).casefold()
    ):
        raise ConfigurationError(
            "BING_CUSTOM_SEARCH_RESOURCE_ID must identify the Bing resource in the target subscription and resource group"
        )
    validate_resource_group(match["group"])
    return resource_id


def _properties(
    payload: Mapping[str, Any], resource_id: str, resource_type: str,
    error: str, *, require_state: bool = True,
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ConfigurationError(error)
    actual_id, actual_type = payload.get("id"), payload.get("type")
    properties = payload.get("properties")
    if (
        not isinstance(actual_id, str) or actual_id.casefold() != resource_id.casefold()
        or not isinstance(actual_type, str) or actual_type.casefold() != resource_type.casefold()
        or not isinstance(properties, Mapping)
        or (
            (require_state or "provisioningState" in properties)
            and properties.get("provisioningState") != "Succeeded"
        )
    ):
        raise ConfigurationError(error)
    return properties


def verify_bing_custom_search(
    reader: ResourceReader, resource_id: str, binding: BingCustomSearchBinding,
    websites: Sequence[str],
) -> None:
    resource_id = validate_bing_resource_id(resource_id, binding)
    expected_domains = validate_websites(tuple(websites))
    resource_error = "Bing Custom Search resource identity or state could not be verified."
    account = reader.read_resource(resource_id, "2020-06-10")
    _properties(account, resource_id, _ACCOUNT_TYPE, resource_error)
    sku = account.get("sku")
    if (
        account.get("kind") != "Bing.GroundingCustomSearch"
        or str(account.get("location", "")).casefold() != "global"
        or not isinstance(sku, Mapping) or sku.get("name") != "G2"
    ):
        raise ConfigurationError(resource_error)

    configuration_id = resource_id + "/customSearchConfigurations/" + binding.instance_name
    configuration_error = "Bing Custom Search configuration identity or state could not be verified."
    configuration = reader.read_resource(configuration_id, "2025-05-01-preview")
    properties = _properties(
        configuration, configuration_id, _CONFIGURATION_TYPE, configuration_error,
    )
    if configuration.get("name") != binding.instance_name:
        raise ConfigurationError(configuration_error)

    policy_error = "Bing Custom Search configuration does not match the authorized site policy."
    if (
        set(properties) - {"provisioningState", "allowedDomains", "blockedDomains", "pinnedDomains"}
        or properties.get("blockedDomains") != []
        or properties.get("pinnedDomains") != []
    ):
        raise ConfigurationError(policy_error)
    allowed = properties.get("allowedDomains")
    if not isinstance(allowed, list) or len(allowed) != len(expected_domains):
        raise ConfigurationError(policy_error)
    domains: list[str] = []
    for entry in allowed:
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"domain", "includeSubPages", "boostLevel"}
            or not isinstance(entry.get("domain"), str)
            or not entry["domain"].startswith("https://")
            or entry["includeSubPages"] is not True
            or entry["boostLevel"] != "Default"
        ):
            raise ConfigurationError(policy_error)
        domains.append(entry["domain"])
    try:
        normalized = validate_websites(domains)
    except ConfigurationError:
        raise ConfigurationError(policy_error) from None
    if len(normalized) != len(domains) or set(normalized) != set(expected_domains):
        raise ConfigurationError(policy_error)

    connection_error = "Bing Custom Search connection does not match the configured resource."
    connection = reader.read_resource(binding.connection_id, "2026-05-01")
    properties = _properties(
        connection, binding.connection_id, _CONNECTION_TYPE, connection_error,
        require_state=False,
    )
    metadata = properties.get("metadata")
    linked_resource = metadata.get("ResourceId") if isinstance(metadata, Mapping) else None
    if (
        properties.get("category") != "GroundingWithCustomSearch"
        or properties.get("authType") != "ApiKey"
        or properties.get("target") not in {
            "https://api.bing.microsoft.com", "https://api.bing.microsoft.com/",
        }
        or not isinstance(linked_resource, str)
        or linked_resource.casefold() != resource_id.casefold()
    ):
        raise ConfigurationError(connection_error)
