import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from azure_bing_assistant.config import InstallerConfig, KnowledgeMode
from azure_bing_assistant.provision import (
    AzureArmClient,
    AzureProvisioner,
    ProvisioningError,
    _canonical_deployment_outputs,
    _deployment_parameters,
    provision_argv,
    DeploymentFailedError,
)


@pytest.mark.parametrize("language", ["it", "en"])
def test_failed_payload_preserves_safe_codes_and_exact_diagnostics_without_calls(language):
    current = "/subscriptions/example-sub/providers/Microsoft.Resources/deployments/chatbot-demo"
    nested = "/subscriptions/example-sub/resourceGroups/rg-demo/providers/Microsoft.Resources/deployments/foundry"
    payload = {"properties": {
        "provisioningState": "Failed",
        "parameters": {"password": {"value": "PARAMETER_SECRET"}},
        "error": {
            "code": "DeploymentFailed",
            "message": "Authorization: Bearer BEARER_SECRET",
            "headers": {"api-key": "HEADER_SECRET"},
            "details": [{
                "code": "ResourceDeploymentFailure", "target": nested,
                "message": f"The deployment '{nested}' failed. https://example.org/?sig=SAS_SECRET",
                "details": [{
                    "code": "InsufficientQuota",
                    "message": "Tokens Per Minute quota: operation requires 1000 new capacity; current usage 7; current limit 80. api-key=KEY_SECRET",
                    "innererror": {"code": "CapacityLimitExceeded", "message": "USER_CONTENT"},
                }],
            }],
        },
    }}
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = Mock(side_effect=AssertionError("no extra requests"))
    with pytest.raises(DeploymentFailedError) as caught:
        arm._poll_deployment("https://management.azure.com" + current + "?api-version=example", 0, payload, {})
    text = caught.value.render(language)
    for code in ("DeploymentFailed", "ResourceDeploymentFailure", "InsufficientQuota", "CapacityLimitExceeded"):
        assert code in text
    assert "1000" in text and "80" in text
    assert "az deployment operation sub list --subscription 'example-sub' --name 'chatbot-demo' --output json" in text
    assert "az deployment operation group list --subscription 'example-sub' --resource-group 'rg-demo' --name 'foundry' --output json" in text
    assert "non è una causa confermata" in text if language == "it" else "not a confirmed root cause" in text
    for forbidden in ("PARAMETER_SECRET", "BEARER_SECRET", "HEADER_SECRET", "SAS_SECRET", "KEY_SECRET", "USER_CONTENT", "api-version"):
        assert forbidden not in text
    arm._send_json.assert_not_called()


def test_terminal_error_context_is_bounded_and_rejects_unsafe_targets():
    current = "https://management.azure.com/subscriptions/example-sub/providers/Microsoft.Resources/deployments/demo"
    error = {"code": "ResourceDeploymentFailure", "details": [
        {"code": "password=CODE_SECRET", "target": "/subscriptions/example-sub/resourceGroups/rg-demo/providers/Microsoft.Resources/deployments/demo?sig=SAS_SECRET"},
        {"code": "not a code USER_CONTENT", "target": "/subscriptions/other-sub/providers/Microsoft.Resources/deployments/other"},
        *({"code": f"Failure{index}", "message": "PRIVATE" * 10000} for index in range(1000)),
    ]}
    text = str(DeploymentFailedError("Canceled", current, error))
    assert "Canceled" in text
    assert "ResourceDeploymentFailure" in text
    assert len(text) < 2000 and text.count("az deployment operation") == 1
    assert not any(value in text for value in ("SECRET", "PRIVATE", "USER_CONTENT", "other-sub", "Failure999"))


def test_nested_deployment_id_from_existing_message_without_raw_prose():
    current = "https://management.azure.com/subscriptions/example-sub/providers/Microsoft.Resources/deployments/demo"
    nested = "/subscriptions/example-sub/resourceGroups/rg-demo/providers/Microsoft.Resources/deployments/foundry"
    error = {"code": "ResourceDeploymentFailure", "message": f"The deployment '{nested}' failed. PRIVATE"}
    text = str(DeploymentFailedError("Failed", current, error))
    assert "--resource-group 'rg-demo' --name 'foundry'" in text and "PRIVATE" not in text


@pytest.mark.parametrize("payload,expected", [
    ({"properties": {}}, "valid deployment provisioning state"),
    ({"properties": {"provisioningState": "Running"}}, "before timeout"),
])
def test_missing_state_and_timeout_do_not_invent_terminal_failure(payload, expected):
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = Mock(side_effect=AssertionError("no extra requests"))
    with pytest.raises(ProvisioningError, match=expected) as caught:
        arm._poll_deployment("https://management.azure.com/example", -1, payload, {})
    assert not isinstance(caught.value, DeploymentFailedError)
    arm._send_json.assert_not_called()


def test_cleanup_cannot_mask_primary_terminal_error():
    arm = AzureArmClient.__new__(AzureArmClient)
    arm.close = Mock(side_effect=RuntimeError("cleanup failure"))
    failure = ProvisioningError("primary error")
    with pytest.raises(ProvisioningError) as caught:
        with arm:
            raise failure
    assert caught.value is failure


