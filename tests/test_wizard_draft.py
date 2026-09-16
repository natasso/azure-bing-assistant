from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from azure_bing_assistant import cli, wizard_draft
from azure_bing_assistant.config import ConfigurationError, InstallerConfig
from azure_bing_assistant.wizard import (
    CapabilityError, ConsolePrompts, DiscoveryError, ModelChoice, RegionChoice,
    SubscriptionChoice, WizardCancelled, collect_websites, run_wizard,
)
from azure_bing_assistant.wizard_draft import MAX_DRAFT_BYTES, WizardDraft, WizardDraftError


def load(project):
    draft = WizardDraft(project)
    draft.load()
    return draft


def prompts(answers, language="en"):
    reader = Mock(side_effect=answers)
    output = []
    return ConsolePrompts(reader, output.append, language), reader, output


def discovery():
    return SimpleNamespace(
        subscriptions=Mock(return_value=[SubscriptionChoice("Development", "sub-one", "tenant-one")]),
        resource_groups=Mock(return_value=["rg-existing"]),
        regions=Mock(return_value=[RegionChoice("westeurope", "West Europe")]),
        models=Mock(return_value=[ModelChoice("model-one", "1", "OpenAI", "GlobalStandard", 2, 20, 5)]),
        role_definition=Mock(return_value="/subscriptions/sub-one/providers/Microsoft.Authorization/roleDefinitions/role-one"),
    )


FIRST_ANSWERS = [
    "1", "2", "1", "1", "7", "helper", "chatbot-dev", "chat-model", "no",
    "example.org", "yes", "no", "yes",
]
RESUME_ANSWERS = [""] * 12 + ["yes"]


@pytest.fixture(autouse=True)
def no_cloud(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("No Azure, login, network or deployment allowed"))
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli, "AzdRunner", forbidden)
    monkeypatch.setattr(cli, "AzureProvisioner", forbidden)
    monkeypatch.setattr(cli, "_deploy_application", forbidden)
    monkeypatch.setattr(cli, "AzureCliDiscovery", forbidden)


def seed(project, *, language="en"):
    draft = load(project)
    config = run_wizard(discovery(), prompts(FIRST_ANSWERS)[0], language, draft)
    return draft, config


def test_incremental_valid_answers_survive_cancel_and_two_independent_wizards(tmp_path):
    first = load(tmp_path)
    p, _, _ = prompts(FIRST_ANSWERS[:5] + ["Invalid Chatbot", "helper", EOFError()])
    with pytest.raises(WizardCancelled):
        run_wizard(discovery(), p, "en", first)
    restored = load(tmp_path)
    assert restored.get("capacity") == 7
    assert restored.get("chatbot_name") == "helper"
    assert restored.get("environment_name") is None
    assert "Invalid Chatbot" not in restored.path.read_text()
    p, reader, output = prompts([""] * 6 + FIRST_ANSWERS[6:])
    config = run_wizard(discovery(), p, "en", restored)
    assert config.subscription_id == "sub-one"
    assert config.chatbot_name == "helper" and config.model_capacity == 7
    assert "[helper]" in reader.call_args_list[5].args[0]
    assert "Resuming local installer" in "\n".join(output)
    assert restored.path.exists()  # Returning a config is not a deployment.


@pytest.mark.parametrize("failure", ["provider", "final-config", "terms"])
def test_failure_after_answers_keeps_draft_without_consent_or_service_outputs(tmp_path, monkeypatch, failure):
    d = discovery()
    answers = list(FIRST_ANSWERS)
    if failure == "provider":
        d.role_definition.side_effect = DiscoveryError("provider unavailable")
    elif failure == "final-config":
        monkeypatch.setattr(InstallerConfig, "__post_init__", Mock(side_effect=ConfigurationError("final config failed")))
    else:
        answers[-1] = ""
    with pytest.raises((DiscoveryError, ConfigurationError)):
        run_wizard(d, prompts(answers)[0], "en", load(tmp_path))
    stored = load(tmp_path)
    assert stored.get("domains") == [{"domain": "example.org", "include_subdomains": True}]
    assert set(json.loads(stored.path.read_text())["answers"]) == {
        "language", "tenant_id", "subscription_id", "resource_group", "create_group",
        "location", "model", "capacity", "chatbot_name", "environment_name",
        "deployment_name", "use_search", "domains", "domain_more",
    }
    assert "role-one" not in stored.path.read_text()


