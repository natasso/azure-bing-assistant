"""Offline contracts for opt-in Foundry account naming generations."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from azure_bing_assistant import cli
from azure_bing_assistant.azd import AzdError
from azure_bing_assistant.config import ConfigurationError, InstallerConfig, KnowledgeMode
from azure_bing_assistant.provision import _deployment_parameters
from azure_bing_assistant.wizard import ConsolePrompts


SALT = "1234567890abcdef1234567890abcdef"
SECOND_SALT = "abcdef1234567890abcdef1234567890"
ROLE = "/subscriptions/offline/providers/Microsoft.Authorization/roleDefinitions/offline"
CONFIG = InstallerConfig(
    environment_name="demo", location="westeurope", knowledge_mode=KnowledgeMode.OFF,
    subscription_id="offline", resource_group_name="rg-existing", create_resource_group=False,
    model_name="offline-model", model_version="1", model_format="OpenAI", model_sku="GlobalStandard",
    model_capacity=1000, model_deployment_name="chat-model", chatbot_name="helper", ui_language="en",
    websites=("example.org",), bing_terms_accepted=True, foundry_user_role_definition_id=ROLE,
)
ARGUMENTS = [
    "install", "--non-interactive", "--ui-language", "en", "--environment", "demo",
    "--subscription", "offline", "--resource-group", "rg-existing", "--no-create-resource-group",
    "--location", "westeurope", "--model-name", "offline-model", "--model-version", "1",
    "--model-format", "OpenAI", "--model-sku", "GlobalStandard", "--model-capacity", "1000",
    "--deployment-name", "chat-model", "--chatbot-name", "helper", "--websites", "example.org",
    "--accept-bing-terms", "--foundry-user-role-id", ROLE,
]


@pytest.fixture
def installation(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    state = {"demo": {}}
    events = []
    reads = Mock()
    reads.side_effect = lambda environment: dict(state[environment])
    class Runner:
        def ensure_environment(self, environment):
            events.append(("ensure", environment))
            state.setdefault(environment, {})

        def get_environment_values(self, environment):
            events.append(("read", environment))
            return reads(environment)

        def run(self, argv):
            assert argv[:3] == ["azd", "env", "set"]
            events.append(("save", argv[3], argv[4], argv[6]))
            state[argv[6]][argv[3]] = argv[4]

    runner = Runner()
    provision = Mock()
    provision.side_effect = lambda config: events.append(("arm", config.foundry_name_salt)) or {}
    deploy = Mock(side_effect=lambda _runner, config, _values, **_: SimpleNamespace(config=config))
    factory = Mock(return_value=runner)
    monkeypatch.setattr(cli, "AzdRunner", factory)
    monkeypatch.setattr(cli, "AzureProvisioner", lambda _: SimpleNamespace(run=provision))
    monkeypatch.setattr(cli, "_deploy_application", deploy)
    monkeypatch.setattr(cli.subprocess, "run", Mock(side_effect=AssertionError("No external commands")))
    random = Mock(side_effect=[SimpleNamespace(hex=SALT), SimpleNamespace(hex=SECOND_SALT)])
    monkeypatch.setattr(cli.uuid, "uuid4", random)
    return SimpleNamespace(
        state=state, events=events, random=random, provision=provision, deploy=deploy,
        reads=reads, factory=factory, runner=runner,
    )


def test_legacy_default_is_empty_and_propagates_without_exposing_salt():
    assert CONFIG.foundry_name_salt == ""
    assert _deployment_parameters(CONFIG)["foundryNameSalt"] == {"value": ""}
    assert CONFIG.azd_environment_values()["FOUNDRY_NAME_SALT"] == ""
    assert CONFIG.public_parameters()["foundryNameGenerationConfigured"] is False
    updated = replace(CONFIG, foundry_name_salt=SALT)
    assert updated.public_parameters()["foundryNameGenerationConfigured"] is True
    assert SALT not in json.dumps(updated.public_parameters())
    assert _deployment_parameters(updated)["foundryNameSalt"] == {"value": SALT}
    assert updated.azd_environment_values()["FOUNDRY_NAME_SALT"] == SALT
    assert cli._commands(updated, "provision")[0] == [
        "azd", "env", "set", "FOUNDRY_NAME_SALT", SALT,
        "--environment", "demo", "--no-prompt",
    ]


@pytest.mark.parametrize("value", [None, True, 123, [], {}, " ", "a" * 31, "a" * 33, "A" * 32, "g" * 32, SALT + "\n"])
def test_invalid_salt_is_rejected_in_config_and_environment_without_value_disclosure(value):
    message = "FOUNDRY_NAME_SALT must be empty or 32 lowercase hexadecimal characters"
    with pytest.raises(ConfigurationError, match=message):
        replace(CONFIG, foundry_name_salt=value)
    with pytest.raises(ConfigurationError, match=message):
        InstallerConfig.from_values("off", environ={"FOUNDRY_NAME_SALT": value})


@pytest.mark.parametrize("source,expected", [({}, ""), ({"FOUNDRY_NAME_SALT": ""}, ""), ({"FOUNDRY_NAME_SALT": SALT}, SALT)])
def test_from_values_reads_valid_saved_generation(source, expected):
    assert InstallerConfig.from_values("off", environ=source).foundry_name_salt == expected


def test_normal_legacy_install_never_randomizes_account_name(installation):
    assert cli.main(ARGUMENTS) == 0
    installation.random.assert_not_called()
    assert installation.provision.call_args.args[0].foundry_name_salt == ""
    assert installation.events[:2] == [("ensure", "demo"), ("read", "demo")]
    assert "FOUNDRY_NAME_SALT" not in installation.state["demo"]


@pytest.mark.parametrize("failure", ["provision", "deployment"])
def test_rotation_is_persisted_before_arm_and_reused_after_failure_and_success(installation, failure):
    if failure == "provision":
        installation.provision.side_effect = AzdError("offline failure")
    else:
        installation.deploy.side_effect = AzdError("offline failure")
    assert cli.main(ARGUMENTS + ["--new-foundry-account"]) == 2
    assert installation.state["demo"]["FOUNDRY_NAME_SALT"] == SALT
    assert installation.events[2] == ("save", "FOUNDRY_NAME_SALT", SALT, "demo")
    assert installation.provision.call_args.args[0].foundry_name_salt == SALT
    installation.random.assert_called_once()
    installation.provision.side_effect = None
    installation.provision.return_value = {}
    installation.deploy.side_effect = lambda _r, config, _v, **_: SimpleNamespace(config=config)
    for _ in range(2):
        assert cli.main(ARGUMENTS) == 0
        assert installation.provision.call_args.args[0].foundry_name_salt == SALT
    installation.random.assert_called_once()
    assert "NEW_FOUNDRY_ACCOUNT" not in installation.state["demo"]


def test_each_explicit_rotation_is_different_but_other_resources_and_settings_are_unchanged(installation):
    results = []
    for _ in range(2):
        assert cli.main(ARGUMENTS + ["--new-foundry-account"]) == 0
        results.append(installation.provision.call_args.args[0])
    first, second = results
    assert first.foundry_name_salt == SALT and second.foundry_name_salt == SECOND_SALT
    assert replace(first, foundry_name_salt=SECOND_SALT) == second
    assert first.resource_group_name == "rg-existing" and first.create_resource_group is False
    assert first.model_capacity == 1000
    assert first.websites == ("example.org",)
    assert installation.state["demo"]["FOUNDRY_NAME_SALT"] == SECOND_SALT
    assert not any("delete" in str(event) or "purge" in str(event) for event in installation.events)


def test_existing_selected_azd_generation_overrides_ambient_config(installation):
    installation.state["demo"]["FOUNDRY_NAME_SALT"] = SALT
    other = replace(CONFIG, foundry_name_salt=SECOND_SALT)
    assert cli._resolve_foundry_name_generation(installation.runner, other).foundry_name_salt == SALT
    installation.random.assert_not_called()


@pytest.mark.parametrize("value", [None, False, "uppercase" * 4, "a" * 31, SALT + " "])
@pytest.mark.parametrize("rotate", [False, True])
def test_invalid_saved_salt_fails_before_new_generation_or_any_deployment(installation, value, rotate, capsys):
    installation.state["demo"]["FOUNDRY_NAME_SALT"] = value
    assert cli.main(ARGUMENTS + (["--new-foundry-account"] if rotate else [])) == 2
    assert "FOUNDRY_NAME_SALT must be empty or 32 lowercase hexadecimal characters" in capsys.readouterr().err
    installation.random.assert_not_called()
    installation.provision.assert_not_called()
    installation.deploy.assert_not_called()
    assert installation.events == [("ensure", "demo"), ("read", "demo")]


@pytest.mark.parametrize("failure", [AzdError("PRIVATE_SAVED_VALUES"), None, Mock()])
def test_unreadable_or_non_mapping_saved_generation_never_falls_back(installation, failure, capsys):
    if isinstance(failure, BaseException):
        installation.reads.side_effect = failure
    else:
        installation.reads.side_effect = None
        installation.reads.return_value = failure
    assert cli.main(ARGUMENTS + ["--new-foundry-account"]) == 2
    captured = capsys.readouterr()
    assert "Saved Foundry name generation could not be read safely; no new Azure deployment was started." in captured.err
    assert "PRIVATE" not in captured.err
    installation.random.assert_not_called()
    installation.provision.assert_not_called()


def test_generation_read_error_keeps_explicit_cause_without_copying_provider_output(installation):
    error = AzdError("PRIVATE_PROVIDER_VALUES")
    installation.reads.side_effect = error
    with pytest.raises(ConfigurationError) as caught:
        cli._resolve_foundry_name_generation(installation.runner, CONFIG, True)
    assert caught.value.__cause__ is error
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("rotate", [False, True])
def test_dry_run_is_offline_without_uuid_or_files_and_reports_planned_rotation(installation, tmp_path, capsys, rotate):
    assert cli.main(ARGUMENTS + ["--dry-run"] + (["--new-foundry-account"] if rotate else [])) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["foundryAccountNaming"]["newGenerationAfterApproval"] is rotate
    assert result["foundryAccountNaming"]["mayRequireAdditionalQuotaAndCost"] is rotate
    assert result["foundryAccountNaming"]["deleteExistingAccounts"] is False
    assert SALT not in json.dumps(result)
    installation.factory.assert_not_called()
    installation.random.assert_not_called()
    installation.provision.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_declined_rotation_is_explained_before_consent_without_generation_or_environment_writes(
    installation, monkeypatch, tmp_path,
):
    messages = []
    def answer(question):
        assert any("Existing Foundry accounts are not deleted" in message for message in messages)
        installation.factory.assert_not_called()
        installation.random.assert_not_called()
        return "no"
    monkeypatch.setattr(cli, "run_wizard", lambda *_a, **_k: CONFIG)
    monkeypatch.setattr(cli, "AzureCliDiscovery", lambda: object())
    monkeypatch.setattr(cli, "ConsolePrompts", lambda **_: ConsolePrompts(answer, messages.append, "en"))
    assert cli.main(["install", "--ui-language", "en", "--new-foundry-account"]) == 1
    installation.factory.assert_not_called()
    installation.random.assert_not_called()
    installation.provision.assert_not_called()
    assert not (tmp_path / ".azure").exists()


def test_salt_save_failure_stops_before_any_arm_deployment(installation):
    installation.runner.run = Mock(side_effect=AzdError("offline save failure"))
    assert cli.main(ARGUMENTS + ["--new-foundry-account"]) == 2
    installation.provision.assert_not_called()
    installation.deploy.assert_not_called()
    assert "FOUNDRY_NAME_SALT" not in installation.state["demo"]


def test_failure_saving_later_settings_keeps_new_generation_for_normal_retry(installation):
    save = installation.runner.run
    def fail_after_generation(argv):
        if argv[3] == "FOUNDRY_NAME_SALT":
            return save(argv)
        raise AzdError("offline later setting failure")
    installation.runner.run = fail_after_generation
    assert cli.main(ARGUMENTS + ["--new-foundry-account"]) == 2
    assert installation.state["demo"]["FOUNDRY_NAME_SALT"] == SALT
    installation.provision.assert_not_called()
    installation.runner.run = save
    assert cli.main(ARGUMENTS) == 0
    assert installation.provision.call_args.args[0].foundry_name_salt == SALT
    installation.random.assert_called_once()


def test_actual_wizard_retains_answers_but_not_rotation_flag_or_generation(installation, monkeypatch, tmp_path):
    from test_wizard_draft import RESUME_ANSWERS, discovery, load, prompts, seed
    seed(tmp_path)
    monkeypatch.setattr(cli, "AzureCliDiscovery", discovery)
    monkeypatch.setattr(cli, "ConsolePrompts", lambda **_: prompts(RESUME_ANSWERS + ["yes"])[0])
    installation.provision.side_effect = AzdError("offline provision failure")
    assert cli.main(["install", "--ui-language", "en", "--new-foundry-account"]) == 2
    assert installation.state["chatbot-dev"]["FOUNDRY_NAME_SALT"] == SALT
    draft = load(tmp_path)
    assert draft.get("capacity") == 7 and draft.get("environment_name") == "chatbot-dev"
    saved = draft.path.read_text(encoding="utf-8")
    assert SALT not in saved and "new_foundry_account" not in saved and "bing_terms_accepted" not in saved
    installation.provision.side_effect = None
    installation.provision.return_value = {}
    assert cli.main(["install", "--ui-language", "en"]) == 0
    installation.random.assert_called_once()
    assert installation.provision.call_args.args[0].foundry_name_salt == SALT
    assert load(tmp_path).get("capacity") == 7


def test_generation_is_scoped_to_selected_environment(installation):
    installation.state["other"] = {"FOUNDRY_NAME_SALT": SECOND_SALT}
    assert cli.main(ARGUMENTS + ["--new-foundry-account"]) == 0
    assert installation.state["other"] == {"FOUNDRY_NAME_SALT": SECOND_SALT}
    assert installation.state["demo"]["FOUNDRY_NAME_SALT"] == SALT


def test_bicep_salt_only_changes_foundry_account_hash_and_remains_deterministic():
    root = Path(__file__).resolve().parents[1]
    template = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    assert "@maxLength(32)" in template
    assert "param foundryNameSalt string = ''" in template
    assert "var token = uniqueString(subscription().id, environmentName)" in template
    assert "var foundryToken = empty(foundryNameSalt) ? token : uniqueString(subscription().id, environmentName, foundryNameSalt)" in template
    assert "var foundryName = 'ai-${environmentName}-${foundryToken}'" in template
    for declaration in (
        "var webAppName = 'app-${environmentName}-${token}'",
        "var storageName = take(replace('st${environmentName}${token}', '-', ''), 24)",
        "var searchName = 'srch-${environmentName}-${token}'",
    ):
        assert declaration in template
    assert "accountName: foundryName" in template and "foundryName: foundryName" in template
    assert "utcNow(" not in template and "newGuid(" not in template
    assert "customSubDomainName: accountName" in (root / "infra" / "modules" / "foundry.bicep").read_text(encoding="utf-8")
