from copy import deepcopy
from unittest.mock import Mock

import pytest

from azure_bing_assistant.bing_binding import BingCustomSearchBinding
from azure_bing_assistant.bing_setup import verify_bing_custom_search
from azure_bing_assistant.config import ConfigurationError
from azure_bing_assistant.provision import AzureArmClient, ProvisioningError


SCOPE = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-example"
ACCOUNT_ID = SCOPE + "/providers/Microsoft.Bing/accounts/bing-example"
BINDING = BingCustomSearchBinding(
    SCOPE + "/providers/Microsoft.CognitiveServices/accounts/ai-example/projects/project/connections/bing-custom-search",
    "official-sites",
)
CONFIG_ID = ACCOUNT_ID + "/customSearchConfigurations/" + BINDING.instance_name


@pytest.fixture
def resources():
    return [
        {
            "id": ACCOUNT_ID, "type": "Microsoft.Bing/accounts",
            "kind": "Bing.GroundingCustomSearch", "location": "global",
            "sku": {"name": "G2"}, "properties": {"provisioningState": "Succeeded"},
        },
        {
            "id": CONFIG_ID, "name": BINDING.instance_name,
            "type": "Microsoft.Bing/accounts/customSearchConfigurations",
            "properties": {
                "provisioningState": "Succeeded",
                "allowedDomains": [{
                    "domain": "https://example.org", "includeSubPages": True, "boostLevel": "Default",
                }],
                "blockedDomains": [], "pinnedDomains": [],
            },
        },
        {
            "id": BINDING.connection_id,
            "type": "Microsoft.CognitiveServices/accounts/projects/connections",
            "properties": {
                "category": "GroundingWithCustomSearch", "authType": "ApiKey",
                "target": "https://api.bing.microsoft.com/",
                "metadata": {"ResourceId": ACCOUNT_ID, "ApiType": "Azure"},
            },
        },
    ]


def verify(resources):
    reader = Mock()
    reader.read_resource.side_effect = resources
    verify_bing_custom_search(reader, ACCOUNT_ID, BINDING, ("example.org",))
    return reader


def test_portal_equivalent_configuration_is_read_without_keys_or_publish(resources):
    reader = verify(resources)
    assert reader.read_resource.call_args_list == [
        ((ACCOUNT_ID, "2020-06-10"),),
        ((CONFIG_ID, "2025-05-01-preview"),),
        ((BINDING.connection_id, "2026-05-01"),),
    ]
    assert reader.method_calls == [
        ("read_resource", (ACCOUNT_ID, "2020-06-10"), {}),
        ("read_resource", (CONFIG_ID, "2025-05-01-preview"), {}),
        ("read_resource", (BINDING.connection_id, "2026-05-01"), {}),
    ]


@pytest.mark.parametrize("index,updates", [
    (0, {"id": ACCOUNT_ID + "-other"}),
    (0, {"kind": "Bing.Grounding"}),
    (0, {"location": "westeurope"}),
    (0, {"sku": {"name": "G1"}}),
    (0, {"properties": {"provisioningState": "Updating"}}),
    (1, {"id": CONFIG_ID + "-other"}),
    (1, {"name": "Official-Sites"}),
    (1, {"type": "Microsoft.Bing/accounts"}),
    (2, {"id": BINDING.connection_id + "-other"}),
])
def test_resource_identity_and_kind_must_match(resources, index, updates):
    resources[index].update(updates)
    with pytest.raises(ConfigurationError):
        verify(resources)


@pytest.mark.parametrize("field,value", [
    ("provisioningState", None),
    ("provisioningState", "Creating"),
    ("allowedDomains", []),
    ("allowedDomains", None),
    ("allowedDomains", {}),
    ("blockedDomains", None),
    ("blockedDomains", [{"domain": "https://example.org/private", "includeSubPages": True}]),
    ("pinnedDomains", None),
    ("pinnedDomains", [{"domain": "https://outside.example.net", "query": "*", "condition": "Any"}]),
    ("unrecognizedPolicy", True),
])
def test_incomplete_or_different_configuration_fails_closed(resources, field, value):
    resources[1]["properties"][field] = value
    with pytest.raises(ConfigurationError):
        verify(resources)


