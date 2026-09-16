from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from azure_bing_assistant import cli
from azure_bing_assistant.provision import _canonical_deployment_outputs
from azure_bing_assistant.wizard import ConsolePrompts, ModelChoice, RegionChoice, SubscriptionChoice


def test_cli_uses_renamed_command():
    parser = cli.build_parser()

    assert parser.prog == "azure-bing-assistant"
    assert "Azure Bing Assistant" in parser.description


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("failure_phase", [None, 2, 3, 4, 5])
def test_install_progress_tracks_real_boundaries_and_keeps_stdout_json(
    monkeypatch, tmp_path, capsys, language, failure_phase,
):
    import io
    from azure_bing_assistant.install_progress import InstallProgress

    monkeypatch.chdir(tmp_path)
    stream = io.StringIO()
    displays = []
    operations = []
    values = {
        "AZURE_SUBSCRIPTION_ID": "example-sub", "AZURE_RESOURCE_GROUP": "rg-demo",
        "SERVICE_WEB_NAME": "app-demo",
        "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/demo",
        "MODEL_DEPLOYMENT_NAME": "chat-model", "KNOWLEDGE_MODE": "off",
    }

    def display(*args):
        progress = InstallProgress(*args, stream=stream)
        displays.append(progress)
        return progress

    def observe(expected, name):
        assert len(displays) == expected
        assert displays[-1].thread.is_alive()
        assert not displays[-1].stop.is_set()
        assert ("in corso" if language == "it" else "in progress") in stream.getvalue().splitlines()[-1]
        operations.append(name)
        if failure_phase == expected:
            if expected == 2:
                raise cli.DeploymentFailedError(
                    "Failed",
                    "https://management.azure.com/subscriptions/example-sub/providers/Microsoft.Resources/deployments/chatbot-demo",
                    {"code": "ResourceDeploymentFailure", "message": "api-key=PRIVATE"},
                )
            raise cli.AzdError("synthetic failure")

    class Runner:
        def ensure_environment(self, _):
            observe(1, "ensure")

        def run(self, argv):
            if argv[:3] == ["azd", "deploy", "web"]:
                observe(5, "package")
            else:
                observe(len(displays), "save")
                values[argv[3]] = argv[4]

        def get_environment_values(self, _):
            observe(3, "read confirmed")
            return values

    def provision(_config):
        observe(2, "ARM confirmed")
        return dict(values)

    monkeypatch.setattr(cli, "InstallProgress", display)
    monkeypatch.setattr(cli, "AzdRunner", lambda _: Runner())
    monkeypatch.setattr(cli, "AzureProvisioner", lambda _: SimpleNamespace(run=provision))
    monkeypatch.setattr(cli, "_configure_post_deploy", lambda _: observe(4, "Foundry"))
    monkeypatch.setattr(cli, "_sync_app_service_settings", lambda *_: observe(4, "runtime"))
    monkeypatch.setattr(cli.subprocess, "run", Mock(side_effect=AssertionError("No live commands")))
    result = cli.main([
        "install", "--non-interactive", "--ui-language", language, "--mode", "off",
        "--environment", "demo", "--subscription", "example-sub", "--resource-group", "rg-demo",
        "--location", "westeurope", "--model-name", "example-model", "--model-version", "1",
        "--model-format", "OpenAI", "--model-sku", "DataZoneStandard", "--model-capacity", "1000",
        "--deployment-name", "chat-model", "--chatbot-name", "helper", "--websites", "example.org",
        "--accept-bing-terms", "--foundry-user-role-id",
        "/subscriptions/example-sub/providers/Microsoft.Authorization/roleDefinitions/example-role",
    ])
    captured = capsys.readouterr()
    if failure_phase is None:
        assert result == 0 and json.loads(captured.out)["status"] == "succeeded"
        assert operations.index("ARM confirmed") < operations.index("read confirmed") < operations.index("Foundry") < operations.index("runtime") < operations.index("package")
        assert len(displays) == 5
    else:
        assert result == 2 and captured.out == ""
        assert len(displays) == failure_phase
        assert ("non riuscita" if language == "it" else "failed") in stream.getvalue().splitlines()[-1]
        if failure_phase == 2:
            assert "ResourceDeploymentFailure" in captured.err and "--name 'chatbot-demo'" in captured.err
            assert "PRIVATE" not in captured.err
    assert values["MODEL_CAPACITY"] == "1000"
    assert not (tmp_path / ".azure").exists()
    assert all(not progress.thread.is_alive() for progress in displays)
    text = stream.getvalue()
    assert "%" not in text and "\r" not in text and "\x1b" not in text
    assert len(text.splitlines()) == 2 * len(displays)


