from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from azure_bing_assistant.config import InstallerConfig, KnowledgeMode
from azure_bing_assistant.provision import (
    AzureArmClient, AzureProvisioner, ProvisioningError, RESUME_MESSAGES,
)


CONFIG = InstallerConfig(
    environment_name="chatbot-demo", subscription_id="subscription",
    resource_group_name="rg-demo", location="westeurope", knowledge_mode=KnowledgeMode.OFF,
    model_name="model", model_version="1", model_format="OpenAI",
    model_sku="GlobalStandard", model_capacity=1000, model_deployment_name="chat",
    chatbot_name="helper", websites=("example.org",), bing_terms_accepted=True,
    foundry_user_role_definition_id=(
        "/subscriptions/subscription/providers/Microsoft.Authorization/roleDefinitions/foundry-user"
    ),
)
GROUP = "/subscriptions/subscription/resourceGroups/rg-demo"
RESOURCE = GROUP + "/providers/Microsoft.CognitiveServices/accounts/account"
URL = (
    "https://management.azure.com/subscriptions/subscription/providers/"
    "Microsoft.Resources/deployments/chatbot-chatbot-demo?api-version=2022-09-01"
)
MARKER = "22222222-2222-4222-8222-222222222222"
PARAMETERS = {
    "environmentName": {"value": "chatbot-demo"},
    "modelCapacity": {"value": 1000},
    "provisioningConfigHash": {"value": "a" * 64},
}
TEMPLATE = {
    "parameters": {
        "provisioningConfigHash": {"type": "string"},
        "provisioningOperationId": {"type": "string"},
    },
    "resources": [],
}


def prior(state="Succeeded"):
    return {"properties": {
        "provisioningState": state,
        "parameters": {**deepcopy(PARAMETERS), "provisioningOperationId": {"value": MARKER}},
        "outputResources": [{"id": RESOURCE}],
        "outputs": {
            "SERVICE_WEB_NAME": {"value": "app-demo"},
            "FOUNDRY_PROJECT_ENDPOINT": {
                "value": "https://account.services.ai.azure.com/api/projects/project",
            },
        },
    }}


def comparison(kind="NoChange", **overrides):
    change = {
        "resourceId": RESOURCE, "changeType": kind,
        "before": {"properties": {"provisioningState": "Succeeded"}},
        **overrides,
    }
    return {"status": "Succeeded", "properties": {"changes": [change]}}


def client(*responses):
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = Mock(side_effect=list(responses))
    arm._deployment_pause = Mock()
    return arm


def inspect(arm, report=None):
    return arm.inspect_existing(CONFIG, TEMPLATE, PARAMETERS, report or Mock())


def test_fresh_install_only_reads_before_normal_incremental_provisioning():
    report = Mock()
    arm = client((404, {}, {}))
    assert inspect(arm, report) is None
    assert arm._send_json.call_args.args == ("GET", URL)
    assert arm._send_json.call_args.kwargs["accepted"] == {200, 404}
    report.assert_any_call(RESUME_MESSAGES[1])


def test_reuses_only_confirmed_success_with_live_nochange_comparison():
    result = prior()
    report = Mock()
    arm = client((200, result, {}), (200, comparison(), {}), (200, result, {}))
    assert inspect(arm, report) == result
    assert [call.args[0] for call in arm._send_json.call_args_list] == ["GET", "POST", "GET"]
    what_if = arm._send_json.call_args_list[1]
    assert "/whatIf?" in what_if.args[1]
    assert what_if.kwargs["body"]["properties"]["mode"] == "Incremental"
    report.assert_any_call(RESUME_MESSAGES[7])
    report.assert_any_call(RESUME_MESSAGES[10], resource_id=RESOURCE, state="NoChange")


@pytest.mark.parametrize("state", ["Failed", "Canceled"])
def test_partial_or_failed_deployment_is_not_accepted_as_complete(state):
    arm = client((200, prior(state), {}), (200, comparison(), {}))
    assert inspect(arm) is None


@pytest.mark.parametrize("kind", ["Create", "Modify", "Ignore", "Deploy", "Unsupported"])
def test_missing_changed_or_unresolved_resources_require_incremental_reconciliation(kind):
    report = Mock()
    arm = client((200, prior(), {}), (200, comparison(kind), {}))
    assert inspect(arm, report) is None
    report.assert_any_call(RESUME_MESSAGES[8])


@pytest.mark.parametrize("change", ["hash", "parameters", "legacy"])
def test_changed_configuration_or_legacy_deployment_cannot_skip(change):
    previous = prior()
    parameters = previous["properties"]["parameters"]
    if change == "hash":
        parameters["provisioningConfigHash"]["value"] = "b" * 64
    elif change == "parameters":
        parameters["modelCapacity"]["value"] = 1
    else:
        del parameters["provisioningConfigHash"]
    arm = client((200, previous, {}), (200, comparison(), {}))
    assert inspect(arm) is None