@pytest.mark.parametrize("field,value", [
    ("domain", "https://outside.example.net"),
    ("domain", "https://example.org.evil.org"),
    ("domain", "https://example.org/private"),
    ("domain", "http://example.org"),
    ("domain", "https://*.example.org"),
    ("domain", 42),
    ("includeSubPages", False),
    ("includeSubPages", "false"),
    ("includeSubPages", "true"),
    ("includeSubPages", 1),
    ("boostLevel", "Boosted"),
    ("unexpectedPolicy", True),
])
def test_domain_entries_match_the_complete_portal_policy(resources, field, value):
    resources[1]["properties"]["allowedDomains"][0][field] = value
    with pytest.raises(ConfigurationError, match="authorized site policy"):
        verify(resources)


@pytest.mark.parametrize("missing", ["allowedDomains", "blockedDomains", "pinnedDomains"])
def test_absent_collections_are_not_accepted_as_empty(resources, missing):
    del resources[1]["properties"][missing]
    with pytest.raises(ConfigurationError):
        verify(resources)


@pytest.mark.parametrize("field,value", [
    ("category", "Bing"),
    ("category", "GroundingWithBingCustomSearch"),
    ("authType", "AAD"),
    ("target", "https://api.bing.microsoft.com.evil.org/"),
    ("target", "https://api.bing.microsoft.com/?key=SECRET"),
    ("metadata", {"ResourceId": ACCOUNT_ID + "-different"}),
    ("metadata", {}),
    ("provisioningState", "Failed"),
])
def test_arm_connection_must_identify_the_verified_bing_account(resources, field, value):
    resources[2]["properties"][field] = value
    with pytest.raises(ConfigurationError, match="connection does not match") as caught:
        verify(resources)
    assert "SECRET" not in str(caught.value)


def test_order_and_root_slash_do_not_change_policy(resources):
    original = resources[1]["properties"]["allowedDomains"][0]
    original["domain"] = "https://EXAMPLE.ORG/"
    resources[1]["properties"]["allowedDomains"].insert(0, {
        **deepcopy(original), "domain": "https://example.net",
    })
    reader = Mock()
    reader.read_resource.side_effect = resources
    verify_bing_custom_search(reader, ACCOUNT_ID, BINDING, ("example.org", "example.net"))


def test_duplicates_do_not_replace_missing_expected_domain(resources):
    resources[1]["properties"]["allowedDomains"] *= 2
    reader = Mock()
    reader.read_resource.side_effect = resources
    with pytest.raises(ConfigurationError, match="authorized site policy"):
        verify_bing_custom_search(reader, ACCOUNT_ID, BINDING, ("example.org", "example.net"))
    assert reader.read_resource.call_count == 2


@pytest.mark.parametrize("resource_id", [
    ACCOUNT_ID.replace("11111111", "22222222"),
    ACCOUNT_ID.replace("rg-example", "rg-other"),
    ACCOUNT_ID + "?api-version=other",
    "https://outside.example.org/" + ACCOUNT_ID,
    ACCOUNT_ID + "/../other",
])
def test_invalid_resource_scope_never_makes_a_request(resource_id):
    reader = Mock()
    with pytest.raises(ConfigurationError):
        verify_bing_custom_search(reader, resource_id, BINDING, ("example.org",))
    reader.read_resource.assert_not_called()


def test_unreadable_configuration_propagates_without_success_or_agent_changes(resources):
    reader = Mock()
    reader.read_resource.side_effect = [resources[0], ProvisioningError("Azure read failed")]
    with pytest.raises(ProvisioningError, match="Azure read failed"):
        verify_bing_custom_search(reader, ACCOUNT_ID, BINDING, ("example.org",))
    assert reader.read_resource.call_count == 2


def test_arm_resource_read_is_keyless_bounded_and_scoped():
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = Mock(return_value=(200, {"id": CONFIG_ID}, {}))
    assert arm.read_resource(CONFIG_ID, "2025-05-01-preview") == {"id": CONFIG_ID}
    arm._send_json.assert_called_once_with(
        "GET", "https://management.azure.com" + CONFIG_ID + "?api-version=2025-05-01-preview",
        operation="read resource configuration", retry_total=0, request_timeout=30,
    )


@pytest.mark.parametrize("resource_id,api_version", [
    ("https://outside.example.org/resource", "2020-06-10"),
    (ACCOUNT_ID + "?secret=value", "2020-06-10"),
    (ACCOUNT_ID + "/../other", "2020-06-10"),
    (ACCOUNT_ID + "/%2e%2e/other", "2020-06-10"),
    (ACCOUNT_ID, "2020-06-10&secret=value"),
])
def test_arm_reader_rejects_unsafe_resource_urls(resource_id, api_version):
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = Mock()
    with pytest.raises(ValueError):
        arm.read_resource(resource_id, api_version)
    arm._send_json.assert_not_called()