@pytest.fixture
def interactive_install(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    discovery = SimpleNamespace(
        subscriptions=lambda: [SubscriptionChoice("Test subscription", "test-sub", "test-tenant")],
        resource_groups=lambda _: ["rg-existing"],
        regions=lambda _: [RegionChoice("westeurope", "West Europe")],
        models=lambda *_: [ModelChoice("test-model", "1", "OpenAI", "GlobalStandard")],
        role_definition=lambda *_: "/subscriptions/test-sub/providers/Microsoft.Authorization/roleDefinitions/test",
    )
    monkeypatch.setattr(cli, "AzureCliDiscovery", lambda: discovery)
    forbidden = Mock(side_effect=AssertionError("No subprocess, network, or real writer allowed"))
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli, "_configure_post_deploy", forbidden)
    monkeypatch.setattr(cli, "_sync_app_service_settings", forbidden)
    runner_factory = Mock(side_effect=AssertionError("No azd writes before approval"))
    provisioner_factory = Mock(side_effect=AssertionError("No ARM writes before approval"))
    deploy = Mock(side_effect=AssertionError("No deploy before approval"))
    monkeypatch.setattr(cli, "AzdRunner", runner_factory)
    monkeypatch.setattr(cli, "AzureProvisioner", provisioner_factory)
    monkeypatch.setattr(cli, "_deploy_application", deploy)
    transcript = []
    approval_events = []

    def run(domain_answers, language="en", final_answers=(), explicit=True, prefix_answers=None):
        values = iter([
            *([] if explicit else ["2" if language == "en" else ""]),
            *(prefix_answers if prefix_answers is not None else [
                "1", "2", "1", "1", "", "helper", "chatbot-dev", "chat-model", "",
            ]),
            *domain_answers, *final_answers,
        ])

        def answer(question):
            runner_factory.assert_not_called()
            provisioner_factory.assert_not_called()
            deploy.assert_not_called()
            value = next(values)
            if isinstance(value, BaseException):
                raise value
            transcript.append(question + value)
            if ("Proceed with" in question or "Procedere con" in question) and value in {"y", "yes", "sì"}:
                approval_events.append("approved")
            return value

        def output(message):
            transcript.append(message)
            print(message)

        monkeypatch.setattr(cli, "ConsolePrompts", lambda **kwargs: ConsolePrompts(answer, output, **kwargs))
        return cli.main(["install", *(["--ui-language", language] if explicit else [])])

    return SimpleNamespace(
        run=run, transcript=transcript, runner=runner_factory,
        provisioner=provisioner_factory, deploy=deploy,
        forbidden=forbidden, approvals=approval_events,
    )


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("domain_answers", [
    ["example.org", "no", "no"],
    ["example.org", "no", "yes", "example.net", "yes", "no"],
    ["example.org", "no", "yes", "https://EXAMPLE.ORG./", "yes", "example.net", "yes", "no"],
])
def test_interactive_unsupported_policy_never_reaches_terms_or_writers(
    interactive_install, capsys, language, domain_answers,
):
    flow = interactive_install
    assert flow.run(domain_answers, language) == 2
    text = "\n".join(flow.transcript)
    error = capsys.readouterr().err
    assert "example.org" in error
    assert "test-sub" not in error and "test-tenant" not in error
    assert ("Installazione non riuscita" if language == "it" else "Installation failed") in error
    assert not any(label in text for label in (
        "Accept Bing", "Accettare costi", "Proceed with", "Procedere con",
        "Installation plan", "Piano di installazione",
    ))
    flow.runner.assert_not_called()
    flow.provisioner.assert_not_called()
    flow.deploy.assert_not_called()
    flow.forbidden.assert_not_called()


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("explicit", [False, True])
def test_interactive_plan_and_final_default_no_keep_selected_language(
    interactive_install, capsys, language, explicit,
):
    flow = interactive_install
    assert flow.run(["example.org", "yes", "no"], language, ["yes", "maybe", ""], explicit) == 1
    text = "\n".join(flow.transcript)
    assert "example.org" in text
    if language == "it":
        assert "Piano di installazione (nessuna modifica effettuata):" in text
        assert "Procedere con la creazione delle risorse e la distribuzione [s/N]:" in text
        assert "Installazione annullata; lo stato di Azure non è stato modificato." in text
        assert "Installation plan" not in text and "Proceed with" not in text
    else:
        assert "Installation plan (no changes yet):" in text
        assert "Proceed with provisioning and deployment [y/N]:" in text
        assert "Installation cancelled; Azure state was not changed." in text
        assert "Piano di installazione" not in text and "Procedere con" not in text
    assert ("Lingua del chatbot e dell'installer /" in text) is not explicit
    flow.runner.assert_not_called()
    flow.provisioner.assert_not_called()
    flow.deploy.assert_not_called()
    flow.forbidden.assert_not_called()
    assert not capsys.readouterr().err


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("retry", [False, True])
def test_interactive_success_writes_only_after_explicit_final_approval(
    interactive_install, monkeypatch, capsys, language, retry,
):
    flow = interactive_install
    runner = Mock()
    runner.get_environment_values.return_value = {}

    def approved_runner(*_):
        assert flow.approvals == ["approved"]
        return runner

    def approved_provision(config):
        assert flow.approvals == ["approved"]
        assert config.ui_language == language
        assert config.websites == ("example.org", "docs.example.net")
        assert config.strict_websites is True
        return {}

    flow.runner.side_effect = approved_runner
    flow.provisioner.side_effect = None
    flow.provisioner.return_value.run.side_effect = approved_provision
    flow.deploy.side_effect = lambda _runner, config, _, **_kwargs: SimpleNamespace(config=config)
    assert flow.run(
        ["https://EXAMPLE.ORG./", "yes", "yes", "docs.example.net", "yes", "no"],
        language, ["yes", "sì" if language == "it" else "yes"],
        prefix_answers=[
            "bad", "1", "2", "1", "1", "0", "-2", "wrong", "",
            "Tor Vergata", "UPPER", "helper", "bad env", "chatbot-dev",
            "bad/route", "chat-model", "maybe", "",
        ] if retry else None,
    ) == 0
    flow.provisioner.return_value.run.assert_called_once()
    flow.deploy.assert_called_once()
    runner.ensure_environment.assert_called_once_with("chatbot-dev")
    flow.forbidden.assert_not_called()
    text = capsys.readouterr().out
    assert ("Installazione completata." if language == "it" else "Installation completed.") in text
    assert json.loads(text.splitlines()[-1])["status"] == "succeeded"


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("ending", [EOFError(), KeyboardInterrupt(), StopIteration()])
def test_interactive_name_retry_cancellation_never_writes(interactive_install, language, ending):
    flow = interactive_install
    assert flow.run([], language, prefix_answers=[
        "1", "2", "1", "1", "", "Tor Vergata", ending,
    ]) == 1
    flow.runner.assert_not_called()
    flow.provisioner.assert_not_called()
    flow.deploy.assert_not_called()
    flow.forbidden.assert_not_called()


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("failure", [OSError("input unavailable"), RuntimeError("input unavailable")])
def test_input_system_failure_stops_with_localized_context(interactive_install, capsys, language, failure):
    flow = interactive_install
    assert flow.run([], language, prefix_answers=[
        "1", "2", "1", "1", "", "Tor Vergata", failure,
    ]) == 2
    error = capsys.readouterr().err
    assert ("Inserimento dati e individuazione delle risorse" if language == "it"
            else "Input and discovery") in error
    assert "input unavailable" in error
    flow.runner.assert_not_called()
    flow.provisioner.assert_not_called()
    flow.deploy.assert_not_called()
    flow.forbidden.assert_not_called()


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("ending", ["no", EOFError(), KeyboardInterrupt()])
def test_final_decline_or_cancellation_after_retries_never_writes(interactive_install, language, ending):
    flow = interactive_install
    assert flow.run(["example.org", "yes", "no"], language, ["yes", "maybe", ending],
                    prefix_answers=[
                        "1", "2", "1", "1", "", "Tor Vergata", "helper",
                        "chatbot-dev", "chat-model", "",
                    ]) == 1
    flow.runner.assert_not_called()
    flow.provisioner.assert_not_called()
    flow.deploy.assert_not_called()
    flow.forbidden.assert_not_called()


@pytest.mark.parametrize("flag, value", [
    ("--chatbot-name", "Tor Vergata"), ("--environment", "UPPER"),
    ("--deployment-name", "bad/route"), ("--resource-group", "bad group"),
    ("--model-capacity", "0"),
])
def test_noninteractive_bad_field_fails_once_without_prompts_or_writes(monkeypatch, flag, value):
    forbidden = Mock(side_effect=AssertionError("No interaction or writes allowed"))
    for name in ("ConsolePrompts", "AzureCliDiscovery", "AzdRunner", "AzureProvisioner", "_deploy_application"):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    fields = {
        "--environment": "chatbot-dev", "--location": "westeurope",
        "--chatbot-name": "helper", "--resource-group": "rg-valid",
        "--deployment-name": "chat-model", "--model-capacity": "10",
        "--websites": "example.org",
    }
    fields[flag] = value
    assert cli.main(["install", "--non-interactive", *[
        item for pair in fields.items() for item in pair
    ]]) == 2
    forbidden.assert_not_called()


@pytest.mark.parametrize("language", ["it", "en"])
def test_interactive_discovery_eof_and_terms_default_do_not_write(interactive_install, language):
    flow = interactive_install
    assert flow.run(["example.org", "yes", "no"], language, []) == 1
    assert flow.run(["example.org", "yes", "no"], language, [""]) == 2
    flow.runner.assert_not_called()
    flow.provisioner.assert_not_called()
    flow.deploy.assert_not_called()


@pytest.mark.parametrize("language", ["it", "en"])
def test_provider_error_has_localized_stage_without_translating_vendor_detail(
    interactive_install, capsys, language,
):
    flow = interactive_install
    flow.runner.side_effect = cli.AzdError("VendorDiagnostic: QuotaExceeded")
    assert flow.run(["example.org", "yes", "no"], language, ["yes", "yes"]) == 2
    error = capsys.readouterr().err
    assert "VendorDiagnostic: QuotaExceeded" in error
    assert ("Salvataggio dell'ambiente" if language == "it" else "Saving the environment") in error
    flow.provisioner.assert_not_called()
    flow.deploy.assert_not_called()


