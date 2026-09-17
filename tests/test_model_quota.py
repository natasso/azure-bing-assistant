from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import subprocess
from unittest.mock import Mock

import pytest

from azure_bing_assistant import model_quota
from azure_bing_assistant.model_quota import QuotaUnavailable, read_model_quota
from azure_bing_assistant.wizard import AzureCliDiscovery, DiscoveryError, ModelChoice


SUBSCRIPTION = "selected-subscription"
LOCATION = "italynorth"
PATH = (
    f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CognitiveServices/"
    f"locations/{LOCATION}/usages"
)
URL = PATH + "?api-version=2024-10-01"
NEXT = URL + "&$skiptoken=second"
USAGE_NAME = "OpenAI.GlobalStandard.example-model"


@pytest.fixture
def azure_payloads():
    # Schema-shaped, synthetic values. The 2024-10-01 published examples verify
    # model.skus[].usageName and Usage.{name.value,currentValue,limit,unit}:
    # https://github.com/Azure/azure-rest-api-specs/tree/main/specification/
    # cognitiveservices/resource-manager/Microsoft.CognitiveServices/stable/
    # 2024-10-01/examples/{ListLocationModels,ListUsages}.json
    return (
        [{
            "kind": "AIServices", "skuName": "S0",
            "model": {
                "format": "OpenAI", "name": "example-model", "version": "1",
                "skus": [{
                    "name": "GlobalStandard", "usageName": USAGE_NAME,
                    "capacity": {"minimum": 1, "maximum": 1000000, "default": 1000},
                }],
            },
        }],
        {"value": [
            {"name": {"value": "AccountCount", "localizedValue": "Accounts"},
             "currentValue": 3, "limit": 200, "unit": "Count"},
            {"name": {"value": USAGE_NAME, "localizedValue": "Tokens per minute (thousands)"},
             "currentValue": 140, "limit": 150, "unit": "Count"},
        ]},
    )


def snapshot(read_json, usage_name=USAGE_NAME):
    return read_model_quota(read_json, SUBSCRIPTION, LOCATION, usage_name)


def test_azure_cli_joins_sku_usage_name_to_regional_subscription_quota(azure_payloads, monkeypatch):
    invocation = Mock(side_effect=lambda args: (list(args), {"SAFE": "yes"}))
    runner = Mock(side_effect=[
        Mock(returncode=0, stdout=json.dumps(payload), stderr="") for payload in azure_payloads
    ])
    monkeypatch.setattr("azure_bing_assistant.wizard.azure_cli_invocation", invocation)
    monkeypatch.setattr("azure_bing_assistant.wizard.subprocess.run", runner)
    discovery = AzureCliDiscovery()
    model = discovery.models(SUBSCRIPTION, LOCATION)[0]
    quota = discovery.quota(SUBSCRIPTION, LOCATION, model)

    assert model.usage_name == USAGE_NAME
    assert quota.limit == 150 and quota.current == 140 and quota.remaining == 10
    assert quota.unit == "Count" and quota.usage_name == USAGE_NAME
    assert quota.checked_at.tzinfo == timezone.utc
    assert abs((datetime.now(timezone.utc) - quota.checked_at).total_seconds()) < 10
    assert model.maximum_capacity == 1000000 and model.default_capacity == 1000
    invocation.assert_called_with([
        "az", "rest", "--method", "get", "--subscription", SUBSCRIPTION,
        "--url", URL, "--output", "json",
    ])
    for call in runner.call_args_list:
        assert call.kwargs == {
            "env": {"SAFE": "yes"}, "shell": False, "check": False,
            "capture_output": True, "text": True, "timeout": 60,
        }


@pytest.mark.parametrize("usage_name", [None, "", " ", [], {}, 123, "pool\nother", "x" * 513])
def test_missing_or_invalid_sku_usage_name_does_not_trigger_guessing(azure_payloads, usage_name):
    models, usages = azure_payloads
    models[0]["model"]["skus"][0]["usageName"] = usage_name
    discovery = AzureCliDiscovery()
    discovery._json = Mock(side_effect=[models, usages])
    model = discovery.models(SUBSCRIPTION, LOCATION)[0]
    assert model.usage_name is None
    with pytest.raises(QuotaUnavailable):
        discovery.quota(SUBSCRIPTION, LOCATION, model)
    discovery._json.assert_called_once()


@pytest.mark.parametrize("duplicate_name", [USAGE_NAME, "another-pool", None])
def test_duplicate_model_metadata_is_deduplicated_without_guessing_pool(azure_payloads, duplicate_name):
    models, _ = azure_payloads
    other = deepcopy(models[0])
    other["model"]["skus"][0]["usageName"] = duplicate_name
    discovery = AzureCliDiscovery()
    discovery._json = Mock(return_value=[models[0], other])
    choices = discovery.models(SUBSCRIPTION, LOCATION)
    assert len(choices) == 1
    assert choices[0].usage_name == (USAGE_NAME if duplicate_name == USAGE_NAME else None)


