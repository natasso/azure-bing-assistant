from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from azure_bing_assistant.config import ConfigurationError, KnowledgeMode, validate_websites
from azure_bing_assistant.wizard import (
    CapabilityError,
    AzureCliDiscovery,
    ConsolePrompts,
    DiscoveryError,
    ModelChoice,
    RegionChoice,
    SubscriptionChoice,
    run_wizard,
)


class FakeDiscovery:
    def subscriptions(self):
        return [SubscriptionChoice("Development", "sub-selected", "tenant-selected")]

    def resource_groups(self, subscription_id):
        assert subscription_id == "sub-selected"
        return ["rg-existing"]

    def regions(self, subscription_id):
        return [RegionChoice("westeurope", "West Europe")]

    def models(self, subscription_id, location):
        assert location == "westeurope"
        return [ModelChoice("live-model", "2026-01-01", "OpenAI", "GlobalStandard")]

    def role_definition(self, subscription_id, accepted_names):
        return (
            f"/subscriptions/{subscription_id}/providers/"
            f"Microsoft.Authorization/roleDefinitions/{accepted_names[0].replace(' ', '-')}"
        )


def prompts_for(answers):
    values = iter(answers)
    output = []
    return ConsolePrompts(lambda question: next(values), output.append), output


def test_interactive_answers_are_collected_from_real_discovery_choices():
    prompts, output = prompts_for(
        [
            "2",
            "1",
            "1",
            "rg-new",
            "1",
            "1",
            "10",
            "helper",
            "chatbot-dev",
            "chat-model",
            "y",
            "docs.example.org,https://example.net/reference",
            "n",
            "y",
        ]
    )

    config = run_wizard(FakeDiscovery(), prompts)

    assert config.subscription_id == "sub-selected"
    assert config.ui_language == "en"
    assert config.resource_group_name == "rg-new"
    assert config.create_resource_group is True
    assert config.knowledge_mode is KnowledgeMode.SEARCH_BLOB
    assert config.model_name == "live-model"
    assert config.websites == (
        "https://docs.example.org",
        "https://example.net/reference",
    )
    assert any("advisory" in line for line in output)
    assert any("Document search is optional and off" in line for line in output)
    assert not any(
        term in line.lower()
        for line in output
        for term in ("entra", "application registration", "visitor login")
    )


def test_default_wizard_path_keeps_document_search_off_and_names_extra_cost():
    answers = iter([
        "",
        "1",
        "1",
        "rg-new",
        "1",
        "1",
        "10",
        "helper",
        "chatbot-dev",
        "chat-model",
        "",
        "docs.example.org",
        "n",
        "y",
    ])
    questions = []
    output = []

    def answer(question):
        questions.append(question)
        return next(answers)

    config = run_wizard(FakeDiscovery(), ConsolePrompts(answer, output.append))

    assert config.knowledge_mode is KnowledgeMode.OFF
    assert config.ui_language == "it"
    assert any("Italiano (default)" in line for line in output)
    search_question = next(question for question in questions if "Azure AI Search" in question)
    assert "Optional:" in search_question
    assert "adds Search and Storage costs" in search_question
    assert any("Bing web grounding by default" in line for line in output)
    assert not any(
        term in question.lower()
        for question in questions
        for term in ("entra", "application registration", "visitor login")
    )


def test_explicit_language_skips_interactive_language_question():
    answers = iter([
        "1",
        "1",
        "rg-new",
        "1",
        "1",
        "10",
        "helper",
        "chatbot-dev",
        "chat-model",
        "n",
        "docs.example.org",
        "n",
        "y",
    ])
    questions = []

    def answer(question):
        questions.append(question)
        return next(answers)

    config = run_wizard(
        FakeDiscovery(),
        ConsolePrompts(answer, lambda _message: None),
        ui_language="en",
    )

    assert config.ui_language == "en"
    assert not any("interface language" in question for question in questions)


def test_strict_site_request_fails_closed():
    prompts, _ = prompts_for(
        [
            "",
            "1",
            "2",
            "1",
            "1",
            "10",
            "helper",
            "chatbot-dev",
            "chat-model",
            "n",
            "docs.example.org",
            "y",
        ]
    )

    with pytest.raises(CapabilityError, match="Web Knowledge Source"):
        run_wizard(FakeDiscovery(), prompts)