@pytest.mark.parametrize("language", ["it", "en"])
def test_install_help_uses_explicit_language(capsys, language):
    with pytest.raises(SystemExit) as caught:
        cli.main(["install", "--ui-language", language, "--help"])
    assert caught.value.code == 0
    text = capsys.readouterr().out
    if language == "it":
        assert "lingua del chatbot e dell'installer" in text
        assert "include sempre i sottodomini" in text
        assert "opzioni:" in text and "uso:" in text
        assert "show this help" not in text
    else:
        assert "chatbot and installer language" in text
        assert "always includes subdomains" in text
        assert "options:" in text and "usage:" in text


@pytest.mark.parametrize(
    ("mode", "attached"),
    [("off", False), ("searchBlob", True)],
)
def test_dry_run_is_structured_and_never_executes(monkeypatch, capsys, mode, attached):
    run = Mock(side_effect=AssertionError("subprocess execution is forbidden in dry-run"))
    cloud = Mock(side_effect=AssertionError("cloud setup is forbidden in dry-run"))
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setattr(cli, "_configure_post_deploy", cloud)

    assert cli.main(["plan", "--mode", mode, "--dry-run", "--websites", "example.org"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dryRun"] is True
    assert payload["config"]["knowledgeMode"] == mode
    assert payload["postDeploy"]["attachSearchTool"] is attached
    assert payload["userExperience"] == {
        "label": (
            "Authorized websites + documents (Azure AI Search, optional)"
            if attached
            else "Authorized websites (default)"
        ),
        "bingGroundingConfigured": True,
        "documentSearchConfigured": attached,
    }
    assert all(isinstance(command, list) for command in payload["commands"])
    run.assert_not_called()
    cloud.assert_not_called()


def test_noninteractive_install_dry_run_is_offline_and_deterministic(
    monkeypatch, capsys
):
    run = Mock(side_effect=AssertionError("offline dry-run started a subprocess"))
    discovery = Mock(side_effect=AssertionError("offline dry-run contacted Azure"))
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setattr(cli, "AzureCliDiscovery", discovery)
    monkeypatch.setattr(cli, "InstallProgress", Mock(side_effect=AssertionError("No progress on dry-run")))
    args = [
        "install",
        "--non-interactive",
        "--dry-run",
        "--mode",
        "off",
        "--environment",
        "chatbot-dev",
        "--subscription",
        "configured-subscription",
        "--resource-group",
        "rg-chatbot-dev",
        "--create-resource-group",
        "--location",
        "westeurope",
        "--model-name",
        "model-from-azure",
        "--model-version",
        "2026-01-01",
        "--model-format",
        "OpenAI",
        "--model-sku",
        "GlobalStandard",
        "--model-capacity",
        "10",
        "--deployment-name",
        "chat-model",
        "--chatbot-name",
        "helper",
        "--websites",
        "https://docs.example.org,example.net",
        "--accept-bing-terms",
        "--foundry-user-role-id",
        "/subscriptions/configured/providers/Microsoft.Authorization/roleDefinitions/foundry-user",
    ]

    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    first = json.loads(captured.out)
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    second = json.loads(captured.out)

    assert first == second
    assert first["config"]["webGrounding"] == "web_search"
    assert first["config"]["websiteEnforcement"] == "allowed_domains"
    assert first["config"]["uiLanguage"] == "it"
    configured_names = {
        command[3]
        for command in first["commands"]
        if command[:3] == ["azd", "env", "set"]
    }
    assert "UI_LANGUAGE" in configured_names
    assert not configured_names.intersection({
        "UI_PRODUCT_NAME",
        "UI_ORGANIZATION_NAME",
        "UI_ASSISTANT_NAME",
        "UI_WELCOME_TITLE",
        "UI_WELCOME_SUBTITLE",
        "UI_DISCLAIMER",
        "UI_SUGGESTED_QUESTIONS",
    })
    assert "authConfigured" not in first["config"]
    assert all(
        name not in {"AUTH_CLIENT_ID", "AUTH_TENANT_ID"}
        for command in first["commands"]
        for name in command
    )
    run.assert_not_called()
    discovery.assert_not_called()


def test_visitor_auth_flags_are_not_accepted_and_old_environment_values_are_ignored():
    parser = cli.build_parser()
    option_strings = {
        option
        for action in parser._subparsers._group_actions[0].choices["install"]._actions
        for option in action.option_strings
    }

    assert "--auth-client-id" not in option_strings
    assert "--auth-tenant-id" not in option_strings
    with pytest.raises(SystemExit):
        parser.parse_args(["install", "--auth-client-id", "obsolete-client"])
    config = cli.InstallerConfig.from_values(
        "off",
        environ={
            "AUTH_CLIENT_ID": "obsolete-client",
            "AUTH_TENANT_ID": "obsolete-tenant",
        },
    )
    assert "authConfigured" not in config.public_parameters()
    assert "AUTH_CLIENT_ID" not in config.azd_environment_values()
    assert "AUTH_TENANT_ID" not in config.azd_environment_values()


@pytest.mark.parametrize(
    ("removed_flag", "expected_error"),
    [
        ("--subscription", "subscription_id"),
        ("--model-name", "model_name"),
        ("--chatbot-name", "chatbot_name"),
        ("--foundry-user-role-id", "foundry_user_role_definition_id"),
    ],
)
def test_noninteractive_install_still_requires_service_prerequisites(
    capsys, removed_flag, expected_error
):
    arguments = [
        "install", "--non-interactive", "--dry-run", "--mode", "off",
        "--environment", "chatbot-dev", "--subscription", "subscription",
        "--resource-group", "rg-chatbot-dev", "--location", "westeurope",
        "--model-name", "model", "--model-version", "1",
        "--model-format", "OpenAI", "--model-sku", "GlobalStandard",
        "--model-capacity", "10", "--deployment-name", "chat-model",
        "--chatbot-name", "helper", "--websites", "https://docs.example.org",
        "--accept-bing-terms", "--foundry-user-role-id",
        "/subscriptions/configured/providers/Microsoft.Authorization/roleDefinitions/foundry",
    ]
    index = arguments.index(removed_flag)
    del arguments[index:index + 2]

    assert cli.main(arguments) == 2
    assert expected_error in capsys.readouterr().err


def test_doctor_returns_nonzero_for_missing_prerequisite(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "azure_cli_invocation",
        Mock(side_effect=cli.AzureCliResolutionError("not found")),
    )
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    assert cli.main(["doctor"]) == 1

    checks = json.loads(capsys.readouterr().out)["checks"]
    assert checks["azureCli"] is False
    assert checks["azureAuthenticated"] is False


def test_doctor_checks_auth_without_mutating_state(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/tools/{name}")
    command = ["az", "account", "show", "--query", "id", "--output", "tsv"]
    monkeypatch.setattr(
        cli,
        "azure_cli_invocation",
        lambda args: (list(args), {"SAFE": "yes"}),
    )
    completed = Mock(returncode=0, stdout="configured\n")
    run = Mock(return_value=completed)
    monkeypatch.setattr(cli.subprocess, "run", run)

    assert cli.main(["doctor"]) == 0
    assert run.call_args.args[0] == command
    assert run.call_args.kwargs["env"] == {"SAFE": "yes"}
    assert run.call_args.kwargs["shell"] is False


def test_invalid_identifier_is_not_silently_replaced(capsys):
    assert (
        cli.main(
            [
                "plan",
                "--mode",
                "off",
                "--environment",
                "Not Valid",
                "--dry-run",
            ]
        )
        == 2
    )
    assert "environment_name" in capsys.readouterr().err


def test_post_deploy_configures_the_runtime_agent_name(monkeypatch):
    captured = {}

    class RecordingWriter:
        def __init__(self, *args, **kwargs):
            captured["owns_credential"] = kwargs["owns_credential"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            captured["writer_closed"] = True

    class RecordingOrchestrator:
        def __init__(self, writer, agent_name):
            captured["agent_name"] = agent_name

        def configure_tools(self, **kwargs):
            captured["tools"] = kwargs

    monkeypatch.setitem(
        sys.modules,
        "azure.identity",
        SimpleNamespace(DefaultAzureCredential=lambda: object()),
    )
    monkeypatch.setattr(cli, "FoundrySdkWriter", RecordingWriter)
    monkeypatch.setattr(cli, "AgentToolOrchestrator", RecordingOrchestrator)

    config = cli.InstallerConfig(
        environment_name="chatbot-dev",
        location="westeurope",
        knowledge_mode=cli.KnowledgeMode.OFF,
        chatbot_name="generic-assistant",
        model_deployment_name="chat-model",
        websites=("https://docs.example.org",),
    )
    resolved = cli._resolve_deploy_config(
        config,
        deployment_values(),
    )
    cli._configure_post_deploy(resolved)

    assert captured["agent_name"] == "generic-assistant"
    assert captured["tools"]["allowed_domains"] == ("docs.example.org",)
    assert "bing_connection_name" not in captured["tools"]
    assert captured["owns_credential"] is True
    assert captured["writer_closed"] is True


@pytest.mark.parametrize("operation_fails", [False, True])
def test_post_deploy_closes_foundry_client_before_credential(
    monkeypatch, operation_fails
):
    events = []
    primary = RuntimeError("Foundry operation failed")

    class Credential:
        def close(self):
            events.append("credential")

    class Project:
        def close(self):
            events.append("project_client")

    class Orchestrator:
        def __init__(self, writer, agent_name):
            pass

        def configure_tools(self, **kwargs):
            if operation_fails:
                raise primary

    monkeypatch.setitem(
        sys.modules,
        "azure.identity",
        SimpleNamespace(DefaultAzureCredential=Credential),
    )
    monkeypatch.setattr(
        "azure.ai.projects.AIProjectClient",
        lambda *, endpoint, credential: Project(),
    )
    monkeypatch.setattr(cli, "AgentToolOrchestrator", Orchestrator)
    resolved = cli._resolve_deploy_config(deploy_config(), deployment_values())

    if operation_fails:
        with pytest.raises(RuntimeError) as caught:
            cli._configure_post_deploy(resolved)
        assert caught.value is primary
    else:
        cli._configure_post_deploy(resolved)

    assert events == ["project_client", "credential"]


def deploy_config(
    *,
    mode=cli.KnowledgeMode.OFF,
    chatbot_name=None,
    websites=(),
    ui_language=None,
):
    return cli.InstallerConfig(
        environment_name="chatbot-dev",
        location="westeurope",
        knowledge_mode=mode,
        chatbot_name=chatbot_name,
        model_deployment_name="chat-model",
        websites=websites,
        ui_language=ui_language,
    )


def deployment_values(**overrides):
    values = {
        "AZURE_SUBSCRIPTION_ID": "configured-subscription",
        "AZURE_RESOURCE_GROUP": "rg-chatbot-dev",
        "SERVICE_WEB_NAME": "app-chatbot-dev",
        "MODEL_DEPLOYMENT_NAME": "chat-model",
        "FOUNDRY_PROJECT_ENDPOINT": (
            "https://example.services.ai.azure.com/api/projects/project"
        ),
        "WEB_GROUNDING_SITES": "docs.example.org",
    }
    values.update(overrides)
    return values


def test_observed_arm_casing_is_persisted_with_canonical_azd_keys():
    result = {
        "properties": {
            "outputs": {
                "servicE_WEB_NAME": {"value": "app-example"},
                "binG_CONNECTION_NAME": {"value": "bing-grounding"},
                "foundrY_PROJECT_ENDPOINT": {
                    "value": "https://example.services.ai.azure.com/api/projects/project"
                },
            }
        }
    }
    outputs = _canonical_deployment_outputs(result)
    commands = []
    runner = Mock()
    runner.run.side_effect = commands.append

    cli._save_deployment_outputs(runner, "chatbot-dev", outputs)

    persisted = {command[3]: command[4] for command in commands}
    assert persisted == {
        "SERVICE_WEB_NAME": "app-example",
        "FOUNDRY_PROJECT_ENDPOINT": (
            "https://example.services.ai.azure.com/api/projects/project"
        ),
    }


def search_deployment_values(**overrides):
    values = deployment_values(
        KNOWLEDGE_MODE="searchBlob",
        SEARCH_ENDPOINT="https://chatbotsearch.search.windows.net",
        SEARCH_INDEX_NAME="documents",
        SEARCH_INDEXER_NAME="documents-indexer",
        SEARCH_DATA_SOURCE_NAME="documents-source",
        SEARCH_CONNECTION_NAME="search-connection",
        STORAGE_RESOURCE_ID=(
            "/subscriptions/configured-subscription/resourceGroups/rg-chatbot-dev/"
            "providers/Microsoft.Storage/storageAccounts/chatbotstorage"
        ),
        STORAGE_ACCOUNT_NAME="chatbotstorage",
        STORAGE_CONTAINER_NAME="documents",
    )
    values.update(overrides)
    return values


def test_standalone_deploy_parser_and_model_distinguish_omitted_mode():
    parser = cli.build_parser()

    assert parser.parse_args(["deploy"]).mode is None
    assert parser.parse_args(["deploy", "--mode", "off"]).mode == "off"
    assert cli.InstallerConfig.from_values(None, environ={}).knowledge_mode is None
    assert (
        cli.InstallerConfig.from_values(
            None, environ={"KNOWLEDGE_MODE": "off"}
        ).knowledge_mode
        is cli.KnowledgeMode.OFF
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["plan", "--dry-run"])


def test_explicit_deploy_values_override_persisted_values():
    persisted = deployment_values(**{
        "CHATBOT_NAME": "helper",
        "WEB_GROUNDING_SITES": ["https://persisted.example.org"],
    })

    resolved = cli._resolve_deploy_config(
        deploy_config(
            chatbot_name="explicit-agent",
            websites=("https://explicit.example.org",),
        ),
        persisted,
    )

    assert resolved.config.chatbot_name == "explicit-agent"
    assert resolved.config.websites == ("explicit.example.org",)
    assert persisted["CHATBOT_NAME"] == "helper"
    assert persisted["WEB_GROUNDING_SITES"] == ["https://persisted.example.org"]


@pytest.mark.parametrize("persisted", [{}, {"CHATBOT_NAME": ""}, {"CHATBOT_NAME": "  "}])
def test_absent_or_blank_persisted_agent_uses_safe_default(persisted):
    resolved = cli._resolve_deploy_config(
        deploy_config(),
        deployment_values(**persisted),
    )

    assert resolved.config.chatbot_name == "assistant"


def test_persisted_agent_overrides_default():
    resolved = cli._resolve_deploy_config(
        deploy_config(),
        deployment_values(CHATBOT_NAME="helper"),
    )

    assert resolved.config.chatbot_name == "helper"


@pytest.mark.parametrize("value", ["Not Valid", 123])
def test_malformed_persisted_agent_fails_visibly(value):
    with pytest.raises(cli.ConfigurationError, match="CHATBOT_NAME|chatbot_name"):
        cli._resolve_deploy_config(
            deploy_config(),
            deployment_values(CHATBOT_NAME=value),
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ("docs.example.org",)),
        ("docs.example.org, https://example.net/", (
            "docs.example.org",
            "example.net",
        )),
        (["docs.example.org", "https://example.net/"], (
            "docs.example.org",
            "example.net",
        )),
    ],
)
def test_persisted_allowed_websites_are_normalized(value, expected):
    persisted = deployment_values(
        **({} if value is None else {"WEB_GROUNDING_SITES": value})
    )

    resolved = cli._resolve_deploy_config(deploy_config(), persisted)

    assert resolved.config.websites == expected


@pytest.mark.parametrize(
    "value",
    [123, ["https://docs.example.org", 123], "http://docs.example.org",
     "", [], "https://example.org/department", "*.example.org"],
)
def test_malformed_persisted_allowed_websites_fail_visibly(value):
    with pytest.raises(cli.ConfigurationError, match="WEB_GROUNDING_SITES|website|domain|DNS"):
        cli._resolve_deploy_config(
            deploy_config(),
            deployment_values(WEB_GROUNDING_SITES=value),
        )


def test_explicit_standalone_values_configure_foundry_then_app_then_deploy(
    monkeypatch, capsys
):
    events = []
    persisted = deployment_values(
        CHATBOT_NAME="helper-old",
        WEB_GROUNDING_SITES="https://old.example.org",
    )

    class FakeRunner:
        def __init__(self, cwd):
            self.cwd = cwd

        def run(self, command):
            if command[:3] == ["azd", "env", "set"]:
                events.append(("persist", command[3], command[4]))
            elif command[:3] == ["azd", "deploy", "web"]:
                events.append(("deploy",))

        def get_environment_values(self, environment_name):
            assert environment_name == "chatbot-dev"
            return persisted

    monkeypatch.setenv("CHATBOT_NAME", "helper-new")
    monkeypatch.setenv(
        "WEB_GROUNDING_SITES",
        "docs.example.org,https://example.net/,docs.example.org",
    )
    monkeypatch.setattr(cli, "AzdRunner", FakeRunner)
    monkeypatch.setattr(
        cli,
        "_configure_post_deploy",
        lambda resolved: events.append(
            ("foundry", resolved.config.chatbot_name, resolved.config.websites)
        ),
    )
    monkeypatch.setattr(
        cli,
        "_sync_app_service_settings",
        lambda resolved, cwd: events.append(
            ("app", resolved.app_settings, resolved.web_app_name)
        ),
    )

    assert cli.main([
        "deploy", "--mode", "off", "--environment", "chatbot-dev",
        "--ui-language", "en",
    ]) == 0

    assert events[0] == (
        "foundry",
        "helper-new",
        ("docs.example.org", "example.net"),
    )
    assert events[1] == (
        "app",
        {
            "CHATBOT_NAME": "helper-new",
            "WEB_GROUNDING_SITES": (
                "docs.example.org,example.net"
            ),
            "KNOWLEDGE_MODE": "off",
            "UI_LANGUAGE": "en",
        },
        "app-chatbot-dev",
    )
    assert events[-1] == ("deploy",)
    assert events.index(("deploy",)) > events.index(events[1])
    assert ("persist", "CHATBOT_NAME", "helper-new") in events
    assert ("persist", "UI_LANGUAGE", "en") in events
    assert events.index(events[1]) < events.index(("persist", "UI_LANGUAGE", "en"))
    assert json.loads(capsys.readouterr().out)["status"] == "succeeded"


def test_persisted_deploy_avoids_divergent_environment_writes(monkeypatch):
    events = []
    persisted = deployment_values(
        CHATBOT_NAME="helper",
        WEB_GROUNDING_SITES="docs.example.org",
        KNOWLEDGE_MODE="off",
        UI_LANGUAGE="it",
    )

    class FakeRunner:
        def __init__(self, cwd):
            pass

        def get_environment_values(self, environment_name):
            return persisted

        def run(self, command):
            events.append(command)

    monkeypatch.delenv("CHATBOT_NAME", raising=False)
    monkeypatch.delenv("WEB_GROUNDING_SITES", raising=False)
    monkeypatch.setattr(cli, "AzdRunner", FakeRunner)
    monkeypatch.setattr(cli, "_configure_post_deploy", lambda resolved: None)
    monkeypatch.setattr(cli, "_sync_app_service_settings", lambda resolved, cwd: False)

    assert cli.main([
        "deploy", "--mode", "off", "--environment", "chatbot-dev",
    ]) == 0

    assert events == [[
        "azd", "deploy", "web", "--environment", "chatbot-dev", "--no-prompt",
    ]]


def test_foundry_failure_makes_no_app_service_change_or_package_deploy(monkeypatch):
    runner = Mock()
    monkeypatch.setattr(
        cli,
        "_configure_post_deploy",
        Mock(side_effect=RuntimeError("Foundry rejected configuration")),
    )
    app_sync = Mock()
    monkeypatch.setattr(cli, "_sync_app_service_settings", app_sync)

    with pytest.raises(RuntimeError, match="Foundry"):
        cli._deploy_application(
            runner,
            deploy_config(chatbot_name="helper"),
            deployment_values(
                CHATBOT_NAME="helper",
                WEB_GROUNDING_SITES="https://docs.example.org",
            ),
        )

    app_sync.assert_not_called()
    runner.run.assert_not_called()


def test_app_service_failure_keeps_old_setting_and_stops_before_deploy(monkeypatch):
    runner = Mock()
    current = {"CHATBOT_NAME": "helper-old"}
    monkeypatch.setattr(cli, "_configure_post_deploy", lambda resolved: None)

    def fail_before_update(resolved, cwd):
        assert resolved.app_settings["CHATBOT_NAME"] == "helper-new"
        raise cli.AzdError("update rejected")

    monkeypatch.setattr(cli, "_sync_app_service_settings", fail_before_update)

    with pytest.raises(cli.AzdError, match="application package was not deployed"):
        cli._deploy_application(
            runner,
            deploy_config(chatbot_name="helper-new"),
            deployment_values(
                CHATBOT_NAME="helper-old",
                WEB_GROUNDING_SITES="https://docs.example.org",
            ),
        )

    assert current["CHATBOT_NAME"] == "helper-old"
    runner.run.assert_not_called()


@pytest.mark.parametrize("timed_out", [False, True])
@pytest.mark.parametrize("language", ["it", "en"])
def test_package_failure_occurs_after_valid_agent_and_runtime(monkeypatch, timed_out, language):
    events = []

    class FailingRunner:
        def run(self, command):
            assert command[:3] == ["azd", "deploy", "web"]
            events.append("deploy")
            if timed_out:
                raise cli.AzdError("local wait expired") from cli.subprocess.TimeoutExpired(
                    command, 900,
                )
            raise cli.AzdError("package failed")

    monkeypatch.setattr(
        cli, "_configure_post_deploy", lambda resolved: events.append("foundry")
    )
    monkeypatch.setattr(
        cli, "_sync_app_service_settings", lambda resolved, cwd: events.append("app")
    )

    with pytest.raises(cli.AzdError, match="App Service settings are valid") as caught:
        cli._deploy_application(
            FailingRunner(),
            deploy_config(chatbot_name="helper"),
            deployment_values(
                CHATBOT_NAME="helper",
                WEB_GROUNDING_SITES="docs.example.org",
                KNOWLEDGE_MODE="off",
                UI_LANGUAGE="it",
            ),
        )

    assert events == ["foundry", "app", "deploy"]
    text = cli.InstallerMessages(language)(str(caught.value))
    assert ("non è stata confermata" if language == "it" else "was not confirmed") in text
    assert ("prima di riprovare" if language == "it" else "before retrying") in text
    assert isinstance(caught.value.__cause__, cli.AzdError)
    if timed_out:
        assert isinstance(caught.value.__cause__.__cause__, cli.subprocess.TimeoutExpired)


@pytest.mark.parametrize(
    ("configured_mode", "persisted_mode", "expected_mode", "expects_mode_write"),
    [
        (None, "searchBlob", "searchBlob", False),
        (cli.KnowledgeMode.OFF, "searchBlob", "off", True),
        (cli.KnowledgeMode.SEARCH_BLOB, "off", "searchBlob", True),
    ],
)
def test_cross_mode_transitions_use_one_effective_state_and_order(
    monkeypatch,
    configured_mode,
    persisted_mode,
    expected_mode,
    expects_mode_write,
):
    events = []
    persisted = search_deployment_values(
        KNOWLEDGE_MODE=persisted_mode,
        CHATBOT_NAME="helper",
        WEB_GROUNDING_SITES="https://docs.example.org",
    )

    class RecordingRunner:
        def run(self, command):
            if command[:3] == ["azd", "env", "set"]:
                events.append(("persist", command[3], command[4]))
            else:
                assert command[:3] == ["azd", "deploy", "web"]
                events.append(("deploy", expected_mode))

    def record_foundry(resolved):
        events.append(
            (
                "foundry",
                resolved.config.knowledge_mode.value,
                resolved.search_index_name,
                resolved.search_connection_name,
            )
        )

    def record_app(resolved, cwd):
        events.append(("app", resolved.app_settings))
        return True

    monkeypatch.setattr(cli, "_configure_post_deploy", record_foundry)
    monkeypatch.setattr(cli, "_sync_app_service_settings", record_app)

    resolved = cli._deploy_application(
        RecordingRunner(),
        deploy_config(
            mode=configured_mode,
            chatbot_name="helper",
            websites=("https://docs.example.org",),
        ),
        persisted,
    )

    assert resolved.config.knowledge_mode.value == expected_mode
    assert events[0][0:2] == ("foundry", expected_mode)
    if expected_mode == "searchBlob":
        assert events[0][2:] == ("documents", "search-connection")
    else:
        assert events[0][2:] == (None, None)
    assert events[1] == (
        "app",
        {
            "CHATBOT_NAME": "helper",
            "WEB_GROUNDING_SITES": "docs.example.org",
            "KNOWLEDGE_MODE": expected_mode,
            "UI_LANGUAGE": "it",
            **({
                "STORAGE_ACCOUNT_NAME": "chatbotstorage",
                "STORAGE_CONTAINER_NAME": "documents",
            } if expected_mode == "searchBlob" else {}),
        },
    )
    mode_writes = [
        event
        for event in events
        if event[0] == "persist" and event[1] == "KNOWLEDGE_MODE"
    ]
    assert bool(mode_writes) is expects_mode_write
    if mode_writes:
        assert mode_writes == [("persist", "KNOWLEDGE_MODE", expected_mode)]
    assert events[-1] == ("deploy", expected_mode)
    assert next(
        index for index, event in enumerate(events) if event[0] == "deploy"
    ) > max(
        index for index, event in enumerate(events) if event[0] in {"app", "persist"}
    )


def test_legacy_deploy_without_persisted_mode_safely_resolves_and_persists_off(
    monkeypatch,
):
    events = []
    values = deployment_values(
        CHATBOT_NAME="helper",
        WEB_GROUNDING_SITES="docs.example.org",
    )
    monkeypatch.setattr(cli, "_configure_post_deploy", lambda resolved: None)
    monkeypatch.setattr(cli, "_sync_app_service_settings", lambda resolved, cwd: False)

    class RecordingRunner:
        def run(self, command):
            events.append(command)

    resolved = cli._deploy_application(
        RecordingRunner(),
        deploy_config(
            mode=None,
            chatbot_name="helper",
            websites=("https://docs.example.org",),
        ),
        values,
    )

    assert resolved.config.knowledge_mode is cli.KnowledgeMode.OFF
    assert events[0][:5] == [
        "azd", "env", "set", "KNOWLEDGE_MODE", "off",
    ]
    assert events[-1][:3] == ["azd", "deploy", "web"]


def test_invalid_persisted_mode_fails_before_side_effects(monkeypatch):
    runner = Mock()
    foundry = Mock()
    app = Mock()
    monkeypatch.setattr(cli, "_configure_post_deploy", foundry)
    monkeypatch.setattr(cli, "_sync_app_service_settings", app)

    with pytest.raises(cli.ConfigurationError, match="KNOWLEDGE_MODE"):
        cli._deploy_application(
            runner,
            deploy_config(mode=None),
            deployment_values(KNOWLEDGE_MODE="invalid"),
        )

    foundry.assert_not_called()
    app.assert_not_called()
    runner.run.assert_not_called()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda values: values.pop("SEARCH_CONNECTION_NAME"),
        lambda values: values.pop("STORAGE_CONTAINER_NAME"),
        lambda values: values.update(STORAGE_CONTAINER_NAME=""),
        lambda values: values.update(STORAGE_CONTAINER_NAME="invalid/container"),
        lambda values: values.pop("STORAGE_ACCOUNT_NAME"),
        lambda values: values.update(
            STORAGE_RESOURCE_ID=(
                "/subscriptions/configured-subscription/resourceGroups/other-group/"
                "providers/Microsoft.Storage/storageAccounts/chatbotstorage"
            )
        ),
        lambda values: values.update(
            SEARCH_ENDPOINT="https://stale.example.org"
        ),
    ],
)
def test_searchblob_prerequisite_failure_has_zero_side_effects(monkeypatch, mutate):
    values = search_deployment_values(KNOWLEDGE_MODE="off")
    mutate(values)
    runner = Mock()
    foundry = Mock()
    app = Mock()
    monkeypatch.setattr(cli, "_configure_post_deploy", foundry)
    monkeypatch.setattr(cli, "_sync_app_service_settings", app)

    with pytest.raises(cli.ConfigurationError):
        cli._deploy_application(
            runner,
            deploy_config(mode=cli.KnowledgeMode.SEARCH_BLOB),
            values,
        )

    foundry.assert_not_called()
    app.assert_not_called()
    runner.run.assert_not_called()


