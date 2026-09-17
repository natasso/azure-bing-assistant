"""Read-only current-attempt diagnostics and fail-closed deleted-name recovery."""

import copy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from azure_bing_assistant import cli
from azure_bing_assistant import provision as provisioning
from azure_bing_assistant.provision import AzureArmClient, DeploymentFailedError, ProvisioningError
from test_foundry_name_generation import ARGUMENTS, CONFIG, SALT, SECOND_SALT, installation


MARKER = "12345678-1234-1234-1234-123456789abc"
CORRELATION = "23456789-2345-2345-2345-23456789abcd"
TIMESTAMP = "2026-09-17T12:00:00.1234567+02:00"
URL = "https://management.azure.com/subscriptions/offline/providers/Microsoft.Resources/deployments/chatbot-demo?api-version=2022-09-01"
OPERATIONS = URL.replace("?api-version=", "/operations?api-version=")
ACCOUNT = "/subscriptions/offline/resourceGroups/rg-existing/providers/Microsoft.CognitiveServices/accounts/ai-demo-deleted123"
ORIGINAL_DEPLOY = cli._deploy_application


def flag(target=ACCOUNT):
    return {
        "code": "FlagMustBeSetForRestore",
        "message": f"The resource '{target}' is soft deleted. PRIVATE_PROVIDER api-key=PRIVATE_TOKEN",
    }


def payload(error=None):
    return {"properties": {
        "provisioningState": "Failed", "timestamp": TIMESTAMP, "correlationId": CORRELATION,
        "parameters": {
            "provisioningOperationId": {"value": MARKER},
            "password": {"value": "PRIVATE_PARAMETER"},
        },
        "error": error if error is not None else {
            "code": "DeploymentFailed", "details": [{"code": "InvalidTemplateDeployment"}],
        },
    }}


def operations(error=None):
    return {"value": [{"properties": {
        "provisioningState": "Failed",
        "statusMessage": {"error": {
            "code": "InvalidTemplateDeployment", "details": [error if error is not None else flag()],
        }},
    }}]}


def diagnose(monkeypatch, original=None, rows=None, current=None, *, deadline=100, expected_marker=MARKER):
    original = payload() if original is None else original
    rows = operations() if rows is None else rows
    current = copy.deepcopy(original) if current is None else current
    monkeypatch.setattr(provisioning.time, "monotonic", lambda: 0)
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = Mock(side_effect=[(200, rows, {}), (200, current, {})])
    with pytest.raises(DeploymentFailedError) as caught:
        arm._poll_deployment(URL, deadline, original, {}, expected_marker=expected_marker)
    return caught.value, arm


def verified_failure(error=None, **kwargs):
    return DeploymentFailedError(
        "Failed", URL, {"code": "DeploymentFailed", "details": [error if error is not None else flag()]},
        timestamp=TIMESTAMP, attempt_verified=True, **kwargs,
    )


def test_observed_parent_operations_expose_verified_flag_without_provider_prose(monkeypatch):
    error, arm = diagnose(monkeypatch)
    assert error.codes == ["DeploymentFailed", "InvalidTemplateDeployment", "FlagMustBeSetForRestore"]
    assert error.can_retry_with_new_foundry_account(CONFIG)
    assert error.timestamp == "2026-09-17T10:00:00.123456Z"
    text = str(error)
    assert "Failure details were read automatically from this deployment's Azure operations." in text
    assert "Azure deployment timestamp (UTC): 2026-09-17T10:00:00.123456Z" in text
    assert "PRIVATE" not in text and "api-key" not in text and ACCOUNT not in text
    assert [call.args for call in arm._send_json.call_args_list] == [
        ("GET", OPERATIONS), ("GET", URL),
    ]
    assert all(call.kwargs["retry_total"] == 0 and call.kwargs["request_timeout"] == 30 for call in arm._send_json.call_args_list)