@pytest.mark.parametrize("explicit", [None, "it", "en"])
def test_language_defaults_and_explicit_override_do_not_discard_other_answers(tmp_path, explicit):
    seed(tmp_path)
    p, reader, output = prompts(([""] if explicit is None else []) + RESUME_ANSWERS)
    config = run_wizard(discovery(), p, explicit, load(tmp_path))
    assert config.ui_language == (explicit or "en")
    assert config.chatbot_name == "helper"
    if explicit is None:
        assert reader.call_args_list[0].args[0].endswith("[2]: ")
    assert ("Ripresa" if explicit == "it" else "Resuming") in "\n".join(output)


def test_new_resource_group_text_default_is_revalidated_and_bad_override_not_saved(tmp_path):
    p, _, _ = prompts(["1", "1", "rg-created", "1", "1", "7", "helper", EOFError()])
    with pytest.raises(WizardCancelled):
        run_wizard(discovery(), p, "en", load(tmp_path))
    draft = load(tmp_path)
    p, reader, output = prompts(["", "", "bad/group", "", EOFError()])
    with pytest.raises(WizardCancelled):
        run_wizard(discovery(), p, "en", draft)
    assert draft.get("resource_group") == "rg-created"
    assert "[rg-created]" in reader.call_args_list[2].args[0]
    assert "not valid for Azure" in "\n".join(output)


def test_reordered_menus_match_stable_ids_not_indices_and_retry_without_discovery(tmp_path):
    seed(tmp_path)
    d = discovery()
    d.subscriptions.return_value.insert(0, SubscriptionChoice("Other", "sub-two", "tenant-two"))
    d.resource_groups.return_value.insert(0, "rg-other")
    d.regions.return_value.insert(0, RegionChoice("eastus", "East US"))
    d.models.return_value.insert(0, ModelChoice("model-two", "2", "OpenAI", "Standard"))
    p, reader, _ = prompts(["wrong", "", "wrong", "", "wrong", "", "wrong", ""] + RESUME_ANSWERS[4:])
    config = run_wizard(d, p, "en", load(tmp_path))
    assert (config.subscription_id, config.resource_group_name, config.location, config.model_name) == (
        "sub-one", "rg-existing", "westeurope", "model-one",
    )
    assert [reader.call_args_list[n].args[0] for n in (0, 2, 4, 6)] == [
        "Select a number [2]: ", "Select a number [3]: ",
        "Select a number [2]: ", "Select a number [2]: ",
    ]
    for name in ("subscriptions", "resource_groups", "regions", "models"):
        getattr(d, name).assert_called_once()


@pytest.mark.parametrize("removed", ["subscription", "group", "region", "model"])
def test_missing_saved_selections_require_explicit_available_choice(tmp_path, removed):
    seed(tmp_path)
    d = discovery()
    if removed == "subscription":
        d.subscriptions.return_value = [SubscriptionChoice("Other", "sub-two", "tenant-two")]
        before, choose = [], "1"
    elif removed == "group":
        d.resource_groups.return_value = ["rg-other"]
        before, choose = [""], "2"
    elif removed == "region":
        d.regions.return_value = [RegionChoice("eastus", "East US")]
        before, choose = ["", ""], "1"
    else:
        d.models.return_value = [ModelChoice("model-two", "2", "OpenAI", "Standard")]
        before, choose = ["", "", ""], "1"
    p, reader, output = prompts(before + ["", choose, EOFError()])
    with pytest.raises(WizardCancelled):
        run_wizard(d, p, "en", load(tmp_path))
    assert "no longer available" in "\n".join(output)
    assert reader.call_args_list[len(before)].args[0] == "Select a number: "
    assert reader.call_args_list[len(before) + 1].args[0] == "Select a number: "


@pytest.mark.parametrize("change", ["tenant", "subscription", "region", "sku"])
def test_parent_changes_drop_only_dependent_defaults_persistently(tmp_path, change):
    seed(tmp_path)
    d = discovery()
    if change in {"tenant", "subscription"}:
        d.subscriptions.return_value = [SubscriptionChoice(
            "Other", "sub-two" if change == "subscription" else "sub-one",
            "tenant-two" if change == "tenant" else "tenant-one",
        )]
        answers = ["1", EOFError()]
        removed = {"resource_group", "create_group", "location", "model", "capacity", "environment_name", "deployment_name"}
    elif change == "region":
        d.regions.return_value = [RegionChoice("eastus", "East US")]
        answers, removed = ["", "", "1", EOFError()], {"model", "capacity"}
    else:
        d.models.return_value = [ModelChoice("model-one", "1", "OpenAI", "Standard", 1, 3, 2)]
        answers, removed = ["", "", "", "1", EOFError()], {"capacity"}
    with pytest.raises(WizardCancelled):
        run_wizard(d, prompts(answers)[0], "en", load(tmp_path))
    restored = load(tmp_path)
    for field in removed:
        assert restored.get(field) is None
    assert restored.get("chatbot_name") == "helper"
    assert restored.get("domains")[0]["domain"] == "example.org"
    assert restored.get("use_search") is False
    if change in {"region", "sku"}:
        assert restored.get("environment_name") == "chatbot-dev"