@pytest.mark.parametrize(
    "site",
    [
        "http://example.org",
        "https://user:pass@example.org",
        "https://example.org?secret=value",
        "https://127.0.0.1",
        "localhost",
    ],
)
def test_unsafe_or_nonpublic_sites_are_rejected(site):
    with pytest.raises(ConfigurationError):
        validate_websites([site])


def test_discovery_uses_live_azure_cli_json_and_argv(monkeypatch):
    payload = [
        {
            "model": {
                "name": "available-model",
                "version": "2026-01-01",
                "format": "OpenAI",
            },
            "skus": [
                {
                    "name": "RegionalStandard",
                    "capacity": {"minimum": 1, "maximum": 50, "default": 5},
                }
            ],
        }
    ]
    completed = Mock(returncode=0, stdout=json.dumps(payload), stderr="")
    run = Mock(return_value=completed)
    monkeypatch.setattr(
        "azure_bing_assistant.wizard.subprocess.run",
        run,
    )
    monkeypatch.setattr(
        "azure_bing_assistant.wizard.azure_cli_invocation",
        lambda args: (list(args), {"SAFE": "yes"}),
    )

    choices = AzureCliDiscovery().models("selected-subscription", "westeurope")

    assert choices[0].name == "available-model"
    assert choices[0].maximum_capacity == 50
    assert run.call_args.args[0] == [
        "az",
        "cognitiveservices",
        "model",
        "list",
        "--location",
        "westeurope",
        "--subscription",
        "selected-subscription",
        "--output",
        "json",
    ]
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["env"] == {"SAFE": "yes"}


def test_discovery_parses_nested_live_model_skus(monkeypatch):
    payload = [
        {
            "kind": "OpenAI",
            "model": {
                "name": "gpt-5.4",
                "version": "2026-03-05",
                "format": "OpenAI",
                "skus": [{"name": "GlobalStandard", "capacity": {"default": 10}}],
            },
        },
        {
            "kind": "AIServices",
            "model": {
                "name": "gpt-5.4",
                "version": "2026-03-05",
                "format": "OpenAI",
                "skus": [
                    {
                        "name": "DataZoneStandard",
                        "capacity": {
                            "minimum": None,
                            "maximum": 1000000,
                            "default": 10,
                        },
                    },
                    {
                        "name": "GlobalStandard",
                        "capacity": {
                            "minimum": None,
                            "maximum": 1000000,
                            "default": 10,
                        },
                    },
                ],
            },
        }
    ]
    monkeypatch.setattr(
        "azure_bing_assistant.wizard.azure_cli_invocation",
        lambda args: (list(args), {}),
    )
    monkeypatch.setattr(
        "azure_bing_assistant.wizard.subprocess.run",
        Mock(return_value=Mock(returncode=0, stdout=json.dumps(payload), stderr="")),
    )

    choices = AzureCliDiscovery().models("sanitized-subscription", "italynorth")

    assert [(choice.name, choice.version, choice.model_format, choice.sku) for choice in choices] == [
        ("gpt-5.4", "2026-03-05", "OpenAI", "DataZoneStandard"),
        ("gpt-5.4", "2026-03-05", "OpenAI", "GlobalStandard"),
    ]
    assert all(choice.default_capacity == 10 for choice in choices)
    assert all(choice.maximum_capacity == 1000000 for choice in choices)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        [{"kind": "AIServices", "model": {"name": "gpt-5.4", "version": "1", "format": "OpenAI"}}],
        [{"kind": "AIServices", "model": {"name": "gpt-5.4", "version": "1", "format": "OpenAI", "skus": {}}}],
        [{"model": "malformed"}],
    ],
)
def test_discovery_rejects_empty_or_malformed_model_skus(monkeypatch, payload):
    monkeypatch.setattr(
        "azure_bing_assistant.wizard.azure_cli_invocation",
        lambda args: (list(args), {}),
    )
    monkeypatch.setattr(
        "azure_bing_assistant.wizard.subprocess.run",
        Mock(return_value=Mock(returncode=0, stdout=json.dumps(payload), stderr="")),
    )

    with pytest.raises(DiscoveryError, match="no deployable model/SKU"):
        AzureCliDiscovery().models("sanitized-subscription", "italynorth")