def test_observed_quota_wording_extracts_only_bounded_numeric_fields(monkeypatch):
    quota = {
        "code": "InsufficientQuota",
        "message": (
            "This operation require 1000 new capacity in quota One Thousand Tokens Per Minute - "
            "gpt-5.6-luna - DataZoneStandard, which is bigger than the current available capacity 83. "
            "The current quota usage is 3250 and the quota limit is 3333. PRIVATE_BODY sig=PRIVATE_SAS"
        ),
    }
    error, _ = diagnose(monkeypatch, rows=operations(quota))
    assert error.numbers == [
        ("Required capacity", "1000"), ("Available capacity", "83"),
        ("Current usage", "3250"), ("Current limit", "3333"),
    ]
    assert not error.can_retry_with_new_foundry_account(CONFIG)
    assert all(word not in str(error) for word in ("PRIVATE", "gpt-5.6-luna", "DataZoneStandard", "sig="))
    other = DeploymentFailedError("Failed", URL, {**quota, "code": "OtherError"})
    assert other.numbers == []


@pytest.mark.parametrize("kind", ["marker", "correlation", "timestamp", "state"])
def test_concurrent_revision_preserves_original_failure_and_disables_rotation(monkeypatch, kind):
    current = payload()
    if kind == "marker":
        current["properties"]["parameters"]["provisioningOperationId"]["value"] = CORRELATION
    elif kind == "state":
        current["properties"]["provisioningState"] = "Succeeded"
    elif kind == "timestamp":
        current["properties"]["timestamp"] = "2026-09-17T12:00:00.1234568+02:00"
    else:
        current["properties"]["correlationId"] = MARKER
    error, arm = diagnose(monkeypatch, current=current)
    assert error.codes == ["DeploymentFailed", "InvalidTemplateDeployment"]
    assert error.details_unverified and not error.can_retry_with_new_foundry_account(CONFIG)
    assert "original error is preserved" in str(error)
    assert arm._send_json.call_count == 2


@pytest.mark.parametrize("change", ["no-metadata", "bad-marker", "bad-timestamp", "wrong-own-marker", "deadline"])
def test_unstable_metadata_or_no_budget_never_performs_diagnostic_reads(monkeypatch, change):
    original = payload()
    if change == "no-metadata":
        original["properties"] = {"provisioningState": "Failed", "error": original["properties"]["error"]}
    elif change == "bad-marker":
        original["properties"]["parameters"]["provisioningOperationId"]["value"] = "not-a-uuid"
    elif change == "bad-timestamp":
        original["properties"]["timestamp"] = "PRIVATE_timestamp"
    error, arm = diagnose(
        monkeypatch, original=original, deadline=0 if change == "deadline" else 100,
        expected_marker=CORRELATION if change == "wrong-own-marker" else MARKER,
    )
    arm._send_json.assert_not_called()
    assert not error.can_retry_with_new_foundry_account(CONFIG)
    assert "PRIVATE" not in str(error)


def test_stable_correlation_and_timestamp_can_verify_when_marker_unavailable(monkeypatch):
    original = payload()
    original["properties"]["parameters"] = {}
    error, _ = diagnose(monkeypatch, original=original, expected_marker=None)
    assert error.can_retry_with_new_foundry_account(CONFIG)


@pytest.mark.parametrize("same_correlation", [False, True])
def test_polling_markerless_terminal_state_must_match_original_attempt_correlation(monkeypatch, same_correlation):
    monkeypatch.setattr(provisioning.time, "monotonic", lambda: 0)
    initial = payload()
    initial["properties"]["provisioningState"] = "Running"
    terminal = payload()
    terminal["properties"]["parameters"] = {}
    if not same_correlation:
        terminal["properties"]["correlationId"] = MARKER
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._deployment_pause = Mock()
    arm._send_json = Mock(side_effect=[
        (200, terminal, {}), (200, operations(), {}), (200, copy.deepcopy(terminal), {}),
    ])
    with pytest.raises(DeploymentFailedError) as caught:
        arm._poll_deployment(URL, 100, initial, {}, expected_marker=MARKER)
    assert caught.value.can_retry_with_new_foundry_account(CONFIG) is same_correlation
    assert arm._send_json.call_count == (3 if same_correlation else 1)


def test_inline_flag_is_verified_against_same_attempt_without_needing_operation_errors(monkeypatch):
    original = payload({"code": "DeploymentFailed", "details": [flag()]})
    error, _ = diagnose(monkeypatch, original=original, rows={"value": []})
    assert error.can_retry_with_new_foundry_account(CONFIG)
    assert not error.operations_read