def test_cached_capacity_outside_fresh_bounds_is_explained_not_clamped(tmp_path):
    seed(tmp_path)
    d = discovery()
    d.models.return_value = [ModelChoice("model-one", "1", "OpenAI", "GlobalStandard", 8, 20, 12)]
    p, reader, output = prompts([""] * 4 + ["7", "8"] + RESUME_ANSWERS[5:])
    config = run_wizard(d, p, "en", load(tmp_path))
    assert config.model_capacity == 8
    assert reader.call_args_list[4].args[0].endswith("[12]: ")
    assert reader.call_args_list[4] == reader.call_args_list[5]
    assert "Saved capacity 7 is outside" in "\n".join(output)
    assert load(tmp_path).get("capacity") == 8


@pytest.mark.parametrize("language", ["it", "en"])
def test_remembered_search_yes_and_capacity_boundary_revalidate(tmp_path, language):
    draft, _ = seed(tmp_path, language=language)
    draft.update(use_search=True, capacity=20)
    d = discovery()
    p, reader, output = prompts(RESUME_ANSWERS, language)
    config = run_wizard(d, p, language, load(tmp_path))
    assert config.knowledge_mode.value == "searchBlob"
    assert config.model_capacity == 20
    assert reader.call_args_list[4].args[0].endswith("[20]: ")
    assert reader.call_args_list[8].args[0].endswith("[S/n]: " if language == "it" else "[Y/n]: ")
    assert d.role_definition.call_count == 3
    assert ("Invio = Sì." if language == "it" else "Enter = Yes.") in "\n".join(output)


def test_invalid_domain_override_keeps_previous_valid_answer_and_policy(tmp_path):
    draft = domain_seed(tmp_path, [("one.org", True), ("two.org", False)])
    original = draft.path.read_bytes()
    with pytest.raises(WizardCancelled):
        collect_websites(prompts(["one.org/path", EOFError()])[0], draft)
    assert draft.path.read_bytes() == original


def domain_seed(project, rules):
    draft = load(project)
    draft.update(domains=[
        {"domain": domain, "include_subdomains": policy} for domain, policy in rules
    ], domain_more=False)
    return draft


def test_partial_multidomain_resume_keeps_unvisited_tail_and_pending_text(tmp_path):
    domain_seed(tmp_path, [("one.org", True), ("two.org", False), ("three.org", True)])
    with pytest.raises(WizardCancelled):
        collect_websites(prompts(["", "", "", "edited.org", EOFError()])[0], load(tmp_path))
    draft = load(tmp_path)
    assert draft.get("domains") == [
        {"domain": "one.org", "include_subdomains": True},
        {"domain": "edited.org"},
        {"domain": "three.org", "include_subdomains": True},
    ]
    p, reader, _ = prompts(["", "", "", "", "yes", "", "", "", ""])
    assert collect_websites(p, draft) == ("one.org", "edited.org", "three.org")
    questions = [call.args[0] for call in reader.call_args_list]
    assert questions[2].endswith("[Y/n]: ")
    assert questions[4].endswith("[y/N]: ")  # Edited identity never inherits old Yes.
    assert questions[5].endswith("[Y/n]: ")
    assert questions[8].endswith("[y/N]: ")


def test_partial_policy_resume_does_not_drop_later_saved_pending_answer(tmp_path):
    draft = load(tmp_path)
    draft.update(domains=[
        {"domain": "one.org", "include_subdomains": True},
        {"domain": "two.org"},
        {"domain": "three.org", "include_subdomains": False},
    ])
    with pytest.raises(WizardCancelled):
        collect_websites(prompts(["", "", EOFError()])[0], draft)
    assert len(load(tmp_path).get("domains")) == 3
    assert load(tmp_path).get("domains")[1] == {"domain": "two.org"}