def test_deletion_stops_without_a_deployment_request():
    arm = client((200, prior(), {}), (200, comparison("Delete"), {}))
    with pytest.raises(ProvisioningError, match="deletion"):
        inspect(arm)
    assert all(call.args[0] != "PUT" for call in arm._send_json.call_args_list)


@pytest.mark.parametrize("recorded", [
    None, [], [{}], [{"id": RESOURCE}, {"id": GROUP + "/providers/Microsoft.Web/sites/app"}],
])
def test_nochange_must_cover_all_previously_deployed_resources(recorded):
    result = prior()
    result["properties"]["outputResources"] = recorded
    arm = client((200, result, {}), (200, comparison(), {}))
    assert inspect(arm) is None


def test_comparison_diagnostics_prevent_reuse():
    payload = comparison()
    payload["properties"]["diagnostics"] = [{"message": "PRIVATE_DETAIL"}]
    arm = client((200, prior(), {}), (200, payload, {}))
    report = Mock()
    assert inspect(arm, report) is None
    report.assert_any_call(RESUME_MESSAGES[6])
    assert "PRIVATE_DETAIL" not in str(report.call_args_list)


def test_identical_running_attempt_is_waited_not_resubmitted():
    result = prior()
    arm = client(
        (200, prior("Running"), {}), (200, result, {}),
        (200, comparison(), {}), (200, result, {}),
    )
    report = Mock()
    assert inspect(arm, report) == result
    assert [call.args[0] for call in arm._send_json.call_args_list] == ["GET", "GET", "POST", "GET"]
    report.assert_any_call(RESUME_MESSAGES[2])


def test_other_running_attempt_is_waited_then_reconciled():
    other = prior("Running")
    other["properties"]["parameters"]["modelCapacity"]["value"] = 10
    finished = deepcopy(other)
    finished["properties"]["provisioningState"] = "Succeeded"
    arm = client((200, other, {}), (200, finished, {}), (200, comparison(), {}))
    assert inspect(arm) is None
    assert arm._send_json.call_args_list[1].args[0] == "GET"


@pytest.mark.parametrize("stage", ["running", "confirming"])
def test_concurrent_revision_change_does_not_accept_outputs(stage):
    updated = prior()
    updated["properties"]["parameters"]["provisioningOperationId"]["value"] = (
        "33333333-3333-4333-8333-333333333333"
    )
    responses = (
        [(200, prior("Running"), {}), (200, updated, {})] if stage == "running"
        else [(200, prior(), {}), (200, comparison(), {}), (200, updated, {})]
    )
    with pytest.raises(ProvisioningError, match="changed during inspection"):
        inspect(client(*responses))


def test_unreadable_previous_deployment_blocks_instead_of_assuming_absence():
    arm = client(ProvisioningError("HTTP 403"))
    with pytest.raises(ProvisioningError, match="403"):
        inspect(arm)
    assert arm._send_json.call_count == 1


def test_unavailable_what_if_is_explicit_and_never_skips_provisioning():
    report = Mock()
    arm = client((200, prior(), {}), ProvisioningError("PRIVATE_PROVIDER_DETAIL"))
    assert inspect(arm, report) is None
    report.assert_any_call(RESUME_MESSAGES[6])
    assert "PRIVATE_PROVIDER_DETAIL" not in str(report.call_args_list)


@pytest.mark.parametrize("changes", [
    [], None, "invalid", [{}],
    [comparison()["properties"]["changes"][0]] * 2,
    [{"resourceId": "/subscriptions/other/resourceGroups/rg/providers/Foo/bar", "changeType": "NoChange"}],
    [{"resourceId": RESOURCE, "changeType": "NoChange", "before": None}],
    [{"resourceId": RESOURCE, "changeType": "NoChange", "before": {"properties": None}}],
    [{"resourceId": RESOURCE, "changeType": "NoChange", "before": {"properties": {"provisioningState": "Failed"}}}],
])
def test_incomplete_or_unhealthy_comparison_does_not_reuse(changes):
    payload = {"status": "Succeeded", "properties": {"changes": changes}}
    arm = client((200, prior(), {}), (200, payload, {}))
    assert inspect(arm) is None