def test_searchblob_required_keys_are_real_provision_outputs():
    root = Path(__file__).parents[1]
    bicep = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    expected = {
        "SEARCH_ENDPOINT",
        "SEARCH_INDEX_NAME",
        "SEARCH_INDEXER_NAME",
        "SEARCH_DATA_SOURCE_NAME",
        "SEARCH_CONNECTION_NAME",
        "STORAGE_RESOURCE_ID",
        "STORAGE_ACCOUNT_NAME",
        "STORAGE_CONTAINER_NAME",
    }

    assert {name for _, name in cli._SEARCH_DEPLOYMENT_FIELDS} == expected
    for name in expected:
        assert f"output {name} string" in bicep


@pytest.mark.parametrize("action", ["install", "deploy"])
def test_search_storage_reaches_backend_through_real_settings_commands_before_package(
    monkeypatch, action
):
    import httpx
    from azure.ai.projects.models import AgentDetails
    from fastapi.testclient import TestClient
    from openai import AsyncOpenAI
    from openai.types.responses import Response

    from app.backend import main as backend
    from app.backend.config import AppSettings
    from azure_bing_assistant import azd
    from azure_bing_assistant.agent import FoundryAgentAdapter, SearchDocumentSource

    values = search_deployment_values(
        CHATBOT_NAME="helper",
        UI_LANGUAGE="en",
        STORAGE_ACCOUNT_NAME="wiredstorage",
        STORAGE_CONTAINER_NAME="customer-documents",
        STORAGE_RESOURCE_ID=(
            "/subscriptions/configured-subscription/resourceGroups/rg-chatbot-dev/"
            "providers/Microsoft.Storage/storageAccounts/wiredstorage"
        ),
    )
    persisted = {} if action == "install" else dict(values)
    current = {
        "FOUNDRY_PROJECT_ENDPOINT": values["FOUNDRY_PROJECT_ENDPOINT"],
        "CHATBOT_NAME": "helper",
        "WEB_GROUNDING_SITES": "docs.example.org",
        "KNOWLEDGE_MODE": "searchBlob",
        "UI_LANGUAGE": "en",
        "UI_WELCOME_TITLE": "Custom welcome",
        "UNRELATED_SETTING": "preserved",
        "API_KEY": "synthetic-not-for-sync",
    }
    before = dict(current)
    events = []
    commands = []

    class Runner:
        def __init__(self, cwd):
            pass

        def ensure_environment(self, name):
            assert name == "chatbot-dev"

        def get_environment_values(self, name):
            assert name == "chatbot-dev"
            return dict(persisted)

        def run(self, command):
            if command[:3] == ["azd", "env", "set"]:
                persisted[command[3]] = command[4]
                events.append("persist")
            else:
                assert command[:3] == ["azd", "deploy", "web"]
                assert current["STORAGE_ACCOUNT_NAME"] == "wiredstorage"
                assert current["STORAGE_CONTAINER_NAME"] == "customer-documents"
                events.append("package")

    class Provisioner:
        def __init__(self, cwd):
            pass

        def run(self, config):
            events.append("provision")
            return dict(values)

    def run_settings_command(command, **kwargs):
        assert command[:4] == ["az", "webapp", "config", "appsettings"]
        assert kwargs["shell"] is False
        assert command[command.index("--subscription") + 1] == "configured-subscription"
        assert command[command.index("--resource-group") + 1] == "rg-chatbot-dev"
        assert command[command.index("--name") + 1] == "app-chatbot-dev"
        commands.append(command)
        if command[4] == "list":
            events.append("settings-read")
            query = command[command.index("--query") + 1]
            names = [clause.removeprefix("name=='").removesuffix("'")
                     for clause in query[2:query.index("]")].split(" || ")]
            assert set(names) == {
                "CHATBOT_NAME", "WEB_GROUNDING_SITES", "KNOWLEDGE_MODE", "UI_LANGUAGE",
                "STORAGE_ACCOUNT_NAME", "STORAGE_CONTAINER_NAME",
            }
            return Mock(returncode=0, stderr="", stdout=json.dumps([
                {"name": name, "value": current[name]} for name in names if name in current
            ]))
        assert command[4] == "set"
        events.append("settings-write")
        updates = command[command.index("--settings") + 1:command.index("--output")]
        assert updates == [
            "STORAGE_ACCOUNT_NAME=wiredstorage",
            "STORAGE_CONTAINER_NAME=customer-documents",
        ]
        current.update(item.split("=", 1) for item in updates)
        return Mock(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(cli, "AzdRunner", Runner)
    monkeypatch.setattr(cli, "AzureProvisioner", Provisioner)
    monkeypatch.setattr(cli, "_configure_post_deploy", lambda resolved: events.append("foundry"))
    monkeypatch.setattr(azd, "azure_cli_invocation", lambda args: (list(args), {}))
    monkeypatch.setattr(azd.subprocess, "run", run_settings_command)
    # Environment discovery and all CLI subprocesses are replaced, not synchronization.
    monkeypatch.setattr(cli.os, "environ", {})
    arguments = [
        action, "--mode", "searchBlob", "--environment", "chatbot-dev", "--ui-language", "en",
    ]
    if action == "install":
        role_prefix = (
            "/subscriptions/configured-subscription/providers/"
            "Microsoft.Authorization/roleDefinitions/"
        )
        arguments += [
            "--non-interactive", "--subscription", "configured-subscription",
            "--resource-group", "rg-chatbot-dev", "--location", "westeurope",
            "--model-name", "offline-model", "--model-version", "1",
            "--model-format", "OpenAI", "--model-sku", "GlobalStandard",
            "--model-capacity", "10", "--deployment-name", "chat-model",
            "--chatbot-name", "helper", "--websites", "docs.example.org", "--accept-bing-terms",
            "--foundry-user-role-id", role_prefix + "foundry-user",
            "--storage-blob-data-reader-role-id", role_prefix + "blob-reader",
            "--search-index-data-reader-role-id", role_prefix + "search-reader",
        ]

    assert cli.main(arguments) == 0
    assert len(commands) == 2
    assert events.index("foundry") < events.index("settings-read")
    assert events.index("settings-read") < events.index("settings-write") < events.index("package")
    if action == "install":
        assert events.index("provision") < events.index("foundry")
    assert current == {
        **before,
        "STORAGE_ACCOUNT_NAME": "wiredstorage",
        "STORAGE_CONTAINER_NAME": "customer-documents",
    }
    settings = AppSettings.from_environment(current)
    assert settings.document_source == SearchDocumentSource("wiredstorage", "customer-documents")

    tools = [
        {"type": "web_search", "filters": {"allowed_domains": ["docs.example.org"]}},
        {"type": "azure_ai_search", "azure_ai_search": {"indexes": [{
            "project_connection_id": "search-connection", "index_name": "documents",
        }]}},
    ]
    private_url = (
        "https://wiredstorage.blob.core.windows.net/customer-documents/handbook.pdf?sig=synthetic"
    )
    payload = {
        "id": "resp-offline", "object": "response", "created_at": 0,
        "status": "completed", "model": "offline-model", "tools": tools,
        "parallel_tool_calls": True, "tool_choice": "auto",
        "output": [
            {"type": "azure_ai_search_call", "id": "ais-offline",
             "call_id": "search-offline", "status": "completed",
             "results": [{"url": private_url, "title": "Private", "content": "Document text"}]},
            {"type": "message", "id": "msg-offline", "status": "completed", "role": "assistant",
             "content": [{"type": "output_text", "text": "Document answer",
                          "annotations": [{"type": "url_citation", "url": private_url,
                                           "title": "Private", "start_index": 0, "end_index": 8}]}]},
        ],
    }

    class Agents:
        async def get(self, *, agent_name):
            assert agent_name == "helper"
            return AgentDetails({
                "id": "helper", "object": "agent", "name": "helper",
                "versions": {"latest": {
                    "id": "helper:7", "name": "helper", "version": "7",
                    "object": "agent.version", "created_at": 0, "metadata": {},
                    "definition": {"kind": "prompt", "model": "offline-model", "tools": tools},
                }},
            })

    requests = []

    def response_transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    sdk = AsyncOpenAI(
        api_key="offline-synthetic-key", base_url="https://offline.example/openai/v1/",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(response_transport)),
        max_retries=0,
    )
    sdk_create = sdk.responses.create
    parsed = []

    async def capture_response(**kwargs):
        response = await sdk_create(**kwargs)
        assert isinstance(response, Response)
        parsed.append(response)
        return response

    sdk.responses.create = capture_response
    monkeypatch.setattr(
        backend, "FoundryAgentAdapter",
        lambda *args, **kwargs: FoundryAgentAdapter(
            *args, **kwargs, openai_client=sdk, project_client=SimpleNamespace(agents=Agents())
        ),
    )
    with TestClient(backend.create_app(settings)) as client:
        response = client.post("/api/chat", json={"message": "Offline document question"})
    assert response.status_code == 200
    assert len(parsed) == 1
    assert requests[0]["agent_reference"]["version"] == "7"
    assert response.json()["citations"][0]["label"] == "Document 1"
    assert response.json()["citations"][0]["reference"].startswith("documents/")
    assert response.json()["consultedSources"] == []
    assert response.json()["webSearchUsed"] is False
    assert "wiredstorage" not in response.text
    assert "customer-documents" not in response.text
    assert "sig=" not in response.text
    assert "Private" not in response.text


