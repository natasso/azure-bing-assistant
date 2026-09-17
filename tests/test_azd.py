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


class RecordingAppSettingsRunner:
    def __init__(self, settings):
        self.settings = dict(settings)
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        assert command[:4] == ["az", "webapp", "config", "appsettings"]
        if command[4] == "list":
            query = command[command.index("--query") + 1]
            assert query == (
                "[?name=='CHATBOT_NAME' || name=='WEB_GROUNDING_SITES' || "
                "name=='WEB_SEARCH_PROVIDER' || name=='BING_CUSTOM_SEARCH_CONNECTION_ID' || "
                "name=='BING_CUSTOM_SEARCH_INSTANCE_NAME' || "
                "name=='KNOWLEDGE_MODE' || name=='UI_LANGUAGE' || "
                "name=='STORAGE_ACCOUNT_NAME' || name=='STORAGE_CONTAINER_NAME']."
                "{name:name,value:value}"
            )
            names = [clause.removeprefix("name=='").removesuffix("'")
                     for clause in query[2:query.index("]")].split(" || ")]
            return CommandResult(command, json.dumps([
                {"name": name, "value": self.settings[name]}
                for name in names if name in self.settings
            ]))
        assert command[4] == "set"
        updates = command[command.index("--settings") + 1:command.index("--output")]
        self.settings.update(item.split("=", 1) for item in updates)
        return CommandResult(command, "")


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


@pytest.mark.parametrize("before_storage", [
    {},
    {"STORAGE_ACCOUNT_NAME": "", "STORAGE_CONTAINER_NAME": ""},
    {"STORAGE_ACCOUNT_NAME": "oldstorage", "STORAGE_CONTAINER_NAME": "old-documents"},
    {"STORAGE_ACCOUNT_NAME": "trustedstorage", "STORAGE_CONTAINER_NAME": "old-documents"},
    {"STORAGE_ACCOUNT_NAME": "oldstorage", "STORAGE_CONTAINER_NAME": "private-documents"},
    {"STORAGE_ACCOUNT_NAME": "trustedstorage", "STORAGE_CONTAINER_NAME": "private-documents"},
])
def test_search_storage_identity_is_read_written_exactly_and_compared(before_storage):
    base = {
        "CHATBOT_NAME": "helper",
        "WEB_GROUNDING_SITES": "docs.example.org",
        "KNOWLEDGE_MODE": "searchBlob",
        "UI_LANGUAGE": "en",
    }
    storage = {
        "STORAGE_ACCOUNT_NAME": "trustedstorage",
        "STORAGE_CONTAINER_NAME": "private-documents",
    }
    unrelated = {
        "UNRELATED_SETTING": "preserved",
        "UI_WELCOME_TITLE": "Custom welcome",
        "API_KEY": "synthetic-not-for-sync",
    }
    runner = RecordingAppSettingsRunner({**base, **before_storage, **unrelated})
    sync = AppServiceSettingsSynchronizer(".", runner)

    changed = sync.synchronize("subscription", "group", "web", {
        **base, **storage, "UNRELATED_SETTING": "do-not-write", "API_KEY": "do-not-write",
    })

    expected_updates = {
        name: value for name, value in storage.items() if before_storage.get(name) != value
    }
    assert changed is bool(expected_updates)
    assert runner.settings == {**base, **storage, **unrelated}
    assert len(runner.commands) == (2 if expected_updates else 1)
    if expected_updates:
        update = runner.commands[1]
        assert update[update.index("--settings") + 1:update.index("--output")] == [
            f"{name}={value}" for name, value in expected_updates.items()
        ]
    assert sync.synchronize("subscription", "group", "web", {**base, **storage}) is False
    assert runner.commands[-1][4] == "list"


@pytest.mark.parametrize("before_storage", [
    {},
    {"STORAGE_ACCOUNT_NAME": "", "STORAGE_CONTAINER_NAME": ""},
    {"STORAGE_ACCOUNT_NAME": "oldstorage", "STORAGE_CONTAINER_NAME": "old-documents"},
])
@pytest.mark.parametrize("supplied_storage", [{}, {
    "STORAGE_ACCOUNT_NAME": "ignoredstorage", "STORAGE_CONTAINER_NAME": "ignored-documents",
}])
def test_off_storage_is_optional_absent_is_noop_and_stale_identity_is_cleared(
    before_storage, supplied_storage
):
    from app.backend.config import AppSettings

    base = {
        "FOUNDRY_PROJECT_ENDPOINT": "https://offline.services.ai.azure.com/api/projects/project",
        "CHATBOT_NAME": "helper",
        "WEB_GROUNDING_SITES": "docs.example.org",
        "KNOWLEDGE_MODE": "off",
        "UI_LANGUAGE": "it",
    }
    runner = RecordingAppSettingsRunner({**base, **before_storage})
    sync = AppServiceSettingsSynchronizer(".", runner)
    changed = sync.synchronize("subscription", "group", "web", {**base, **supplied_storage})

    assert changed is any(before_storage.values())
    assert runner.settings == {**base, **{name: "" for name in before_storage}}
    assert AppSettings.from_environment(runner.settings).document_source is None
    if not before_storage:
        assert len(runner.commands) == 1
        assert not any(name.startswith("STORAGE_") for name in runner.settings)
    assert sync.synchronize("subscription", "group", "web", base) is False


