import ast
from collections import Counter
from io import BytesIO, StringIO, TextIOWrapper
import json
import os
from pathlib import Path
import re
from string import Formatter
import subprocess
import sys
from unittest.mock import Mock

import pytest

from azure_bing_assistant import cli
from azure_bing_assistant.agent import transform_citations
from azure_bing_assistant.config import ConfigurationError, validate_ui_language
from azure_bing_assistant.install_progress import InstallProgress
from azure_bing_assistant.installer_messages import InstallerMessages
from azure_bing_assistant.localization import (
    DEFAULT_UI_LANGUAGE,
    LANGUAGE_LABELS,
    NO_WORDS,
    RTL_UI_LANGUAGES,
    SUPPORTED_UI_LANGUAGES,
    YES_WORDS,
    load_catalog,
)
from azure_bing_assistant.provision import _deployment_parameters
from azure_bing_assistant.wizard import (
    ConsolePrompts, ModelChoice, RegionChoice, SubscriptionChoice, run_wizard,
)
from azure_bing_assistant.wizard_draft import WizardDraft


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "src" / "azure_bing_assistant" / "locales"
LANGUAGES = ("it", "en", "fr", "es", "pt", "el", "he", "ar", "tr")


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        assert name not in result, f"Duplicate catalog key: {name}"
        result[name] = value
    return result


def placeholders(value):
    return Counter(
        (name, spec, conversion)
        for _, name, spec, conversion in Formatter().parse(value)
        if name is not None
    )


def test_language_registry_is_consistent_and_keeps_existing_defaults():
    assert SUPPORTED_UI_LANGUAGES == LANGUAGES
    assert DEFAULT_UI_LANGUAGE == "it"
    assert RTL_UI_LANGUAGES == ("he", "ar")
    assert len(LANGUAGE_LABELS) == len(LANGUAGES)
    assert set(YES_WORDS) == set(NO_WORDS) == set(LANGUAGES)
    assert {p.stem for p in LOCALES.glob("*.json")} == set(LANGUAGES)


@pytest.mark.parametrize("language", LANGUAGES)
def test_catalogs_have_complete_keys_types_and_matching_placeholders(language):
    reference = load_catalog("en")
    raw = json.loads(
        (LOCALES / f"{language}.json").read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
    )
    assert set(raw) == set(reference)
    assert load_catalog(language) == raw
    for section, messages in reference.items():
        assert set(raw[section]) == set(messages)
        for key, source in messages.items():
            translated = raw[section][key]
            assert type(translated) is type(source), (language, section, key)
            sources = source if isinstance(source, list) else [source]
            values = translated if isinstance(translated, list) else [translated]
            assert len(sources) == len(values)
            for original, value in zip(sources, values):
                assert value.strip(), (language, section, key)
                assert placeholders(value) == placeholders(original), (language, section, key)
                assert not re.search(r"[\u202a-\u202e\u2066-\u2069]", value)
    if language != "en":
        assert raw["frontend"]["startConversation"] != reference["frontend"]["startConversation"]
        assert raw["installer"]["Installation failed"] != "Installation failed"


@pytest.mark.parametrize("language", LANGUAGES)
def test_native_yes_no_and_english_aliases_keep_explicit_consent(language):
    yes, no = YES_WORDS[language], NO_WORDS[language]
    assert not set(yes).intersection(no)
    assert {"y", "yes"} <= set(yes)
    assert {"n", "no"} <= set(no)
    for accepted, words in ((True, yes), (False, no)):
        for word in words:
            reader = Mock(return_value=word)
            output = []
            prompts = ConsolePrompts(reader, output.append, language=language)
            assert prompts.yes_no("Consent", default=False) is accepted
            assert "/".join(yes) in output[0] and "/".join(no) in output[0]
    assert ConsolePrompts(lambda _: "", lambda _: None, language).yes_no("Consent") is False


@pytest.mark.parametrize("language", LANGUAGES)
def test_wizard_menu_config_draft_and_arm_parameters_use_the_selected_language(tmp_path, language):
    discovery = Mock()
    discovery.subscriptions.return_value = [
        SubscriptionChoice("Example", "sub-example", "tenant-example"),
    ]
    discovery.resource_groups.return_value = ["rg-university"]
    discovery.regions.return_value = [RegionChoice("westeurope", "West Europe")]
    discovery.models.return_value = [
        ModelChoice("example-model", "2026-01-01", "OpenAI", "DataZoneStandard", 1, 2000, 1000),
    ]
    discovery.role_definition.return_value = (
        "/subscriptions/sub-example/providers/Microsoft.Authorization/roleDefinitions/example"
    )
    reader = Mock(side_effect=[
        str(LANGUAGES.index(language) + 1),
        "1", "2", "1", "1", "",
        "university-assistant", "university-demo", "chat-model",
        NO_WORDS[language][1], "portal.example.edu",
        YES_WORDS[language][1], NO_WORDS[language][1], YES_WORDS[language][1],
    ])
    output = []
    draft = WizardDraft(tmp_path)
    draft.load()
    config = run_wizard(discovery, ConsolePrompts(reader, output.append), draft=draft)
    assert config.ui_language == language
    assert config.model_capacity == 1000
    assert config.websites == ("portal.example.edu",)
    assert config.bing_terms_accepted is True
    assert _deployment_parameters(config)["uiLanguage"] == {"value": language}
    assert reader.call_count == 14
    for label in LANGUAGE_LABELS:
        assert any(label in line for line in output)
    tr = InstallerMessages(language)
    assert any(tr("Press Enter to keep this value, or enter another value (positive integer).") == line for line in output)
    assert any(tr("Short installation name (e.g. assistant-demo)") in call.args[0] for call in reader.call_args_list)
    resumed = WizardDraft(tmp_path)
    resumed.load()
    assert resumed.get("language") == language
    assert resumed.get("capacity") == 1000