def test_searchblob_effective_mode_reaches_search_and_foundry_adapters(monkeypatch):
    events = []

    class RecordingWriter:
        def __init__(self, *args, **kwargs):
            events.append(("writer-created", kwargs["owns_credential"]))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append(("writer-closed",))

    class RecordingSearch:
        def __init__(self, client, settings):
            events.append(("search", client, settings))

        def configure(self):
            events.append(("search-configured",))

    class RecordingAgent:
        def __init__(self, writer, agent_name):
            events.append(("agent", agent_name))

        def configure_tools(self, **tools):
            events.append(("tools", tools))

    monkeypatch.setitem(
        sys.modules,
        "azure.identity",
        SimpleNamespace(DefaultAzureCredential=lambda: object()),
    )
    monkeypatch.setattr(cli, "FoundrySdkWriter", RecordingWriter)
    monkeypatch.setattr(
        cli, "AzureRestClient", lambda endpoint, *args, **kwargs: endpoint
    )
    monkeypatch.setattr(cli, "SearchBlobOrchestrator", RecordingSearch)
    monkeypatch.setattr(cli, "AgentToolOrchestrator", RecordingAgent)
    resolved = cli._resolve_deploy_config(
        deploy_config(mode=cli.KnowledgeMode.SEARCH_BLOB),
        search_deployment_values(),
    )

    cli._configure_post_deploy(resolved)

    tools = next(event[1] for event in events if event[0] == "tools")
    assert tools["allowed_domains"] == ("docs.example.org",)
    assert "bing_connection_name" not in tools
    assert tools["search_index_name"] == "documents"
    assert tools["search_connection_name"] == "search-connection"
    assert events.index(("search-configured",)) < next(
        index for index, event in enumerate(events) if event[0] == "tools"
    )
    assert events[0] == ("writer-created", True)
    assert events[-1] == ("writer-closed",)