def test_explicit_no_truncates_tail_even_if_later_installation_fails(tmp_path):
    draft = domain_seed(tmp_path, [("one.org", True), ("two.org", False), ("three.org", True)])
    assert collect_websites(prompts(["", "", "no"])[0], draft) == ("one.org",)
    assert load(tmp_path).get("domains") == [{"domain": "one.org", "include_subdomains": True}]


@pytest.mark.parametrize("edited", ["one.org", "https://ONE.ORG./", "other.org"])
def test_policy_defaults_follow_canonical_identity_and_never_broaden(tmp_path, edited):
    draft = domain_seed(tmp_path, [("one.org", True)])
    p, reader, _ = prompts([edited, "", ""])
    if edited == "other.org":
        with pytest.raises(CapabilityError):
            collect_websites(p, draft)
        assert reader.call_args_list[1].args[0].endswith("[y/N]: ")
        assert load(tmp_path).get("domains")[0]["include_subdomains"] is False
    else:
        assert collect_websites(p, draft) == ("one.org",)
        assert reader.call_args_list[1].args[0].endswith("[Y/n]: ")


def test_saved_unsupported_false_remains_false_and_stops_before_terms(tmp_path):
    draft, _ = seed(tmp_path)
    draft.update(domains=[{"domain": "example.org", "include_subdomains": False}])
    d = discovery()
    with pytest.raises(CapabilityError):
        run_wizard(d, prompts(RESUME_ANSWERS)[0], "en", load(tmp_path))
    d.role_definition.assert_not_called()
    assert load(tmp_path).get("domains")[0]["include_subdomains"] is False


def test_duplicates_against_unvisited_saved_domains_do_not_change_draft(tmp_path):
    domain_seed(tmp_path, [("one.org", True), ("two.org", False)])
    p, _, output = prompts(["https://TWO.ORG/", EOFError()])
    with pytest.raises(WizardCancelled):
        collect_websites(p, load(tmp_path))
    assert load(tmp_path).get("domains")[0]["domain"] == "one.org"
    assert "remaining saved rules" in "\n".join(output)


def test_saved_add_another_choice_resumes_pending_new_domain_once(tmp_path):
    domain_seed(tmp_path, [("one.org", True)])
    with pytest.raises(WizardCancelled):
        collect_websites(prompts(["", "", "yes", EOFError()])[0], load(tmp_path))
    assert load(tmp_path).get("domain_more") is True
    p, reader, _ = prompts(["", "", "", "two.org", "yes", ""])
    assert collect_websites(p, load(tmp_path)) == ("one.org", "two.org")
    assert reader.call_args_list[2].args[0].endswith("[Y/n]: ")
    assert reader.call_args_list[-1].args[0].endswith("[y/N]: ")
    assert load(tmp_path).get("domain_more") is False


def test_maximum_100_domains_resume_without_101st_prompt(tmp_path):
    draft = domain_seed(tmp_path, [(f"site{index}.org", True) for index in range(100)])
    p, reader, output = prompts([""] * 299)
    assert len(collect_websites(p, draft)) == 100
    assert reader.call_count == 299
    assert "Maximum of 100" in "\n".join(output)


@pytest.mark.parametrize("document", [
    {}, [], {"version": 2, "answers": {}}, {"version": True, "answers": {}},
    {"version": 1, "answers": []},
    {"version": 1, "answers": {}, "accept_bing_terms": True},
    *({"version": 1, "answers": {key: value}} for key, value in [
        ("accept_bing_terms", True), ("bing_terms_accepted", True), ("final_approval", True),
        ("token", "secret"), ("foundry_project_endpoint", "https://example.org"),
        ("language", "xx"), ("language", 1), ("chatbot_name", "bad name"),
        ("use_search", "false"), ("use_search", 1), ("capacity", True),
        ("capacity", 5), ("model", {}), ("domain_more", True),
        ("domains", [{"domain": "example.org", "include_subdomains": "false"}]),
        ("domains", [{"domain": "https://example.org/", "include_subdomains": True}]),
        ("domains", [{"domain": "one.org"}, {"domain": "one.org", "include_subdomains": False}]),
        ("domains", [{"domain": f"site{i}.org"} for i in range(101)]),
    ]),
])
def test_invalid_or_foreign_drafts_fail_closed_and_are_not_overwritten(tmp_path, document):
    path = tmp_path / ".azure" / "installer-draft.json"
    path.parent.mkdir()
    original = json.dumps(document)
    path.write_text(original)
    with pytest.raises(WizardDraftError, match="--reset-wizard"):
        load(tmp_path)
    assert path.read_text() == original