def complete_config(mode=KnowledgeMode.OFF):
    return InstallerConfig(
        environment_name="chatbot-dev",
        location="westeurope",
        knowledge_mode=mode,
        subscription_id="configured-subscription",
        resource_group_name="rg-chatbot-dev",
        model_name="live-model",
        model_version="2026-01-01",
        model_format="OpenAI",
        model_sku="GlobalStandard",
        model_capacity=10,
        model_deployment_name="chat-model",
        chatbot_name="helper",
        websites=("https://docs.example.org",),
        bing_terms_accepted=True,
        foundry_user_role_definition_id=(
            "/subscriptions/configured/providers/"
            "Microsoft.Authorization/roleDefinitions/foundry-user"
        ),
        storage_blob_data_reader_role_definition_id=(
            "/subscriptions/configured/providers/"
            "Microsoft.Authorization/roleDefinitions/blob-reader"
            if mode is KnowledgeMode.SEARCH_BLOB else None
        ),
        search_index_data_reader_role_definition_id=(
            "/subscriptions/configured/providers/"
            "Microsoft.Authorization/roleDefinitions/search-reader"
            if mode is KnowledgeMode.SEARCH_BLOB else None
        ),
    )


def compiled_template():
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "parameters": {
            "provisioningOperationId": {"type": "string"},
        },
        "resources": [],
    }


def deployment_result():
    return {
        "properties": {
            "provisioningState": "Succeeded",
            "outputs": {
                "servicE_WEB_NAME": {"value": "app-example"},
                "foundrY_PROJECT_ENDPOINT": {
                    "value": "https://example.services.ai.azure.com/api/projects/project"
                },
                "binG_CONNECTION_NAME": {"value": "bing-grounding"},
            },
        }
    }


def test_provision_subprocess_only_compiles_bicep_to_stdout():
    assert provision_argv(complete_config(), Path("infra/main.bicep")) == [
        "az",
        "bicep",
        "build",
        "--file",
        str(Path("infra/main.bicep")),
        "--stdout",
    ]


def test_deployment_parameters_are_simple_nonsecret_product_parameters():
    parameters = _deployment_parameters(complete_config())
    serialized = json.dumps(parameters).lower()

    assert parameters["knowledgeMode"] == {"value": "off"}
    assert parameters["uiLanguage"] == {"value": "it"}
    assert parameters["uiProductName"] == {"value": ""}
    assert parameters["uiSuggestedQuestions"] == {"value": ""}
    assert "authClientId" not in parameters
    assert "authTenantId" not in parameters
    for forbidden in ("continuation", "signing", "lease", "provision" + "-lock", "storageaccountkey"):
        assert forbidden not in serialized


def test_provision_compiles_then_uses_single_arm_deployment(monkeypatch):
    class FakeArm:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def deploy(self, *args):
            self.calls.append(args)
            return deployment_result()

    arm = FakeArm()
    monkeypatch.setattr("azure_bing_assistant.provision.AzureArmClient", lambda: arm)
    monkeypatch.setattr(
        AzureProvisioner,
        "_compile_template",
        lambda self, config, path: compiled_template(),
    )

    outputs = AzureProvisioner(Path(".")).run(complete_config())

    assert outputs["SERVICE_WEB_NAME"] == "app-example"
    assert len(arm.calls) == 1
    assert arm.calls[0][1] == "chatbot-chatbot-dev"
    assert "continuation" not in json.dumps(arm.calls[0][-1]).lower()


@pytest.mark.parametrize(
    ("service_name", "bing_name", "foundry_name"),
    [
        ("SERVICE_WEB_NAME", "BING_CONNECTION_NAME", "FOUNDRY_PROJECT_ENDPOINT"),
        ("service_web_name", "bing_connection_name", "foundry_project_endpoint"),
        ("servicE_WEB_NAME", "binG_CONNECTION_NAME", "foundrY_PROJECT_ENDPOINT"),
        ("SeRvIcE_wEb_NaMe", "BiNg_CoNnEcTiOn_NaMe", "FoUnDrY_pRoJeCt_EnDpOiNt"),
    ],
)
def test_deployment_outputs_use_canonical_names_for_any_exact_case(
    service_name, bing_name, foundry_name
):
    result = {
        "properties": {
            "outputs": {
                service_name: {"type": "String", "value": "app-example"},
                bing_name: {"type": "String", "value": "bing-grounding"},
                foundry_name: {
                    "type": "String",
                    "value": "https://example.services.ai.azure.com/api/projects/project",
                },
                "unrelatedOutput": {"type": "String", "value": "ignored"},
            }
        }
    }

    outputs = _canonical_deployment_outputs(result)

    assert outputs == {
        "SERVICE_WEB_NAME": "app-example",
        "FOUNDRY_PROJECT_ENDPOINT": (
            "https://example.services.ai.azure.com/api/projects/project"
        ),
    }