@pytest.mark.parametrize("language", LANGUAGES)
def test_noninteractive_plan_retains_every_supported_language_without_cloud_writes(capsys, language):
    arguments = [
        "install", "--non-interactive", "--dry-run",
        "--environment", "university-demo", "--subscription", "sub-example",
        "--resource-group", "rg-university", "--no-create-resource-group",
        "--location", "westeurope", "--model-name", "example-model",
        "--model-version", "2026-01-01", "--model-format", "OpenAI",
        "--model-sku", "DataZoneStandard", "--model-capacity", "1000",
        "--deployment-name", "chat-model", "--chatbot-name", "university-assistant",
        "--ui-language", language, "--websites", "portal.example.edu",
        "--accept-bing-terms", "--foundry-user-role-id",
        "/subscriptions/sub-example/providers/Microsoft.Authorization/roleDefinitions/example",
    ]
    assert cli.main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["config"]["uiLanguage"] == language
    assert any(
        command[:5] == ["azd", "env", "set", "MODEL_CAPACITY", "1000"]
        for command in result["commands"]
    )
    assert result["postDeploy"]["websiteEnforcement"] == "allowed_domains"


@pytest.mark.parametrize("language", LANGUAGES)
def test_progress_citation_labels_and_validation_are_localized(language):
    tr = InstallerMessages(language)
    stream = StringIO()
    with InstallProgress("Provisioning Azure resources", 2, 5, language, stream=stream):
        pass
    assert tr("Provisioning Azure resources") in stream.getvalue()
    assert tr("completed") in stream.getvalue()
    citation = transform_citations(
        [{"type": "web", "url": "https://portal.example.edu/admissions"}],
        language=language,
    )[0]
    assert citation.label == load_catalog(language)["citations"]["web"] + " 1"
    assert validate_ui_language(language) == language
    with pytest.raises(ConfigurationError) as caught:
        validate_ui_language("xx")
    assert caught.value.render(language) == tr(
        "UI_LANGUAGE must be one of: {languages}", languages=", ".join(LANGUAGES),
    )


@pytest.mark.parametrize("relative", ["infra/main.bicep", "infra/modules/webapp.bicep"])
def test_infrastructure_accepts_exactly_the_same_languages(relative):
    source = (ROOT / relative).read_text(encoding="utf-8")
    match = re.search(
        r"@allowed\(\[([^\]]*)\]\)\s*(?:@description\([^\n]*\)\s*)?param uiLanguage string",
        source,
    )
    assert match is not None
    assert tuple(re.findall(r"'([^']+)'", match[1])) == LANGUAGES


def test_controlled_installer_message_literals_are_all_catalogued():
    keys = load_catalog("en")["installer"]
    for filename in ("wizard.py", "config.py", "cli.py", "wizard_draft.py", "install_progress.py"):
        tree = ast.parse((ROOT / "src" / "azure_bing_assistant" / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name not in {"tr", "messages", "ConfigurationError", "DiscoveryError", "CapabilityError"}:
                continue
            message = node.args[0]
            if isinstance(message, ast.Constant) and isinstance(message.value, str):
                assert message.value in keys, (filename, node.lineno, message.value)


def test_unsupported_cli_language_is_an_argument_error_not_a_translation_crash(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["install", "--ui-language", "xx"])
    assert caught.value.code == 2
    assert "xx" in capsys.readouterr().err


def test_windows_cli_reconfigures_redirected_input_output_and_errors_for_unicode(monkeypatch):
    input_bytes = BytesIO("כן\n".encode("utf-8"))
    output_bytes, error_bytes = BytesIO(), BytesIO()
    input_stream = TextIOWrapper(input_bytes, encoding="cp1252")
    output_stream = TextIOWrapper(output_bytes, encoding="cp1252")
    error_stream = TextIOWrapper(error_bytes, encoding="cp1252", errors="backslashreplace")
    with monkeypatch.context() as patch:
        patch.setattr(cli.os, "name", "nt")
        patch.setattr(cli.sys, "stdin", input_stream)
        patch.setattr(cli.sys, "stdout", output_stream)
        patch.setattr(cli.sys, "stderr", error_stream)
        cli._configure_cli_encoding()
        answer = input_stream.readline()
        output_stream.write("Ελληνικά / עברית / العربية")
        error_stream.write("שגיאה")
        output_stream.flush()
        error_stream.flush()
    assert answer == "כן\n"
    assert output_bytes.getvalue().decode("utf-8") == "Ελληνικά / עברית / العربية"
    assert error_bytes.getvalue().decode("utf-8") == "שגיאה"
    assert error_stream.errors == "backslashreplace"


@pytest.mark.skipif(os.name != "nt", reason="Windows redirected-stream regression")
@pytest.mark.parametrize("language", ["el", "he", "ar", "tr"])
@pytest.mark.parametrize("argument,code", [("--help", 0), ("--unknown", 2)])
def test_windows_cli_help_and_errors_work_with_legacy_redirected_encoding(language, argument, code):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    environment["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "azure_bing_assistant", "install", "--ui-language", language, argument],
        cwd=ROOT, env=environment, capture_output=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == code, result.stderr
    text = result.stdout if code == 0 else result.stderr
    expected_program = "azure-bing-assistant install" if code == 0 else "azure-bing-assistant"
    assert text.splitlines()[0].startswith(InstallerMessages(language)("usage: ") + expected_program)
    assert "UnicodeEncodeError" not in text
