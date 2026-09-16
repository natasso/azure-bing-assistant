"""Safe recovery is a pure formatter, not an Azure cleanup workflow."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from azure_bing_assistant.config import InstallerConfig, KnowledgeMode
from azure_bing_assistant.recovery import format_recovery, _ps


STAGES = [
    "Input and discovery", "Saving the environment", "Provisioning Azure resources",
    "Saving confirmed deployment outputs", "Configuring Foundry and application settings",
    "Packaging and deploying the application",
]
CONFIG = InstallerConfig(
    environment_name="demo", location="westeurope", knowledge_mode=KnowledgeMode.OFF,
    subscription_id="11111111-1111-1111-1111-111111111111",
    resource_group_name="rg-existing", create_resource_group=True, ui_language="en",
    websites=("example.org",),
)
OUTPUTS = {
    "SERVICE_WEB_NAME": "app-demo-abc123",
    "FOUNDRY_PROJECT_ENDPOINT": "https://ai-demo-abc123.services.ai.azure.com/api/projects/project",
    "SEARCH_ENDPOINT": "https://srch-demo-abc123.search.windows.net",
    "STORAGE_ACCOUNT_NAME": "stdemoabc123",
}


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("error", [RuntimeError("PRIVATE_PROVIDER token=SECRET"), KeyboardInterrupt()])
def test_all_phases_are_pure_and_do_not_print_secrets_or_delete_commands(monkeypatch, stage, error):
    forbidden = Mock(side_effect=AssertionError("Formatter must have zero side effects"))
    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    result = format_recovery(CONFIG, stage, error, OUTPUTS)
    forbidden.assert_not_called()
    assert "SECRET" not in result and "PRIVATE" not in result
    assert "--reset-wizard" in result
    assert "Bing terms and final approval" in result
    assert "no recovery commands were executed; nothing was cancelled, deleted or purged" in result
    assert "az group delete" not in result and "az resource delete" not in result
    for command in result.splitlines():
        if command.startswith("az "):
            assert any(operation in command for operation in (" show ", " list ", "list-deleted"))
            assert "--subscription" in command
    if stage in STAGES[:2]:
        assert "No Azure resources were created by this attempt" in result
        assert "az " not in result
    else:
        assert "NOT deletion lists" in result and "Never delete an existing resource group" in result


@pytest.mark.parametrize("stage", STAGES[2:])
def test_read_only_diagnostics_include_current_parent_foundry_timestamps_and_inventory(stage):
    result = format_recovery(CONFIG, stage, RuntimeError("failure"), OUTPUTS)
    assert "az deployment sub show" in result and "timestamp:timestamp" in result
    assert "az deployment operation sub list" in result and "--name 'chatbot-demo'" in result
    assert "az deployment operation group list" in result and "--name 'foundry'" in result
    assert "time:properties.timestamp" in result
    assert "az resource list" in result and "--resource-group 'rg-existing'" in result
    assert "az cognitiveservices account list-deleted" in result
    assert "az webapp log deployment list" in result


@pytest.mark.parametrize("stage", STAGES)
def test_resume_only_after_confirmed_output_persistence_phase(stage):
    result = format_recovery(CONFIG, stage, RuntimeError("failure"), OUTPUTS)
    assert ("azure-bing-assistant deploy --environment 'demo'" in result) == (stage in STAGES[4:])


@pytest.mark.parametrize("outputs", [
    {}, {"SERVICE_WEB_NAME": "app-demo-abc123"},
    {"SERVICE_WEB_NAME": "foreign-app", "FOUNDRY_PROJECT_ENDPOINT": OUTPUTS["FOUNDRY_PROJECT_ENDPOINT"]},
    {"SERVICE_WEB_NAME": OUTPUTS["SERVICE_WEB_NAME"], "FOUNDRY_PROJECT_ENDPOINT": "https://ai-other-abc123.services.ai.azure.com/api/projects/project"},
    {"SERVICE_WEB_NAME": "app-demo-abc123'; Remove-Item -Recurse", "FOUNDRY_PROJECT_ENDPOINT": "https://x/?sig=SECRET"},
])
def test_unconfirmed_or_foreign_names_do_not_enable_resume_or_invent_ownership(outputs):
    result = format_recovery(CONFIG, STAGES[4], RuntimeError("failure"), outputs)
    assert "azure-bing-assistant deploy " not in result
    assert "Unknown" in result
    assert "foreign-app" not in result and "SECRET" not in result
    assert "ai-other-" not in result and "Remove-Item" not in result
    assert "create-resource-group option" in result


@pytest.mark.parametrize("error,expected", [
    ("Conflict", "wait for the active operation"),
    ("AnotherOperationInProgress", "rather than deleting"),
    ("FlagMustBeSetForRestore", "inspect and restore"),
    ("AccountIsDeleted", "never purges"),
    ("InsufficientQuota", "reduce the selected capacity"),
    ("AuthorizationFailed", "subscription tenant and project IAM"),
    ("HTTP 403", "do not broaden roles"),
])
def test_actionable_safe_guidance_by_failure_code(error, expected):
    result = format_recovery(CONFIG, STAGES[2], RuntimeError(error), {})
    assert expected in result


def test_iam_assignment_conflicts_are_not_misdiagnosed_as_active_deployments():
    from azure_bing_assistant.installer_access import ACCESS_MESSAGES, InstallerAccessError
    result = format_recovery(CONFIG, STAGES[4], InstallerAccessError(ACCESS_MESSAGES[4]), OUTPUTS)
    assert "subscription tenant and project IAM" in result
    assert "A deployment conflict was reported" not in result


def test_search_storage_deletion_warning_is_conditional_and_requires_backups():
    result = format_recovery(CONFIG, STAGES[4], RuntimeError(), OUTPUTS)
    assert "Search/Blob mode only" not in result
    assert "stdemoabc123" not in result and "srch-demo-abc123" not in result
    result = format_recovery(replace(CONFIG, knowledge_mode=KnowledgeMode.SEARCH_BLOB), STAGES[4], RuntimeError(), OUTPUTS)
    assert "stdemoabc123" in result and "srch-demo-abc123" in result
    assert "backups and explicit data-loss approval" in result
    assert "plan only if unused by every other app" in result
    assert "Agent, model and plan names require inspection" in result


def test_cleanup_guidance_requires_backups_and_project_first_without_automatic_deletion():
    from azure_bing_assistant.recovery import CLEANUP_CANDIDATES, RECOVERY_MESSAGES
    assert CLEANUP_CANDIDATES == RECOVERY_MESSAGES[13]
    result = format_recovery(CONFIG, STAGES[4], RuntimeError("CannotDeleteResource"), OUTPUTS)
    assert "separate explicit approval, backups and verified exclusive ownership" in result
    assert "Delete the dedicated Foundry project first" in result
    assert "remove the model deployment child if required, then delete the account" in result
    assert "Account deletion must not be assumed to cascade to the project" in result
    assert "az cognitiveservices account delete" not in result
    assert "az cognitiveservices account purge" not in result


def test_no_configuration_yet_is_safe():
    result = format_recovery(None, STAGES[0], RuntimeError("PRIVATE"))
    assert "PRIVATE" not in result and "az " not in result


def test_powershell_values_use_literal_single_quote_escaping():
    assert _ps("name'; danger") == "'name''; danger'"
