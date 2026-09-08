from unittest.mock import Mock
import json

import pytest

from azure_bing_assistant.azd import (
    AppServiceSettingsSynchronizer,
    AzdError,
    AzdRunner,
    AzureCliRunner,
    CommandResult,
    redact_argv,
)
from azure_bing_assistant.azure_cli import AzureCliResolutionError


def test_runner_uses_argv_and_disables_shell(monkeypatch):
    completed = Mock(returncode=0, stdout="ok", stderr="")
    run = Mock(return_value=completed)
    monkeypatch.setattr("azure_bing_assistant.azd.subprocess.run", run)

    result = AzdRunner(".").run(["azd", "provision", "--no-prompt"])

    assert result.stdout == "ok"
    assert run.call_args.args[0] == ["azd", "provision", "--no-prompt"]
    assert run.call_args.kwargs["shell"] is False


def test_runner_redacts_secret_from_failure(monkeypatch):
    completed = Mock(returncode=1, stdout="", stderr="token=do-not-print")
    monkeypatch.setattr(
        "azure_bing_assistant.azd.subprocess.run",
        Mock(return_value=completed),
    )

    with pytest.raises(AzdError) as error:
        AzdRunner(".").run(["azd", "env", "set", "token", "do-not-print"])

    assert "do-not-print" not in str(error.value)
    assert "<redacted>" in str(error.value)


def test_redact_argv_redacts_following_secret_value():
    assert redact_argv(["azd", "--password", "sensitive"]) == [
        "azd",
        "<redacted>",
        "<redacted>",
    ]


def test_deployment_outputs_are_read_as_json_without_shell(monkeypatch):
    completed = Mock(
        returncode=0,
        stdout=json.dumps({"BING_CONNECTION_NAME": "managed-connection"}),
        stderr="",
    )
    run = Mock(return_value=completed)
    monkeypatch.setattr("azure_bing_assistant.azd.subprocess.run", run)

    values = AzdRunner(".").get_environment_values("chatbot-dev")

    assert values == {"BING_CONNECTION_NAME": "managed-connection"}
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.args[0][:4] == ["azd", "env", "get-values", "--environment"]


def test_azure_cli_runner_uses_argv_and_disables_shell(monkeypatch):
    completed = Mock(returncode=0, stdout="[]", stderr="")
    run = Mock(return_value=completed)
    monkeypatch.setattr("azure_bing_assistant.azd.subprocess.run", run)
    monkeypatch.setattr(
        "azure_bing_assistant.azd.azure_cli_invocation",
        lambda args: (list(args), {"SAFE": "yes"}),
    )

    AzureCliRunner(".").run(["az", "webapp", "config", "appsettings", "list"])

    assert run.call_args.args[0] == [
        "az", "webapp", "config", "appsettings", "list",
    ]
    assert run.call_args.kwargs["env"] == {"SAFE": "yes"}
    assert run.call_args.kwargs["shell"] is False


def test_azure_cli_runner_reports_launcher_resolution_failure(monkeypatch):
    monkeypatch.setattr(
        "azure_bing_assistant.azd.azure_cli_invocation",
        Mock(side_effect=AzureCliResolutionError("launcher unavailable")),
    )

    with pytest.raises(AzdError, match="launcher unavailable"):
        AzureCliRunner(".").run(["az", "account", "show"])


def test_app_settings_are_exact_deduplicated_and_injection_safe():
    commands = []

    class RecordingRunner:
        def run(self, command):
            commands.append(command)
            if "list" in command:
                return CommandResult(command, json.dumps([
                    {"name": "CHATBOT_NAME", "value": "helper-old"},
                    {"name": "WEB_GROUNDING_SITES", "value": ""},
                    {"name": "KNOWLEDGE_MODE", "value": "searchBlob"},
                    {"name": "UI_LANGUAGE", "value": "it"},
                    {"name": "UNRELATED_SETTING", "value": "preserved"},
                ]))
            return CommandResult(command, "")

    sites = "https://docs.example.org/path;echo=still-data,https://example.net"
    changed = AppServiceSettingsSynchronizer(
        ".",
        RecordingRunner(),
    ).synchronize(
        "configured-subscription",
        "rg-chatbot-dev",
        "app-chatbot-dev",
        {
            "CHATBOT_NAME": "helper-new",
            "WEB_GROUNDING_SITES": sites,
            "KNOWLEDGE_MODE": "off",
            "UI_LANGUAGE": "it",
        },
    )

    assert changed is True
    update = commands[1]
    assert update[:5] == ["az", "webapp", "config", "appsettings", "set"]
    assert "CHATBOT_NAME=helper-new" in update
    assert f"WEB_GROUNDING_SITES={sites}" in update
    assert "KNOWLEDGE_MODE=off" in update
    assert all(not item.startswith("UI_LANGUAGE=") for item in update)
    assert all(not item.startswith("UNRELATED_SETTING=") for item in update)
    assert all(item != "echo" for item in update)