def test_explicit_override_requires_persisted_app_identity():
    values = deployment_values(CHATBOT_NAME="helper-old")
    del values["SERVICE_WEB_NAME"]

    with pytest.raises(cli.ConfigurationError, match="SERVICE_WEB_NAME"):
        cli._resolve_deploy_config(
            deploy_config(chatbot_name="helper-new"),
            values,
        )


def test_ui_config_flows_from_cli_plan_to_bicep_and_runtime(monkeypatch, capsys):
    from fastapi.testclient import TestClient

    from app.backend.config import AppSettings
    from app.backend.main import create_app

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        Mock(side_effect=AssertionError("offline plan started a subprocess")),
    )
    arguments = [
        "install", "--non-interactive", "--dry-run", "--mode", "off",
        "--environment", "chatbot-dev", "--subscription", "subscription",
        "--resource-group", "rg-chatbot-dev", "--location", "westeurope",
        "--model-name", "model", "--model-version", "1",
        "--model-format", "OpenAI", "--model-sku", "GlobalStandard",
        "--model-capacity", "10", "--deployment-name", "chat-model",
        "--chatbot-name", "helper", "--websites", "https://docs.example.org",
        "--accept-bing-terms", "--foundry-user-role-id",
        "/subscriptions/configured/providers/Microsoft.Authorization/roleDefinitions/foundry",
        "--ui-language", "en",
        "--ui-product-name", "Example Product",
        "--ui-organization-name", "Example Organization",
        "--ui-assistant-name", "Helpful Assistant",
        "--ui-welcome-title", "Welcome",
        "--ui-welcome-subtitle", "Ask a question.",
        "--ui-disclaimer", "AI output requires verification.",
        "--ui-suggestion", "First question?",
        "--ui-suggestion", "Second question?",
    ]

    assert cli.main(arguments) == 0
    plan = json.loads(capsys.readouterr().out)
    env_values = {
        command[3]: command[4]
        for command in plan["commands"]
        if command[:3] == ["azd", "env", "set"]
    }
    assert env_values["UI_PRODUCT_NAME"] == "Example Product"
    assert env_values["UI_LANGUAGE"] == "en"
    assert json.loads(env_values["UI_SUGGESTED_QUESTIONS"]) == [
        "First question?",
        "Second question?",
    ]
    assert plan["config"]["uiProductName"] == "Example Product"
    assert json.loads(plan["config"]["uiSuggestedQuestions"]) == [
        "First question?",
        "Second question?",
    ]
    assert plan["infrastructureDeployment"] == {
        "compile": "Bicep to stdout",
        "transport": "authenticated Azure Resource Manager HTTPS",
        "parameters": "non-secret in-memory request body",
    }

    webapp = (
        Path(__file__).parents[1] / "infra" / "modules" / "webapp.bicep"
    ).read_text(encoding="utf-8")
    for setting in (
        "UI_PRODUCT_NAME",
        "UI_ORGANIZATION_NAME",
        "UI_ASSISTANT_NAME",
        "UI_WELCOME_TITLE",
        "UI_WELCOME_SUBTITLE",
        "UI_DISCLAIMER",
        "UI_SUGGESTED_QUESTIONS",
        "UI_LANGUAGE",
    ):
        assert f"name: '{setting}'" in webapp

    settings = AppSettings.from_environment({
        "APP_ENV": "test",
        "FOUNDRY_PROJECT_ENDPOINT": (
            "https://example.services.ai.azure.com/api/projects/project"
        ),
        **env_values,
    })
    with TestClient(create_app(settings, object_with_response())) as client:
        runtime = client.get("/api/config").json()
    assert runtime == {
        "language": "en",
        "productName": "Example Product",
        "organizationName": "Example Organization",
        "assistantName": "Helpful Assistant",
        "welcomeTitle": "Welcome",
        "welcomeSubtitle": "Ask a question.",
        "disclaimer": "AI output requires verification.",
        "suggestedQuestions": ["First question?", "Second question?"],
        "knowledgeMode": "off",
        "allowedDomains": ["docs.example.org"],
        "websiteEnforcement": "allowed_domains",
        "includesSubdomains": True,
    }