@pytest.mark.parametrize("unit", ["Count", "CountPerSecond", "Bytes", "futureUnit"])
@pytest.mark.parametrize("values", [(150, 140, 10), (0, 0, 0), (10, 15, 0), (0.3, 0.1, 0.2)])
def test_preserves_units_and_numeric_zero_without_assuming_tpm(azure_payloads, unit, values):
    _, payload = azure_payloads
    limit, current, remaining = values
    payload["value"][1].update(limit=limit, currentValue=current, unit=unit)
    quota = snapshot(Mock(return_value=payload))
    assert quota.unit == unit
    assert quota.limit == Decimal(str(limit))
    assert quota.current == Decimal(str(current))
    assert quota.remaining == Decimal(str(remaining))


def test_preserves_quota_period_and_blocked_status(azure_payloads):
    _, payload = azure_payloads
    payload["value"][1].update(quotaPeriod="P1D", status="Blocked")
    quota = snapshot(Mock(return_value=payload))
    assert quota.period == "P1D" and quota.status == "Blocked"


@pytest.mark.parametrize("field", ["limit", "currentValue"])
@pytest.mark.parametrize("value", [None, "150", True, False, -1, float("nan"), float("inf"), {}, []])
def test_invalid_selected_usage_numbers_are_unavailable(azure_payloads, field, value):
    _, payload = azure_payloads
    payload["value"][1][field] = value
    with pytest.raises(QuotaUnavailable):
        snapshot(Mock(return_value=payload))


@pytest.mark.parametrize("field", ["limit", "currentValue", "unit"])
def test_absent_required_metric_values_are_not_zero(azure_payloads, field):
    _, payload = azure_payloads
    del payload["value"][1][field]
    with pytest.raises(QuotaUnavailable):
        snapshot(Mock(return_value=payload))


@pytest.mark.parametrize(
    "payload",
    [
        None, [], {}, {"value": {}}, {"value": [None]},
        {"value": [{"name": "pool"}]},
        {"value": [{"name": {"localizedValue": USAGE_NAME}}]},
        {"value": [{"name": {"value": "pool\n"}}]},
        {"value": []},
    ],
)
def test_malformed_or_missing_usage_cannot_be_misreported_as_zero(payload):
    with pytest.raises(QuotaUnavailable):
        snapshot(Mock(return_value=payload))


@pytest.mark.parametrize("field", ["unit", "quotaPeriod", "status"])
@pytest.mark.parametrize("value", ["", " ", 123, ["Count"], "Count\nfake"])
def test_malformed_units_period_or_status_make_quota_unavailable(azure_payloads, field, value):
    _, payload = azure_payloads
    payload["value"][1][field] = value
    with pytest.raises(QuotaUnavailable):
        snapshot(Mock(return_value=payload))


@pytest.mark.parametrize("name", [
    "OpenAI.Standard.example-model", "OpenAI.GlobalStandard.example-model-other",
    "example-model", "OpenAI.GlobalStandard.example-model.1",
])
def test_no_sku_model_version_or_localized_name_heuristics(azure_payloads, name):
    _, payload = azure_payloads
    payload["value"][1]["name"] = {"value": name, "localizedValue": USAGE_NAME}
    with pytest.raises(QuotaUnavailable):
        snapshot(Mock(return_value=payload))


@pytest.mark.parametrize("prefix", ["", "https://management.azure.com", "https://management.usgovcloudapi.net"])
def test_follows_scoped_paging_and_searches_all_pages(azure_payloads, prefix):
    _, payload = azure_payloads
    reader = Mock(side_effect=[
        {"value": [payload["value"][0]], "nextLink": prefix + NEXT},
        {"value": [payload["value"][1]]},
    ])
    assert snapshot(reader).remaining == 10
    assert reader.call_args.args[0][7] == NEXT
    assert reader.call_count == 2


@pytest.mark.parametrize("conflicting", [False, True])
def test_checks_later_pages_for_duplicate_quota_conflicts(azure_payloads, conflicting):
    _, payload = azure_payloads
    second = deepcopy(payload)
    if conflicting:
        second["value"][1]["limit"] = 200
    reader = Mock(side_effect=[{**payload, "nextLink": NEXT}, second])
    if conflicting:
        with pytest.raises(QuotaUnavailable):
            snapshot(reader)
    else:
        assert snapshot(reader).remaining == 10
    assert reader.call_count == 2


@pytest.mark.parametrize("field,value", [
    ("limit", 200), ("currentValue", 0), ("unit", "Bytes"), ("status", "Blocked"),
    ("quotaPeriod", "P1D"),
])
def test_same_page_conflicting_duplicates_never_sum_or_select_arbitrarily(azure_payloads, field, value):
    _, payload = azure_payloads
    duplicate = deepcopy(payload["value"][1])
    duplicate[field] = value
    payload["value"].append(duplicate)
    with pytest.raises(QuotaUnavailable):
        snapshot(Mock(return_value=payload))