@pytest.mark.parametrize("bad_tree", [
    {"code": "FlagMustBeSetForRestore", "target": ACCOUNT, "details": "bad"},
    {"code": "FlagMustBeSetForRestore", "target": ACCOUNT, "details": [flag()] * 17},
    {"code": "FlagMustBeSetForRestore", "target": ACCOUNT, "message": "PRIVATE" * 2000},
])
def test_malformed_or_truncated_failure_trees_preserve_original_warning(monkeypatch, bad_tree):
    error, _ = diagnose(monkeypatch, rows=operations(bad_tree))
    assert error.details_unverified and not error.can_retry_with_new_foundry_account(CONFIG)
    assert error.codes == ["DeploymentFailed", "InvalidTemplateDeployment"]
    assert "PRIVATE" not in str(error)


def test_foreign_deployment_body_id_cannot_authorize_rotation(monkeypatch):
    current = payload()
    current["id"] = "/subscriptions/foreign/providers/Microsoft.Resources/deployments/chatbot-demo"
    error, _ = diagnose(monkeypatch, current=current)
    assert error.details_unverified and not error.can_retry_with_new_foundry_account(CONFIG)


def test_deploy_binds_enrichment_to_its_generated_operation_marker(monkeypatch):
    monkeypatch.setattr(provisioning.time, "monotonic", lambda: 0)
    current = payload()
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url))
        if method == "PUT":
            current["properties"]["parameters"]["provisioningOperationId"] = kwargs["body"]["properties"]["parameters"]["provisioningOperationId"]
            return 200, current, {}
        return 200, operations() if url == OPERATIONS else current, {}
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = request
    with pytest.raises(DeploymentFailedError) as caught:
        arm.deploy(
            "offline", "chatbot-demo", "westeurope",
            {"parameters": {"provisioningOperationId": {"type": "string"}}}, {},
        )
    assert caught.value.can_retry_with_new_foundry_account(CONFIG)
    assert calls == [("PUT", URL), ("GET", OPERATIONS), ("GET", URL)]


@pytest.mark.parametrize("bad_rows", [
    {"value": "malformed"}, {"value": [{}]}, {"value": [None]},
    {"value": [], "nextLink": "https://evil.example/read"},
    {"value": [{"properties": {"provisioningState": "Running"}}]},
    {"value": [{"properties": {"provisioningState": "Failed", "statusMessage": '{"error":{"code":"FlagMustBeSetForRestore"}}'}}]},
    {"value": [{"properties": {"provisioningState": "Failed", "statusMessage": []}}]},
    {"value": operations()["value"] * 65}, {"value": operations()["value"] * 17},
])
def test_malformed_truncated_or_legacy_string_operations_fail_closed(monkeypatch, bad_rows):
    error, arm = diagnose(monkeypatch, rows=bad_rows)
    assert error.details_unverified and not error.can_retry_with_new_foundry_account(CONFIG)
    assert error.codes == ["DeploymentFailed", "InvalidTemplateDeployment"]
    assert arm._send_json.call_count == 1


@pytest.mark.parametrize("failure", [ProvisioningError("PRIVATE denied HTTP403"), ValueError("PRIVATE malformed")])
def test_diagnostic_denial_or_parsing_failure_does_not_mask_original(monkeypatch, failure):
    monkeypatch.setattr(provisioning.time, "monotonic", lambda: 0)
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = Mock(side_effect=failure)
    with pytest.raises(DeploymentFailedError) as caught:
        arm._poll_deployment(URL, 100, payload(), {})
    assert caught.value.details_unverified
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("failure", [RuntimeError("unexpected programming failure"), KeyboardInterrupt()])
def test_unexpected_errors_and_cancellation_are_not_swallowed(monkeypatch, failure):
    monkeypatch.setattr(provisioning.time, "monotonic", lambda: 0)
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = Mock(side_effect=failure)
    with pytest.raises(type(failure)) as caught:
        arm._poll_deployment(URL, 100, payload(), {})
    assert caught.value is failure