_BING_CONNECTION_ID = (
    "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/offline-rg"
    "/providers/Microsoft.CognitiveServices/accounts/offline/projects/project/connections/bing-custom"
)
_BING_SETTINGS = {
    "WEB_SEARCH_PROVIDER": "bingCustomSearch",
    "BING_CUSTOM_SEARCH_CONNECTION_ID": _BING_CONNECTION_ID,
    "BING_CUSTOM_SEARCH_INSTANCE_NAME": "approved-sites",
}
_BASE_APP_SETTINGS = {
    "FOUNDRY_PROJECT_ENDPOINT": "https://offline.services.ai.azure.com/api/projects/project",
    "CHATBOT_NAME": "helper",
    "WEB_GROUNDING_SITES": "docs.example.org",
    "KNOWLEDGE_MODE": "off",
    "UI_LANGUAGE": "en",
}


@pytest.mark.parametrize("before", [
    {},
    _BING_SETTINGS,
    {**_BING_SETTINGS, "WEB_SEARCH_PROVIDER": "filteredWebSearch"},
    {**_BING_SETTINGS, "BING_CUSTOM_SEARCH_INSTANCE_NAME": "Approved-sites"},
    {**_BING_SETTINGS, "BING_CUSTOM_SEARCH_CONNECTION_ID": _BING_CONNECTION_ID.replace("/project/", "/other/")},
    {"WEB_SEARCH_PROVIDER": "filteredWebSearch", "BING_CUSTOM_SEARCH_CONNECTION_ID": "",
     "BING_CUSTOM_SEARCH_INSTANCE_NAME": ""},
])
def test_bing_settings_roundtrip_compares_full_binding_and_excludes_secrets(before):
    from app.backend.config import AppSettings
    from azure_bing_assistant.bing_binding import BingCustomSearchBinding

    unrelated = {
        "BING_CUSTOM_SEARCH_API_KEY": "synthetic-bing-secret",
        "API_KEY": "synthetic-unrelated-secret",
        "UNRELATED_SETTING": "preserved",
    }
    runner = RecordingAppSettingsRunner({**_BASE_APP_SETTINGS, **before, **unrelated})
    sync = AppServiceSettingsSynchronizer(".", runner)
    desired = {**_BASE_APP_SETTINGS, **_BING_SETTINGS}
    supplied = {**desired, **{name: "must-not-write" for name in unrelated}}

    expected_updates = {name: value for name, value in _BING_SETTINGS.items() if before.get(name) != value}
    assert sync.synchronize("subscription", "group", "web", supplied) is bool(expected_updates)
    assert runner.settings == {**desired, **unrelated}
    assert len(runner.commands) == (2 if expected_updates else 1)
    if expected_updates:
        update = runner.commands[1]
        assert update[update.index("--settings") + 1:update.index("--output")] == [
            f"{name}={value}" for name, value in expected_updates.items()
        ]
        assert update[update.index("--output") + 1] == "none"

    runtime = AppSettings.from_environment(runner.settings)
    assert runtime.bing_custom_search == BingCustomSearchBinding(_BING_CONNECTION_ID, "approved-sites")
    assert runtime.allowed_domains == ("docs.example.org",)
    assert sync.synchronize("subscription", "group", "web", desired) is False
    assert runner.commands[-1][4] == "list"
    for command in runner.commands:
        serialized = json.dumps(command)
        assert "must-not-write" not in serialized
        for name, value in unrelated.items():
            assert name not in serialized
            assert value not in serialized


@pytest.mark.parametrize("before", [
    {},
    _BING_SETTINGS,
    {"WEB_SEARCH_PROVIDER": "filteredWebSearch"},
    {"WEB_SEARCH_PROVIDER": "filteredWebSearch", "BING_CUSTOM_SEARCH_CONNECTION_ID": "",
     "BING_CUSTOM_SEARCH_INSTANCE_NAME": ""},
])
def test_explicit_legacy_provider_clears_stale_bing_pair_and_roundtrips(before):
    from app.backend.config import AppSettings

    legacy = {
        "WEB_SEARCH_PROVIDER": "filteredWebSearch",
        "BING_CUSTOM_SEARCH_CONNECTION_ID": "",
        "BING_CUSTOM_SEARCH_INSTANCE_NAME": "",
    }
    runner = RecordingAppSettingsRunner({**_BASE_APP_SETTINGS, **before})
    sync = AppServiceSettingsSynchronizer(".", runner)
    desired = {**_BASE_APP_SETTINGS, **legacy}
    expected_updates = {
        name: value for name, value in legacy.items()
        if before.get(name, None if name == "WEB_SEARCH_PROVIDER" else "") != value
    }

    assert sync.synchronize("subscription", "group", "web", desired) is bool(expected_updates)
    assert runner.settings == {**_BASE_APP_SETTINGS, **before, **expected_updates}
    assert AppSettings.from_environment(runner.settings).bing_custom_search is None
    if expected_updates:
        update = runner.commands[1]
        assert update[update.index("--settings") + 1:update.index("--output")] == [
            f"{name}={value}" for name, value in expected_updates.items()
        ]
    assert sync.synchronize("subscription", "group", "web", desired) is False


def test_older_synchronizer_callers_do_not_remove_existing_bing_settings():
    runner = RecordingAppSettingsRunner({**_BASE_APP_SETTINGS, **_BING_SETTINGS})
    sync = AppServiceSettingsSynchronizer(".", runner)

    assert sync.synchronize("subscription", "group", "web", _BASE_APP_SETTINGS) is False
    assert runner.settings == {**_BASE_APP_SETTINGS, **_BING_SETTINGS}
    assert len(runner.commands) == 1