@pytest.mark.parametrize("next_link", [
    True, [], {}, 12, " ",
    "https://attacker.example" + NEXT,
    "https://management.azure.com.attacker.example" + NEXT,
    "https://user@management.azure.com" + NEXT,
    "https://management.azure.com:444" + NEXT,
    "http://management.azure.com" + NEXT,
    NEXT.replace(SUBSCRIPTION, "another-subscription"),
    NEXT.replace(LOCATION, "another-region"),
    NEXT.replace("/usages", "/accounts"),
    NEXT.replace("2024-10-01", "2020-01-01"),
    NEXT + "&api-version=2020-01-01",
    NEXT + "#fragment", NEXT + "\n",
])
def test_rejects_unsafe_or_malformed_paging_without_returning_partial_quota(azure_payloads, next_link):
    _, payload = azure_payloads
    reader = Mock(return_value={**payload, "nextLink": next_link})
    with pytest.raises(QuotaUnavailable):
        snapshot(reader)
    reader.assert_called_once()


def test_cyclic_paging_is_bounded_and_does_not_return_partial_quota(azure_payloads):
    _, payload = azure_payloads
    reader = Mock(return_value={**payload, "nextLink": URL})
    with pytest.raises(QuotaUnavailable):
        snapshot(reader)
    reader.assert_called_once()


def test_page_and_row_limits_do_not_return_partial_quota(azure_payloads, monkeypatch):
    _, payload = azure_payloads
    monkeypatch.setattr(model_quota, "MAX_PAGES", 1)
    reader = Mock(return_value={**payload, "nextLink": NEXT})
    with pytest.raises(QuotaUnavailable):
        snapshot(reader)
    reader.assert_called_once()
    monkeypatch.setattr(model_quota, "MAX_ROWS", 1)
    with pytest.raises(QuotaUnavailable):
        snapshot(Mock(return_value=payload))


def test_elapsed_budget_stops_before_starting_another_request(azure_payloads, monkeypatch):
    _, payload = azure_payloads
    monkeypatch.setattr(model_quota, "monotonic", Mock(side_effect=[0, 0, 61]))
    reader = Mock(return_value={**payload, "nextLink": NEXT})
    with pytest.raises(QuotaUnavailable):
        snapshot(reader)
    reader.assert_called_once()


def test_error_on_later_page_never_returns_stale_partial_success(azure_payloads):
    _, payload = azure_payloads
    reader = Mock(side_effect=[{**payload, "nextLink": NEXT}, DiscoveryError("provider failure")])
    with pytest.raises(DiscoveryError):
        snapshot(reader)


def test_subscription_and_region_are_url_encoded_but_kept_in_cli_scope(azure_payloads):
    _, payload = azure_payloads
    reader = Mock(return_value=payload)
    quota = read_model_quota(reader, "sub/ ?#", "region/?#%", USAGE_NAME)
    assert quota.remaining == 10
    command = reader.call_args.args[0]
    assert command[5] == "sub/ ?#"
    assert command[7] == (
        "/subscriptions/sub%2F%20%3F%23/providers/Microsoft.CognitiveServices/"
        "locations/region%2F%3F%23%25/usages?api-version=2024-10-01"
    )


@pytest.mark.parametrize("returncode,stdout", [(1, "{}"), (0, "not-json")])
def test_quota_cli_errors_are_sanitized(monkeypatch, returncode, stdout):
    discovery = AzureCliDiscovery()
    model = ModelChoice("example-model", "1", "OpenAI", "GlobalStandard", usage_name=USAGE_NAME)
    monkeypatch.setattr("azure_bing_assistant.wizard.azure_cli_invocation", lambda args: (list(args), {}))
    monkeypatch.setattr("azure_bing_assistant.wizard.subprocess.run", Mock(
        return_value=Mock(returncode=returncode, stdout=stdout, stderr="secret-error-text"),
    ))
    with pytest.raises(DiscoveryError) as caught:
        discovery.quota(SUBSCRIPTION, LOCATION, model)
    assert "secret-error-text" not in str(caught.value)


@pytest.mark.parametrize("error", [
    OSError("secret-local-path"), subprocess.TimeoutExpired("secret-command", 60),
])
def test_quota_cli_timeout_and_os_error_are_sanitized(monkeypatch, error):
    monkeypatch.setattr("azure_bing_assistant.wizard.azure_cli_invocation", lambda args: (list(args), {}))
    monkeypatch.setattr("azure_bing_assistant.wizard.subprocess.run", Mock(side_effect=error))
    model = ModelChoice("example-model", "1", "OpenAI", "GlobalStandard", usage_name=USAGE_NAME)
    with pytest.raises(DiscoveryError) as caught:
        AzureCliDiscovery().quota(SUBSCRIPTION, LOCATION, model)
    assert "secret" not in str(caught.value)