@pytest.mark.parametrize("operation_path", [
    "providers/Microsoft.Resources/locations/westeurope/operationresults/example",
    "operationresults/opaque-2026-09-17",
])
@pytest.mark.parametrize("query", [
    "api-version=2022-09-01",
    "api-version=2022-09-01&t=opaque-time&c=opaque-context&s=opaque-signature&h=opaque-hash",
])
def test_async_what_if_polling_uses_only_same_subscription_arm_endpoint(operation_path, query):
    # ARM's subscription-level Location also carries opaque t/c/s/h values.
    poll_url = f"https://management.azure.com/subscriptions/subscription/{operation_path}?{query}"
    arm = client(
        (202, {}, {"Location": poll_url}), (202, {"status": "Running"}, {}),
        (200, comparison(), {}),
    )
    assert arm._compare_resources(URL, CONFIG, TEMPLATE, PARAMETERS)[0]["changeType"] == "NoChange"
    assert arm._send_json.call_args.args == ("GET", poll_url)


@pytest.mark.parametrize("url", [
    "https://evil.example/path",
    "https://management.azure.com/subscriptions/other/providers/Microsoft.Resources/path?api-version=1",
    "https://management.azure.com@evil.example/path",
    "http://management.azure.com/subscriptions/subscription/providers/Microsoft.Resources/path",
    "https://management.azure.com/subscriptions/subscription/providers/Microsoft.Resources/path?sig=secret",
    "https://management.azure.com/subscriptions/subscription/operationresults/../other?api-version=1",
    "https://management.azure.com/subscriptions/subscription/operationresults/%2e%2e?api-version=1",
    "https://management.azure.com/subscriptions/subscription/operationresults/id?api-version=1&api-version=2",
    "https://management.azure.com/subscriptions/subscription/operationresults/id?api-version=1\n",
])
def test_what_if_rejects_untrusted_polling_destinations(url):
    arm = client((202, {}, {"Location": url}))
    with pytest.raises(ProvisioningError, match="invalid resource comparison URL"):
        arm._compare_resources(URL, CONFIG, TEMPLATE, PARAMETERS)
    assert arm._send_json.call_count == 1


def test_what_if_is_bounded_even_if_provider_never_completes():
    url = (
        "https://management.azure.com/subscriptions/subscription/operationresults/example"
        "?api-version=2022-09-01"
    )
    arm = client(*[(202, {}, {"Location": url})] * 21)
    with pytest.raises(ProvisioningError, match="complete"):
        arm._compare_resources(URL, CONFIG, TEMPLATE, PARAMETERS)
    assert arm._send_json.call_count == 21


def test_provisioner_reuses_outputs_and_fingerprints_template_and_configuration(monkeypatch):
    arm = Mock()
    arm.__enter__ = Mock(return_value=arm)
    arm.__exit__ = Mock(return_value=None)
    arm.inspect_existing.return_value = prior()
    monkeypatch.setattr("azure_bing_assistant.provision.AzureArmClient", lambda: arm)
    monkeypatch.setattr(AzureProvisioner, "_compile_template", Mock(return_value=TEMPLATE))
    provisioner = AzureProvisioner(Path("."))
    assert provisioner.run(CONFIG)["SERVICE_WEB_NAME"] == "app-demo"
    first = arm.inspect_existing.call_args.args[2]["provisioningConfigHash"]["value"]
    provisioner.run(CONFIG)
    assert arm.inspect_existing.call_args.args[2]["provisioningConfigHash"]["value"] == first
    provisioner.run(replace(CONFIG, model_capacity=10))
    assert arm.inspect_existing.call_args.args[2]["provisioningConfigHash"]["value"] != first
    provisioner.run(replace(CONFIG, foundry_name_salt="b" * 32))
    assert arm.inspect_existing.call_args.args[2]["provisioningConfigHash"]["value"] != first
    monkeypatch.setattr(
        AzureProvisioner, "_compile_template", Mock(return_value={**TEMPLATE, "variables": {"changed": True}}),
    )
    provisioner.run(CONFIG)
    assert arm.inspect_existing.call_args.args[2]["provisioningConfigHash"]["value"] != first
    arm.deploy.assert_not_called()


def test_offline_plan_describes_resume_without_contacting_azure(monkeypatch, capsys):
    from azure_bing_assistant.cli import _plan

    forbidden = Mock(side_effect=AssertionError("offline plan must not contact Azure"))
    monkeypatch.setattr(AzureArmClient, "inspect_existing", forbidden)
    assert _plan(CONFIG) == 0
    resume = json.loads(capsys.readouterr().out)["infrastructureDeployment"]["resume"]
    assert resume["inspectPreviousDeployment"] is True
    assert resume["compareExistingResourcesWithWhatIf"] is True
    assert resume["deleteResources"] is False
    assert resume["skipApplicationDeployment"] is False
    forbidden.assert_not_called()