def test_unchanged_app_settings_skip_update():
    commands = []

    class RecordingRunner:
        def run(self, command):
            commands.append(command)
            return CommandResult(command, json.dumps([
                {"name": "CHATBOT_NAME", "value": "helper"},
                {
                    "name": "WEB_GROUNDING_SITES",
                    "value": "https://docs.example.org",
                },
                {"name": "KNOWLEDGE_MODE", "value": "off"},
                {"name": "UI_LANGUAGE", "value": "it"},
            ]))

    changed = AppServiceSettingsSynchronizer(
        ".",
        RecordingRunner(),
    ).synchronize(
        "configured-subscription",
        "rg-chatbot-dev",
        "app-chatbot-dev",
        {
            "CHATBOT_NAME": "helper",
            "WEB_GROUNDING_SITES": "https://docs.example.org",
            "KNOWLEDGE_MODE": "off",
            "UI_LANGUAGE": "it",
        },
    )

    assert changed is False
    assert len(commands) == 1


def test_failed_app_setting_update_does_not_report_or_record_new_values():
    current = {
        "CHATBOT_NAME": "helper-old",
        "WEB_GROUNDING_SITES": "https://old.example.org",
        "KNOWLEDGE_MODE": "searchBlob",
        "UI_LANGUAGE": "it",
    }

    class FailingRunner:
        def run(self, command):
            if "list" in command:
                return CommandResult(command, json.dumps([
                    {"name": name, "value": value}
                    for name, value in current.items()
                ]))
            raise AzdError("App Service rejected the update")

    with pytest.raises(AzdError, match="rejected"):
        AppServiceSettingsSynchronizer(".", FailingRunner()).synchronize(
            "configured-subscription",
            "rg-chatbot-dev",
            "app-chatbot-dev",
            {
                "CHATBOT_NAME": "helper-new",
                "WEB_GROUNDING_SITES": "https://new.example.org",
                "KNOWLEDGE_MODE": "off",
                "UI_LANGUAGE": "en",
            },
        )

    assert current == {
        "CHATBOT_NAME": "helper-old",
        "WEB_GROUNDING_SITES": "https://old.example.org",
        "KNOWLEDGE_MODE": "searchBlob",
        "UI_LANGUAGE": "it",
    }


@pytest.mark.parametrize(
    ("current_language", "desired_language", "expected_changed"),
    [
        ("it", "en", True),
        ("en", "en", False),
        (None, "it", True),
        (None, "en", True),
    ],
)
def test_ui_language_is_synchronized_without_overwriting_other_settings(
    current_language, desired_language, expected_changed
):
    commands = []

    class RecordingRunner:
        def run(self, command):
            commands.append(command)
            if "list" in command:
                rows = [
                    {"name": "CHATBOT_NAME", "value": "helper"},
                    {"name": "WEB_GROUNDING_SITES", "value": ""},
                    {"name": "KNOWLEDGE_MODE", "value": "off"},
                    {"name": "UNRELATED_SETTING", "value": "keep-me"},
                ]
                if current_language is not None:
                    rows.append({"name": "UI_LANGUAGE", "value": current_language})
                return CommandResult(command, json.dumps(rows))
            return CommandResult(command, "")

    changed = AppServiceSettingsSynchronizer(".", RecordingRunner()).synchronize(
        "configured-subscription",
        "rg-chatbot-dev",
        "app-chatbot-dev",
        {
            "CHATBOT_NAME": "helper",
            "WEB_GROUNDING_SITES": "",
            "KNOWLEDGE_MODE": "off",
            "UI_LANGUAGE": desired_language,
        },
    )

    assert changed is expected_changed
    query = commands[0][commands[0].index("--query") + 1]
    assert "name=='UI_LANGUAGE'" in query
    if expected_changed:
        update = commands[1]
        assert f"UI_LANGUAGE={desired_language}" in update
        assert all(not item.startswith("UNRELATED_SETTING=") for item in update)
        assert all(not item.startswith("CHATBOT_NAME=") for item in update)
    else:
        assert len(commands) == 1