@pytest.mark.parametrize("elapsed", [12, 20])
def test_shared_diagnostic_deadline_reduces_second_request_budget_and_checks_after_read(monkeypatch, elapsed):
    now = [0]
    monkeypatch.setattr(provisioning.time, "monotonic", lambda: now[0])
    calls = []
    def read(method, url, **kwargs):
        calls.append((method, url, kwargs))
        now[0] += elapsed
        return 200, operations() if url == OPERATIONS else payload(), {}
    arm = AzureArmClient.__new__(AzureArmClient)
    arm._send_json = read
    with pytest.raises(DeploymentFailedError) as caught:
        arm._poll_deployment(URL, 20, payload(), {})
    assert not caught.value.can_retry_with_new_foundry_account(CONFIG)
    assert calls[0][2]["request_timeout"] == 20
    if elapsed == 12:
        assert len(calls) == 2 and calls[1][2]["request_timeout"] == 8
    else:
        assert len(calls) == 1


@pytest.mark.parametrize("target", [
    ACCOUNT.replace("/offline/", "/foreign/"), ACCOUNT.replace("rg-existing", "rg-foreign"),
    ACCOUNT.replace("ai-demo-", "ai-other-"), ACCOUNT + "/projects/project",
    ACCOUNT.replace("Microsoft.CognitiveServices", "Microsoft.Other"),
    ACCOUNT + "?sig=PRIVATE", "https://evil.example", ACCOUNT.replace("deleted123", ""),
])
def test_rotation_requires_exact_selected_account_scope_and_expected_prefix(target):
    assert not verified_failure(flag(target)).can_retry_with_new_foundry_account(CONFIG)


@pytest.mark.parametrize("node", [
    {"code": "FlagMustBeSetForRestore"},
    {"code": "FlagMustBeSetForRestore", "target": "invalid", "message": f"'{ACCOUNT}'"},
    {"code": "FlagMustBeSetForRestore", "target": ACCOUNT, "details": "malformed"},
    {"code": "FlagMustBeSetForRestore", "target": ACCOUNT, "message": "x" * 8193},
    {"code": "FlagMustBeSetForRestore", "target": ACCOUNT, "details": [{"code": "InsufficientQuota"}]},
    {"code": "FlagMustBeSetForRestore", "target": ACCOUNT, "details": [{"code": "UnknownError"}]},
    {"code": "FlagMustBeSetForRestore", "target": ACCOUNT, "details": [{"code": "DeploymentFailed"}] * 16},
    {"code": "FlagMustBeSetForRestore", "message": f"'{ACCOUNT}' '{ACCOUNT}other'"},
])
def test_ambiguous_unknown_or_truncated_failure_never_authorizes_rotation(node):
    assert not verified_failure(node).can_retry_with_new_foundry_account(CONFIG)


def test_structured_flag_target_is_accepted_but_default_unverified_and_cancelled_are_not():
    node = {"code": "FlagMustBeSetForRestore", "target": ACCOUNT}
    assert verified_failure(node).can_retry_with_new_foundry_account(CONFIG)
    assert not DeploymentFailedError("Failed", URL, node).can_retry_with_new_foundry_account(CONFIG)
    assert not DeploymentFailedError(
        "Canceled", URL, node, attempt_verified=True,
    ).can_retry_with_new_foundry_account(CONFIG)


def test_cli_auto_rotates_once_and_persists_before_retry_then_reuses_generation(installation):
    installation.provision.side_effect = [verified_failure(), {}]
    assert cli.main(ARGUMENTS) == 0
    assert installation.provision.call_count == 2
    first, second = [call.args[0] for call in installation.provision.call_args_list]
    assert first.foundry_name_salt == "" and second.foundry_name_salt == SALT
    assert replace(first, foundry_name_salt=SALT) == second
    assert installation.state["demo"]["FOUNDRY_NAME_SALT"] == SALT
    installation.random.assert_called_once()
    installation.provision.side_effect = None
    installation.provision.return_value = {}
    assert cli.main(ARGUMENTS) == 0
    assert installation.provision.call_args.args[0].foundry_name_salt == SALT
    installation.random.assert_called_once()


@pytest.mark.parametrize("failure,arguments", [
    (verified_failure(), ["--no-auto-new-foundry-account"]),
    (verified_failure({"code": "InsufficientQuota"}), []),
    (verified_failure(flag(ACCOUNT.replace("rg-existing", "other"))), []),
    (DeploymentFailedError("Failed", URL, flag()), []),
    (DeploymentFailedError("Canceled", URL, flag(), attempt_verified=True), []),
])
def test_cli_does_not_rotate_for_optout_or_noneligible_failure(installation, failure, arguments):
    installation.provision.side_effect = failure
    assert cli.main(ARGUMENTS + arguments) == 2
    installation.random.assert_not_called()
    assert installation.provision.call_count == 1