def test_off_mode_empty_optional_outputs_remain_canonical_and_valid():
    result = deployment_result()
    result["properties"]["outputs"].update(
        {
            "searcH_ENDPOINT": {"value": ""},
            "search_index_name": {"value": ""},
            "STORAGe_ACCOUNT_NAME": {"value": ""},
        }
    )

    outputs = _canonical_deployment_outputs(result)

    assert outputs["SEARCH_ENDPOINT"] == ""
    assert outputs["SEARCH_INDEX_NAME"] == ""
    assert outputs["STORAGE_ACCOUNT_NAME"] == ""


def test_missing_required_deployment_output_fails():
    result = deployment_result()
    del result["properties"]["outputs"]["servicE_WEB_NAME"]

    with pytest.raises(ProvisioningError, match="SERVICE_WEB_NAME"):
        _canonical_deployment_outputs(result)


def test_empty_required_deployment_output_fails():
    result = deployment_result()
    result["properties"]["outputs"]["servicE_WEB_NAME"]["value"] = ""

    with pytest.raises(ProvisioningError, match="SERVICE_WEB_NAME"):
        _canonical_deployment_outputs(result)


def test_case_duplicate_deployment_outputs_fail_without_value_disclosure():
    result = deployment_result()
    result["properties"]["outputs"]["service_web_name"] = {
        "value": "sensitive-conflicting-value"
    }

    with pytest.raises(ProvisioningError, match="ambiguous") as caught:
        _canonical_deployment_outputs(result)

    assert "sensitive-conflicting-value" not in str(caught.value)
    assert "app-example" not in str(caught.value)


def test_invalid_output_type_fails_without_value_disclosure():
    result = deployment_result()
    result["properties"]["outputs"]["SERVICE_WEB_NAME"] = {
        "value": {"token": "sensitive-token-value"}
    }
    del result["properties"]["outputs"]["servicE_WEB_NAME"]

    with pytest.raises(ProvisioningError, match="invalid deployment output type") as caught:
        _canonical_deployment_outputs(result)

    assert "sensitive-token-value" not in str(caught.value)
    assert "token" not in str(caught.value).lower()


def test_arm_deployment_409_reconciles_and_retries_same_operation(monkeypatch):
    marker = "22222222-2222-4222-8222-222222222222"
    monkeypatch.setattr("azure_bing_assistant.provision.uuid.uuid4", lambda: marker)
    monkeypatch.setattr("azure_bing_assistant.provision.time.sleep", lambda _: None)
    client = AzureArmClient.__new__(AzureArmClient)
    concurrent = {
        "properties": {
            "provisioningState": "Succeeded",
            "parameters": {"provisioningOperationId": {"value": "different"}},
        }
    }
    winning = deployment_result()
    winning["properties"]["parameters"] = {
        "provisioningOperationId": {"value": marker}
    }
    client._send_json = Mock(
        side_effect=[
            (409, {}, {"Retry-After": "0"}),
            (200, concurrent, {}),
            (200, winning, {}),
        ]
    )

    assert client.deploy(
        "subscription",
        "deployment",
        "westeurope",
        compiled_template(),
        _deployment_parameters(complete_config()),
    ) is winning
    first = client._send_json.call_args_list[0].kwargs["body"]
    retry = client._send_json.call_args_list[2].kwargs["body"]
    assert first == retry


def test_bicep_keeps_search_blob_conditional_without_conversation_storage():
    root = Path(__file__).parents[1]
    main = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    webapp = (root / "infra" / "modules" / "webapp.bicep").read_text(encoding="utf-8")
    search = (root / "infra" / "modules" / "search-blob.bicep").read_text(encoding="utf-8")
    combined = (main + webapp).lower()

    assert "if (knowledgemode == 'searchblob')" in main.lower()
    assert "microsoft.storage/storageaccounts" in search.lower()
    assert "continuation" not in combined
    assert "provision" + "-lock" not in combined
    assert "storageaccounts" not in webapp.lower()


def test_bicep_keeps_https_and_managed_identity_without_managing_visitor_auth():
    root = Path(__file__).parents[1]
    main = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    webapp = (root / "infra" / "modules" / "webapp.bicep").read_text(encoding="utf-8")
    combined = (main + webapp).lower()

    assert "httpsonly: true" in webapp.lower()
    assert "type: 'systemassigned'" in webapp.lower()
    for removed in (
        "authsettingsv2",
        "authclientid",
        "authtenantid",
        "auth_bypass",
        "requireauthentication",
        "unauthenticatedclientaction",
    ):
        assert removed not in combined
    assert "authsettings" not in combined


def test_bicep_keeps_localized_defaults_switchable_without_frozen_text_overrides():
    root = Path(__file__).parents[1]
    main = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    webapp = (root / "infra" / "modules" / "webapp.bicep").read_text(encoding="utf-8")

    assert "param uiLanguage string = 'it'" in main
    for parameter in (
        "uiProductName",
        "uiOrganizationName",
        "uiAssistantName",
        "uiWelcomeTitle",
        "uiWelcomeSubtitle",
        "uiDisclaimer",
        "uiSuggestedQuestions",
    ):
        assert f"param {parameter} string = ''" in main
        assert f"empty({parameter}) ? []" in webapp
    assert "name: 'UI_LANGUAGE'" in webapp