def test_standalone_language_precedence_preserves_persisted_english():
    persisted = deployment_values(
        CHATBOT_NAME="helper",
        UI_LANGUAGE="en",
    )

    preserved = cli._resolve_deploy_config(deploy_config(), persisted)
    overridden = cli._resolve_deploy_config(
        deploy_config(ui_language="it"),
        persisted,
    )

    assert preserved.config.ui_language == "en"
    assert preserved.app_settings["UI_LANGUAGE"] == "en"
    assert overridden.config.ui_language == "it"
    assert overridden.app_settings["UI_LANGUAGE"] == "it"


@pytest.mark.parametrize("stored", ["fr", "", 42])
def test_invalid_persisted_language_fails_before_deploy_side_effects(
    monkeypatch, stored
):
    runner = Mock()
    foundry = Mock()
    app = Mock()
    monkeypatch.setattr(cli, "_configure_post_deploy", foundry)
    monkeypatch.setattr(cli, "_sync_app_service_settings", app)

    with pytest.raises(cli.ConfigurationError, match="UI_LANGUAGE"):
        cli._deploy_application(
            runner,
            deploy_config(),
            deployment_values(UI_LANGUAGE=stored),
        )

    foundry.assert_not_called()
    app.assert_not_called()
    runner.run.assert_not_called()


def object_with_response():
    class Agent:
        async def respond(self, message, previous_response_id=None):
            from azure_bing_assistant.agent import AgentResponse
            return AgentResponse("unused", [], "response-id")

    return Agent()


def test_explicit_empty_ui_cli_value_is_rejected(capsys):
    result = cli.main([
        "install", "--non-interactive", "--dry-run", "--mode", "off",
        "--environment", "chatbot-dev", "--location", "westeurope",
        "--model-capacity", "10", "--websites", "https://docs.example.org",
        "--ui-product-name", "",
    ])

    assert result == 2
    assert "ui_product_name" in capsys.readouterr().err