@pytest.mark.parametrize("raw", [
    b"{", b"\xff", b" " * (MAX_DRAFT_BYTES + 1),
    b'{"version":1,"version":1,"answers":{}}',
    b'{"version":1,"answers":{"language":"en","language":"it"}}',
    b"[" * 2000 + b"]" * 2000,
], ids=["corrupt", "encoding", "oversized", "duplicate-version", "duplicate-answer", "deep"])
def test_corrupt_oversize_duplicate_or_deep_json_rejected(tmp_path, raw):
    path = tmp_path / ".azure" / "installer-draft.json"
    path.parent.mkdir()
    path.write_bytes(raw)
    with pytest.raises(WizardDraftError, match="--reset-wizard"):
        load(tmp_path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("failure", ["replace", "fsync", "temporary"])
def test_atomic_save_failure_keeps_previous_answers_and_cleans_own_temporary(tmp_path, monkeypatch, failure):
    draft = load(tmp_path)
    draft.update(language="en")
    original = draft.path.read_bytes()
    def fail(*args, **kwargs):
        raise PermissionError("test only")
    if failure == "temporary":
        monkeypatch.setattr(wizard_draft.tempfile, "NamedTemporaryFile", fail)
    else:
        monkeypatch.setattr(wizard_draft.os, failure, fail)
    with pytest.raises(WizardDraftError, match="permissions"):
        draft.update(chatbot_name="helper")
    assert draft.get("chatbot_name") is None
    assert draft.path.read_bytes() == original
    assert list(draft.path.parent.iterdir()) == [draft.path]


def test_atomic_replace_uses_same_ignored_directory_and_valid_json(tmp_path, monkeypatch):
    draft = load(tmp_path)
    real_replace = os.replace
    observations = []
    def replace(source, target):
        observations.append((source, target))
        assert Path(source).parent == draft.path.parent == Path(target).parent
        assert json.loads(Path(source).read_text())["answers"]["language"] == "en"
        return real_replace(source, target)
    monkeypatch.setattr(wizard_draft.os, "replace", replace)
    draft.update(language="en")
    assert len(observations) == 1
    assert load(tmp_path).get("language") == "en"


def test_invalid_save_never_replaces_prior_valid_draft(tmp_path):
    draft = load(tmp_path)
    draft.update(language="en")
    before = draft.path.read_bytes()
    for values in ({"chatbot_name": "Bad Name"}, {"accept_bing_terms": True}, {"domains": ["example.org"]}):
        with pytest.raises(WizardDraftError):
            draft.update(**values)
        assert draft.path.read_bytes() == before


def test_concurrent_or_foreign_file_is_not_overwritten_or_cleared(tmp_path):
    draft = load(tmp_path)
    draft.update(language="en")
    draft.path.write_text("foreign")
    with pytest.raises(WizardDraftError, match="changed on disk"):
        draft.update(chatbot_name="helper")
    with pytest.raises(WizardDraftError, match="changed on disk"):
        draft.clear()
    assert draft.path.read_text() == "foreign"


def test_reset_only_removes_owned_filename_even_when_corrupt(tmp_path):
    draft = WizardDraft(tmp_path)
    draft.path.parent.mkdir()
    draft.path.write_text("corrupt")
    other = draft.path.parent / "config.json"
    other.write_text("preserve")
    environment = draft.path.parent / "my-env"
    environment.mkdir()
    (environment / ".env").write_text("preserve")
    draft.clear(reset=True)
    assert not draft.path.exists()
    assert other.read_text() == "preserve"
    assert (environment / ".env").read_text() == "preserve"
    assert not load(tmp_path).has_answers


def test_first_load_and_reset_without_answers_do_not_create_directory(tmp_path):
    draft = load(tmp_path)
    draft.clear(reset=True)
    assert not (tmp_path / ".azure").exists()


@pytest.mark.parametrize("target", ["directory", "symlink"])
def test_directory_or_symlink_draft_is_not_opened_or_deleted(tmp_path, monkeypatch, target):
    draft = WizardDraft(tmp_path)
    draft.path.parent.mkdir()
    if target == "directory":
        draft.path.mkdir()
    else:
        draft.path.write_text("foreign")
        original_lstat = Path.lstat
        def lstat(path):
            result = original_lstat(path)
            if path == draft.path:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            return result
        monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(WizardDraftError):
        draft.load()
    with pytest.raises(WizardDraftError):
        draft.clear(reset=True)
    assert draft.path.exists()


def test_link_and_reparse_paths_fail_without_read_write_or_delete(tmp_path, monkeypatch):
    draft = WizardDraft(tmp_path)
    draft.path.parent.mkdir()
    draft.path.write_text("foreign")
    original_lstat = Path.lstat
    def lstat(path):
        result = original_lstat(path)
        if path == draft.path.parent:
            return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return result
    monkeypatch.setattr(Path, "lstat", lstat)
    for operation in (draft.load, lambda: draft.clear(reset=True)):
        with pytest.raises(WizardDraftError):
            operation()
    assert draft.path.read_text() == "foreign"


def test_hardlinked_foreign_file_is_not_read_or_deleted(tmp_path):
    foreign = tmp_path / "foreign.json"
    foreign.write_text("foreign")
    draft = WizardDraft(tmp_path)
    draft.path.parent.mkdir()
    os.link(foreign, draft.path)
    with pytest.raises(WizardDraftError):
        draft.load()
    with pytest.raises(WizardDraftError):
        draft.clear(reset=True)
    assert foreign.read_text() == "foreign" and draft.path.exists()


def test_load_io_failure_is_explicit_and_leaves_file(tmp_path, monkeypatch):
    draft, _ = seed(tmp_path)
    original_open = Path.open
    def denied(path, *args, **kwargs):
        if path == draft.path:
            raise PermissionError("test only")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(WizardDraftError, match="permissions"):
        load(tmp_path)
    assert draft.path.exists()


def test_instances_and_wizard_without_injected_draft_do_not_share_or_write(tmp_path, monkeypatch):
    project = tmp_path / "first"
    project.mkdir()
    seed(project)
    monkeypatch.chdir(tmp_path)
    run_wizard(discovery(), prompts(FIRST_ANSWERS)[0], "en")
    assert not (tmp_path / ".azure").exists()
    second = load(tmp_path)
    assert not second.has_answers and second.get("language") is None


def install_run(monkeypatch, answers, *arguments):
    p, reader, output = prompts(answers)
    monkeypatch.setattr(cli, "ConsolePrompts", lambda **kwargs: p)
    monkeypatch.setattr(cli, "AzureCliDiscovery", discovery)
    return cli.main(["install", "--ui-language", "en", *arguments]), reader, output


@pytest.mark.parametrize("first_failure", ["cancel", "provider", "provision", "package", "interrupt", "success"])
def test_repeated_cli_runs_retain_answers_after_all_outcomes(tmp_path, monkeypatch, first_failure):
    monkeypatch.chdir(tmp_path)
    runner = Mock()
    runner.get_environment_values.return_value = {}
    provisioner = Mock()
    provisioner.run.return_value = {}
    monkeypatch.setattr(cli, "AzdRunner", Mock(return_value=runner))
    monkeypatch.setattr(cli, "AzureProvisioner", Mock(return_value=provisioner))
    deployed = Mock(side_effect=lambda _runner, config, _values, **_kwargs: SimpleNamespace(config=config))
    monkeypatch.setattr(cli, "_deploy_application", deployed)
    if first_failure == "cancel":
        answers = FIRST_ANSWERS + [EOFError()]
    elif first_failure == "provider":
        # Role discovery fails after all ordinary answers, before terms/consent.
        d = discovery()
        d.role_definition.side_effect = DiscoveryError("provider unavailable")
        monkeypatch.setattr(cli, "ConsolePrompts", lambda **kwargs: prompts(FIRST_ANSWERS)[0])
        monkeypatch.setattr(cli, "AzureCliDiscovery", lambda: d)
        assert cli.main(["install", "--ui-language", "en"]) == 2
        answers = None
    else:
        answers = FIRST_ANSWERS + ["yes"]
        if first_failure == "interrupt":
            provisioner.run.side_effect = KeyboardInterrupt()
        elif first_failure == "provision":
            provisioner.run.side_effect = RuntimeError("provision failed")
        elif first_failure == "package":
            deployed.side_effect = RuntimeError("package failed")
    if answers is not None:
        assert install_run(monkeypatch, answers)[0] == (
            1 if first_failure == "cancel" else 130 if first_failure == "interrupt" else 0 if first_failure == "success" else 2
        )
    persisted = load(tmp_path)
    assert persisted.path.exists() and persisted.get("chatbot_name") == "helper"
    provisioner.run.side_effect = None
    deployed.side_effect = lambda _runner, config, _values, **_kwargs: SimpleNamespace(config=config)
    result, _, _ = install_run(monkeypatch, RESUME_ANSWERS + ["yes"])
    assert result == 0 and persisted.path.exists()
    assert deployed.call_args.args[1].model_capacity == 7
    assert deployed.call_args.args[1].subscription_id == "sub-one"
    calls = deployed.call_count
    result, reader, _ = install_run(monkeypatch, RESUME_ANSWERS + ["no"])
    assert result == 1 and deployed.call_count == calls
    assert "[7]" in reader.call_args_list[4].args[0]
    assert reader.call_args_list[-1].args[0].endswith("[y/N]: ")
    assert load(tmp_path).get("capacity") == 7
    result, reader, _ = install_run(monkeypatch, [""] * 12 + ["no"])
    assert result == 2 and deployed.call_count == calls
    assert reader.call_args_list[-1].args[0].endswith("[y/N]: ")
    saved = persisted.path.read_text()
    assert "bing_terms_accepted" not in saved and "credential" not in saved


@pytest.mark.parametrize("language", ["it", "en"])
def test_saved_capacity_1000_preserved_and_explained_before_prompt(tmp_path, language):
    seed(tmp_path)
    draft = load(tmp_path)
    draft.update(capacity=1000)
    d = discovery()
    d.models.return_value = [ModelChoice("model-one", "1", "OpenAI", "GlobalStandard", 1, 2000, 10)]
    p, reader, output = prompts(RESUME_ANSWERS, language)
    config = run_wizard(d, p, language, draft)
    assert config.model_capacity == 1000 and load(tmp_path).get("capacity") == 1000
    assert "[1000]" in reader.call_args_list[4].args[0]
    text = "\n".join(output)
    assert ("Capacità mostrata: 1000" if language == "it" else "Displayed capacity: 1000") in text
    assert ("SKU: 10" if language == "it" else "SKU default: 10") in text


@pytest.mark.parametrize("language", ["it", "en"])
def test_interrupt_after_approval_keeps_draft_and_reports_remote_continuation(tmp_path, monkeypatch, capsys, language):
    import threading

    seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    p, _, _ = prompts(RESUME_ANSWERS + ["yes"], language)
    monkeypatch.setattr(cli, "ConsolePrompts", lambda **_: p)
    monkeypatch.setattr(cli, "AzureCliDiscovery", discovery)
    monkeypatch.setattr(cli, "AzdRunner", lambda _: Mock(
        get_environment_values=Mock(return_value={}),
    ))
    monkeypatch.setattr(cli, "AzureProvisioner", lambda _: SimpleNamespace(run=Mock(side_effect=KeyboardInterrupt())))
    assert cli.main(["install", "--ui-language", language]) == 130
    text = capsys.readouterr().err
    assert ("interrotta" if language == "it" else "interrupted") in text
    assert ("Le operazioni remote possono continuare" if language == "it" else "Remote operations may continue") in text
    assert load(tmp_path).has_answers
    assert not any(thread.name == "installer-progress" for thread in threading.enumerate())


@pytest.mark.parametrize("stage", ["terms", "final"])
@pytest.mark.parametrize("answer", ["", "no"])
def test_resumed_consent_always_requires_fresh_yes_and_never_writes_azure(tmp_path, monkeypatch, stage, answer):
    seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    if stage == "terms":
        answers = [""] * 12 + [answer]
    else:
        answers = RESUME_ANSWERS + [answer]
    result, reader, _ = install_run(monkeypatch, answers)
    assert result == (2 if stage == "terms" else 1)
    assert reader.call_args_list[-1].args[0].endswith("[y/N]: ")
    assert load(tmp_path).get("domains")[0]["include_subdomains"] is True


def test_cli_success_never_attempts_to_remove_saved_defaults(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = Mock()
    runner.get_environment_values.return_value = {}
    provisioner = Mock()
    provisioner.run.return_value = {}
    monkeypatch.setattr(cli, "AzdRunner", lambda *_: runner)
    monkeypatch.setattr(cli, "AzureProvisioner", lambda *_: provisioner)
    monkeypatch.setattr(cli, "_deploy_application", lambda _r, config, _v, **_kwargs: SimpleNamespace(config=config))
    original = Path.unlink
    def fail(path, *args, **kwargs):
        if path.name == "installer-draft.json":
            raise AssertionError("Successful installation must retain defaults")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail)
    assert install_run(monkeypatch, RESUME_ANSWERS + ["yes"])[0] == 0
    captured = capsys.readouterr()
    assert '"status": "succeeded"' in captured.out
    assert "Deployment succeeded, but" not in captured.err
    assert "Installation failed" not in captured.err
    assert load(tmp_path).has_answers


def test_reset_after_success_only_clears_local_wizard_answers(tmp_path, monkeypatch):
    seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = Mock()
    runner.get_environment_values.return_value = {}
    provisioner = Mock()
    provisioner.run.return_value = {}
    monkeypatch.setattr(cli, "AzdRunner", lambda *_: runner)
    monkeypatch.setattr(cli, "AzureProvisioner", lambda *_: provisioner)
    monkeypatch.setattr(cli, "_deploy_application", lambda _r, config, _v, **_kwargs: SimpleNamespace(config=config))
    assert install_run(monkeypatch, RESUME_ANSWERS + ["yes"])[0] == 0
    other = tmp_path / ".azure" / "config.json"
    other.write_text("preserve environment")
    assert load(tmp_path).get("capacity") == 7
    result, reader, _ = install_run(monkeypatch, [EOFError()], "--reset-wizard")
    assert result == 1
    assert load(tmp_path).get("capacity") is None
    assert other.read_text() == "preserve environment"
    assert "[7]" not in reader.call_args.args[0]


def test_cli_save_failure_stops_before_discovery_or_any_azure_write(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    d = discovery()
    monkeypatch.setattr(cli, "AzureCliDiscovery", lambda: d)
    monkeypatch.setattr(wizard_draft.os, "replace", Mock(side_effect=OSError("test only")))
    assert cli.main(["install", "--ui-language", "en"]) == 2
    d.subscriptions.assert_not_called()
    assert "--reset-wizard" in capsys.readouterr().err
    assert not (tmp_path / ".azure" / "installer-draft.json").exists()


@pytest.mark.parametrize("language", ["it", "en"])
def test_corrupt_cli_draft_localized_recovery_and_explicit_reset(tmp_path, monkeypatch, capsys, language):
    draft = WizardDraft(tmp_path)
    draft.path.parent.mkdir()
    draft.path.write_text("corrupt")
    other = draft.path.parent / "config.json"
    other.write_text("preserve")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["install", "--ui-language", language]) == 2
    message = capsys.readouterr().err
    assert "--reset-wizard" in message
    assert ("Bozza" if language == "it" else "Invalid installer draft") in message
    p, reader, _ = prompts([EOFError()], language)
    monkeypatch.setattr(cli, "ConsolePrompts", lambda **kwargs: p)
    monkeypatch.setattr(cli, "AzureCliDiscovery", discovery)
    assert cli.main(["install", "--ui-language", language, "--reset-wizard"]) == 1
    assert reader.call_args.args[0].endswith("number: " if language == "en" else "numero: ")
    assert load(tmp_path).get("language") == language
    assert load(tmp_path).get("subscription_id") is None
    assert other.read_text() == "preserve"


@pytest.mark.parametrize("arguments,exit_code", [
    (["install", "--help"], 0),
    (["--help"], 0),
    (["install", "--unknown"], 2),
    (["install", "--ui-language", "xx"], 2),
    (["install", "--dry-run"], None),
    (["install", "--non-interactive"], None),
    (["install", "--non-interactive", "--dry-run"], None),
    (["install", "--reset-wizard", "--non-interactive"], None),
    (["install", "--reset-wizard", "--dry-run"], None),
    (["doctor"], None),
    (["plan", "--mode", "off", "--dry-run", "--websites", "example.org"], None),
    (["provision", "--mode", "off"], None),
    (["deploy", "--websites", "example.org"], None),
])
def test_other_entrypoints_never_construct_or_read_draft(tmp_path, monkeypatch, arguments, exit_code):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "WizardDraft", Mock(side_effect=AssertionError("draft must not be accessed")))
    monkeypatch.setattr(cli, "_doctor", lambda: 0)
    monkeypatch.setattr(cli, "_noninteractive_config", Mock(side_effect=ConfigurationError("missing explicit config")))
    monkeypatch.setattr(cli, "AzdRunner", Mock(side_effect=RuntimeError("stubbed runner")))
    if exit_code is not None:
        with pytest.raises(SystemExit) as error:
            cli.main(arguments)
        assert error.value.code == exit_code
    else:
        cli.main(arguments)
    cli.WizardDraft.assert_not_called()
    assert not (tmp_path / ".azure").exists()