@pytest.mark.parametrize("explicit", [False, True])
def test_cli_never_recurses_after_second_failure_even_with_explicit_generation(installation, explicit):
    installation.provision.side_effect = [verified_failure(), verified_failure()]
    assert cli.main(ARGUMENTS + (["--new-foundry-account"] if explicit else [])) == 2
    assert installation.provision.call_count == 2
    assert installation.random.call_count == (2 if explicit else 1)
    assert installation.state["demo"]["FOUNDRY_NAME_SALT"] == (SECOND_SALT if explicit else SALT)


def test_cli_failed_salt_save_never_starts_second_arm_attempt(installation):
    original = installation.runner.run
    def save(argv):
        if argv[3] == "FOUNDRY_NAME_SALT":
            raise cli.AzdError("offline saving error")
        return original(argv)
    installation.runner.run = save
    installation.provision.side_effect = verified_failure()
    assert cli.main(ARGUMENTS) == 2
    assert installation.provision.call_count == 1
    assert "FOUNDRY_NAME_SALT" not in installation.state["demo"]


@pytest.mark.parametrize("enabled", [False, True])
def test_auto_intent_dry_run_is_offline_without_uuid_or_environment_writes(installation, capsys, enabled):
    import json
    assert cli.main(ARGUMENTS + ["--dry-run"] + ([] if enabled else ["--no-auto-new-foundry-account"])) == 0
    result = json.loads(capsys.readouterr().out)["foundryAccountNaming"]
    assert result["automaticDeletedAccountRetry"] is enabled
    assert result["maxAutomaticRetries"] == (1 if enabled else 0)
    installation.factory.assert_not_called()
    installation.random.assert_not_called()


def test_declined_interactive_auto_retry_discloses_policy_without_writes(installation, monkeypatch):
    from azure_bing_assistant.wizard import ConsolePrompts
    output = []
    def answer(_):
        assert any("No existing account is restored, deleted or purged" in line for line in output)
        installation.random.assert_not_called()
        return "no"
    monkeypatch.setattr(cli, "run_wizard", lambda *_a, **_k: CONFIG)
    monkeypatch.setattr(cli, "AzureCliDiscovery", lambda: object())
    monkeypatch.setattr(cli, "ConsolePrompts", lambda **_: ConsolePrompts(answer, output.append, "en"))
    assert cli.main(["install", "--ui-language", "en"]) == 1
    installation.factory.assert_not_called()
    installation.random.assert_not_called()


def test_successful_auto_recovery_keeps_five_phases_and_persists_before_retry(
    installation, monkeypatch, capsys,
):
    outputs = {
        "SERVICE_WEB_NAME": "app-demo-retained",
        "FOUNDRY_PROJECT_ENDPOINT": "https://ai-demo-fresh.services.ai.azure.com/api/projects/project",
    }
    attempts = []
    def provision(config):
        attempts.append(config)
        if len(attempts) == 1:
            raise verified_failure()
        assert installation.state["demo"]["FOUNDRY_NAME_SALT"] == config.foundry_name_salt == SALT
        return outputs
    installation.provision.side_effect = provision
    save = installation.runner.run
    def run(argv):
        if argv[:3] == ["azd", "deploy", "web"]:
            installation.events.append(("package",))
            return
        return save(argv)
    installation.runner.run = run
    monkeypatch.setattr(cli, "_deploy_application", ORIGINAL_DEPLOY)
    monkeypatch.setattr(cli, "_configure_post_deploy", Mock())
    monkeypatch.setattr(cli, "_sync_app_service_settings", Mock(return_value=True))
    assert cli.main(ARGUMENTS) == 0
    stderr = capsys.readouterr().err
    for number in range(1, 6):
        assert stderr.count(f"Phase {number}/5") == 2
    assert "failed" not in stderr
    assert "retrying infrastructure once" in stderr
    assert installation.events[-1] == ("package",)
