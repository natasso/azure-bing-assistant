from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from azure_bing_assistant.config import (
    ConfigurationError,
    InstallerConfig,
    KnowledgeMode,
    validate_websites,
)
from azure_bing_assistant.wizard import (
    CapabilityError,
    AzureCliDiscovery,
    ConsolePrompts,
    DiscoveryError,
    ModelChoice,
    RegionChoice,
    SubscriptionChoice,
    WizardCancelled,
    collect_websites,
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


@pytest.mark.parametrize("answer", ["", " \t "])
def test_text_without_default_remains_required(answer):
    prompts, output = prompts_for([answer, "valid"])

    assert prompts.text("Name") == "valid"
    assert "Name is required" in output


@pytest.mark.parametrize(
    ("answer", "default", "expected", "question"),
    [
        (" example ", None, "example", "Name: "),
        ("", "10", "10", "Name [10]: "),
        (" \t ", "10", "10", "Name [10]: "),
        (" 7 ", "10", "7", "Name [10]: "),
    ],
)
def test_text_uses_only_an_explicit_default(answer, default, expected, question):
    input_fn = Mock(return_value=answer)
    prompts = ConsolePrompts(input_fn, lambda _message: None)

    assert prompts.text("Name", default=default) == expected
    input_fn.assert_called_once_with(question)


@pytest.fixture
def capacity_wizard(monkeypatch):
    def run(capacity=None, answer="", language="en", invalid_answers=()):
        model_discovery = AzureCliDiscovery()
        monkeypatch.setattr(
            model_discovery,
            "_json",
            Mock(return_value=[{
                "kind": "AIServices",
                "model": {
                    "name": "live-model",
                    "version": "2026-01-01",
                    "format": "OpenAI",
                    "skus": [{"name": "DataZoneStandard", "capacity": capacity}],
                },
            }]),
        )
        discovery = FakeDiscovery()
        discovery.models = model_discovery.models
        input_fn = Mock(side_effect=[
            "1", "2", "1", "1", *invalid_answers, answer,
            "helper", "chatbot-dev", "chat-model", "",
            "docs.example.org", "y", "n", "y",
        ])
        output = []
        config = run_wizard(
            discovery, ConsolePrompts(input_fn, output.append), ui_language=language
        )
        questions = [call.args[0] for call in input_fn.call_args_list]
        retries = len(invalid_answers)
        assert len(questions) == 13 + retries
        assert questions[4:5 + retries] == [questions[4]] * (1 + retries)
        assert questions[5 + retries:8 + retries] == [
            "Nome tecnico del chatbot: " if language == "it" else "Chatbot technical name: ",
            (
                "Nome breve dell’installazione (es. assistente-demo): "
                if language == "it"
                else "Short installation name (e.g. assistant-demo): "
            ),
            "Nome della distribuzione del modello: " if language == "it" else "Model deployment name: ",
        ]
        assert questions[-1].startswith(
            "Accettare costi e termini" if language == "it"
            else "Accept Bing grounding cost, terms, and data flow"
        )
        assert config.chatbot_name == "helper"
        assert config.environment_name == "chatbot-dev"
        assert config.model_deployment_name == "chat-model"
        assert config.websites == ("docs.example.org",)
        assert config.knowledge_mode is KnowledgeMode.OFF
        return config, questions, output

    return run


@pytest.mark.parametrize("answer", ["", " \t "])
@pytest.mark.parametrize(
    ("capacity", "expected", "bounds"),
    [
        (None, 10, ""),
        ({}, 10, ""),
        ({"minimum": None, "maximum": None, "default": None}, 10, ""),
        ({"default": 5}, 5, ""),
        ({"minimum": 20}, 20, " (minimum 20)"),
        ({"maximum": 5}, 5, " (maximum 5)"),
        ({"minimum": 1, "maximum": 50}, 10, " (minimum 1; maximum 50)"),
        ({"minimum": 20, "maximum": 30}, 20, " (minimum 20; maximum 30)"),
        ({"minimum": 1, "maximum": 5}, 5, " (minimum 1; maximum 5)"),
        ({"minimum": 5, "maximum": 5}, 5, " (minimum 5; maximum 5)"),
        ({"minimum": 1, "maximum": 50, "default": 5}, 5, " (minimum 1; maximum 50)"),
    ],
)
def test_capacity_enter_accepts_displayed_valid_default(
    capacity_wizard, capacity, expected, bounds, answer
):
    config, questions, output = capacity_wizard(capacity, answer)

    assert config.model_capacity == expected
    assert questions[4] == f"Model capacity{bounds} [{expected}]: "
    assert any(line.startswith("Native Bing-backed web_search") for line in output)
    assert "Press Enter to keep this value, or enter another value" in "\n".join(output)
    assert (
        "Model capacity is the initial request throughput quota, not the number of "
        "users, guaranteed performance, or a cost budget. Azure validates quota at deployment."
    ) in output


@pytest.mark.parametrize("language", ["it", "en"])
def test_capacity_guidance_keeps_azure_default_1000(capacity_wizard, language):
    config, questions, output = capacity_wizard({"default": 1000}, language=language)
    text = "\n".join(output)
    assert config.model_capacity == 1000 and "[1000]" in questions[4]
    assert "10 unit" in text and "100 unit" in text
    assert "max(60, 10) = 60" in text and "25%" in text and "75" in text
    assert ("NON è una conversione" if language == "it" else "NOT a conversion") in text


@pytest.mark.parametrize("sku", ["Standard", "GlobalStandard", "DataZoneStandard", "ProvisionedManaged", "GlobalProvisionedManaged", "GlobalBatch"])
@pytest.mark.parametrize("language", ["it", "en"])
def test_capacity_examples_respect_sku_bounds_and_billing(sku, language):
    from azure_bing_assistant.wizard import _capacity_guidance

    output = []
    model = ModelChoice("example-model", "1", "OpenAI", sku, 20, 80, 40)
    _capacity_guidance(model, 40, ConsolePrompts(output_fn=output.append, language=language))
    text = "\n".join(output)
    if sku in {"Standard", "GlobalStandard", "DataZoneStandard"}:
        assert text.count("non è applicabile" if language == "it" else "not applicable") == 2
        assert ("Esempio test/POC: 10" if language == "it" else "Test/POC example: 10") not in text
        assert ("token fatturati" if language == "it" else "billed tokens") in text
    else:
        assert ("addebiti diversi" if language == "it" else "different capacity-based charges") in text
        assert "25%" not in text and "10 unit" not in text and "100 unit" not in text


def test_capacity_guidance_matches_italian_language(capacity_wizard):
    config, questions, output = capacity_wizard(language="it")

    assert config.model_capacity == 10
    assert questions[4] == "Capacità del modello [10]: "
    assert (
        "Premi Invio per mantenere questo valore, oppure inserisci un altro valore "
        "(numero intero positivo)."
    ) in output
    assert (
        "La capacità del modello è la quota iniziale per la velocità di elaborazione "
        "delle richieste, non il numero di utenti, una garanzia di prestazioni o un "
        "budget di spesa. Azure convalida la quota durante la distribuzione."
    ) in output


@pytest.mark.parametrize(
    ("capacity", "answer", "expected"),
    [
        (None, " 7 ", 7),
        ({"default": 5}, "12", 12),
        ({"minimum": 20}, "20", 20),
        ({"minimum": 20}, "30", 30),
        ({"maximum": 5}, "1", 1),
        ({"maximum": 5}, "5", 5),
        ({"minimum": 2, "maximum": 20}, "2", 2),
        ({"minimum": 2, "maximum": 20}, "20", 20),
    ],
)
def test_capacity_accepts_valid_explicit_override(capacity_wizard, capacity, answer, expected):
    config, _, _ = capacity_wizard(capacity, answer)

    assert config.model_capacity == expected


@pytest.mark.parametrize("answer", ["0", "-1", "1.5", "abc", "+5", "1e2", "²", "9" * 5000])
def test_capacity_rejects_nonpositive_or_noninteger_input(capacity_wizard, answer):
    config, _, output = capacity_wizard(invalid_answers=[answer])
    assert config.model_capacity == 10
    assert "Model capacity must be a positive integer" in output


@pytest.mark.parametrize(
    ("capacity", "answer"),
    [
        ({"minimum": 20}, "19"),
        ({"maximum": 5}, "6"),
        ({"minimum": 2, "maximum": 20}, "1"),
        ({"minimum": 2, "maximum": 20}, "21"),
    ],
)
def test_capacity_rejects_override_outside_either_bound(capacity_wizard, capacity, answer):
    config, _, output = capacity_wizard(capacity, invalid_answers=[answer])
    assert capacity.get("minimum", 1) <= config.model_capacity <= capacity.get("maximum", 100)
    assert "Model capacity is outside Azure's returned SKU range" in output


@pytest.mark.parametrize("field", ["minimum", "maximum", "default"])
@pytest.mark.parametrize("value", [0, -1, 1.5, True, False, "malformed", "", [], {}])
def test_capacity_rejects_malformed_metadata_values(capacity_wizard, field, value):
    with pytest.raises(DiscoveryError, match="invalid model capacity metadata"):
        capacity_wizard({field: value})


@pytest.mark.parametrize(
    "capacity",
    [
        [], "", 0, False, "malformed",
        {"minimum": 20, "maximum": 5},
        {"minimum": 20, "default": 5},
        {"maximum": 5, "default": 10},
        {"minimum": 2, "maximum": 20, "default": 1},
        {"minimum": 2, "maximum": 20, "default": 21},
    ],
)
def test_capacity_rejects_invalid_or_contradictory_metadata(capacity_wizard, capacity):
    with pytest.raises(DiscoveryError, match="invalid model capacity metadata"):
        capacity_wizard(capacity)


@pytest.mark.parametrize(
    ("answers", "question"),
    [
        (["1", "1", ""], "New resource group name"),
        (["1", "2", "1", "1", "", ""], "Chatbot technical name"),
        (
            ["1", "2", "1", "1", "", "helper", ""],
            "Short installation name (e.g. assistant-demo)",
        ),
        (["1", "2", "1", "1", "", "helper", "chatbot-dev", ""], "Model deployment name"),
    ],
)
def test_capacity_default_does_not_make_other_wizard_text_optional(answers, question):
    prompts, output = prompts_for(answers)

    with pytest.raises(WizardCancelled):
        run_wizard(FakeDiscovery(), prompts, ui_language="en")
    assert f"{question} is required" in output


@pytest.mark.parametrize(
    ("language", "question", "help_lines"),
    [
        (
            "it",
            "Nome breve dell’installazione (es. assistente-demo): ",
            [
                "È un nome interno per salvare la configurazione dell’installer e ricavare "
                "i nomi delle risorse Azure.",
                "Può essere diverso dal nome del gruppo di risorse già scelto; "
                "non è il titolo della chat visibile ai visitatori.",
                "Usa 3–24 caratteri: lettere minuscole, cifre o trattini, iniziando con una lettera.",
                "Riusa questo nome per gli aggiornamenti: cambiarlo può generare "
                "un insieme separato di risorse.",
            ],
        ),
        (
            "en",
            "Short installation name (e.g. assistant-demo): ",
            [
                "This is an internal name used to save the installer configuration and derive "
                "Azure resource names.",
                "It can differ from the resource-group name already chosen; "
                "it is not the chat title visitors see.",
                "Use 3–24 lowercase letters, digits or hyphens, starting with a letter.",
                "Reuse this name for updates: changing it can generate a separate set of resources.",
            ],
        ),
    ],
)
def test_installation_name_help_precedes_required_question_and_preserves_config(
    language, question, help_lines
):
    answers = iter([
        "1", "2", "1", "1", "7", "helper", "my-install-2", "chat-model", "",
        "docs.example.org", "y", "n", "y",
    ])
    transcript = []
    questions = []

    def answer(prompt):
        transcript.append(prompt)
        questions.append(prompt)
        return next(answers)

    config = run_wizard(
        FakeDiscovery(), ConsolePrompts(answer, transcript.append), ui_language=language
    )

    name_index = transcript.index(question)
    chatbot_prompt = "Nome tecnico del chatbot: " if language == "it" else "Chatbot technical name: "
    deployment_prompt = (
        "Nome della distribuzione del modello: " if language == "it" else "Model deployment name: "
    )
    assert transcript.index(chatbot_prompt) < name_index < transcript.index(deployment_prompt)
    assert all(transcript.index(line) < name_index for line in help_lines)
    assert questions[5:8] == [chatbot_prompt, question, deployment_prompt]
    assert len(questions) == 13
    assert config == InstallerConfig(
        environment_name="my-install-2",
        location="westeurope",
        knowledge_mode=KnowledgeMode.OFF,
        subscription_id="sub-selected",
        resource_group_name="rg-existing",
        create_resource_group=False,
        model_name="live-model",
        model_version="2026-01-01",
        model_format="OpenAI",
        model_sku="GlobalStandard",
        model_capacity=7,
        model_deployment_name="chat-model",
        chatbot_name="helper",
        ui_language=language,
        websites=("docs.example.org",),
        bing_terms_accepted=True,
        foundry_user_role_definition_id=(
            "/subscriptions/sub-selected/providers/"
            "Microsoft.Authorization/roleDefinitions/Foundry-User"
        ),
    )


@pytest.mark.parametrize(
    ("language", "question"),
    [
        ("it", "Nome breve dell’installazione (es. assistente-demo)"),
        ("en", "Short installation name (e.g. assistant-demo)"),
    ],
)
@pytest.mark.parametrize("answer", ["", " \t "])
def test_installation_name_remains_required_in_both_languages(language, question, answer):
    prompts, output = prompts_for(["1", "2", "1", "1", "", "helper", answer])

    suffix = "è obbligatorio" if language == "it" else "is required"
    with pytest.raises(WizardCancelled):
        run_wizard(FakeDiscovery(), prompts, ui_language=language)
    assert f"{question} {suffix}" in output


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("name", ["ab", "a" * 25, "Assistant-demo", "1demo", "my_install"])
def test_installation_name_keeps_existing_validation_without_coercion(language, name):
    prompts, output = prompts_for([
        "1", "2", "1", "1", "", "helper", name, "valid-install", "chat-model", "",
        "docs.example.org", "y", "n", "y",
    ])

    message = "Nome dell'installazione deve contenere 3-24" if language == "it" else "Installation name must be 3-24"
    config = run_wizard(FakeDiscovery(), prompts, ui_language=language)
    assert config.environment_name == "valid-install"
    assert any(line.startswith(message) for line in output)


def test_capacity_default_does_not_accept_terms_implicitly():
    prompts, _ = prompts_for([
        "1", "2", "1", "1", "", "helper", "chatbot-dev", "chat-model", "",
        "docs.example.org", "y", "n", "",
    ])

    with pytest.raises(CapabilityError, match="acknowledgement is required"):
        run_wizard(FakeDiscovery(), prompts, ui_language="en")


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
            "docs.example.org", "y", "y", "https://example.net/", "y", "n",
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
        "docs.example.org",
        "example.net",
    )
    assert any("restricted to these domains" in line for line in output)
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
        "s", "n",
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
    assert any("Italiano (predefinito / default)" in line for line in output)
    search_question = next(question for question in questions if "Azure AI Search" in question)
    assert "Opzionale:" in search_question
    assert "aggiunge costi Search e Storage" in search_question
    assert any("per impostazione predefinita la ricerca web Bing" in line for line in output)
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
        "y", "n",
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


def test_wizard_always_restricts_sites_without_asking_for_broad_mode():
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
            "s", "n",
            "y",
        ]
    )

    config = run_wizard(FakeDiscovery(), prompts)
    assert config.strict_websites is True
    assert config.websites == ("docs.example.org",)


def domain_transcript(answers, language="en"):
    inputs = iter(answers)
    transcript = []
    questions = []

    def answer(question):
        questions.append(question)
        value = next(inputs)
        transcript.append(question + value)
        return value

    return ConsolePrompts(answer, transcript.append, language), transcript, questions


@pytest.mark.parametrize(
    ("language", "yes"),
    [("it", "s"), ("it", "si"), ("it", "sì"), ("it", "y"), ("it", "yes"),
     ("en", "y"), ("en", "yes"), ("en", " YES "), ("it", " SÌ ")],
)
def test_one_domain_has_explicit_subdomain_and_another_questions(language, yes):
    prompts, transcript, questions = domain_transcript(
        [" HTTPS://Example.ORG./ ", yes, " no "], language,
    )

    assert collect_websites(prompts) == ("example.org",)
    assert len(questions) == 3
    if language == "it":
        assert questions == [
            "Dominio pubblico autorizzato o URL HTTPS radice: ",
            "Includere anche i sottodomini di example.org? [s/N]: ",
            "Vuoi aggiungere un altro dominio? [s/N]: ",
        ]
        assert "  example.org: con sottodomini" in transcript
    else:
        assert questions == [
            "Authorized public domain or root HTTPS URL: ",
            "Include subdomains of example.org? [y/N]: ",
            "Add another domain? [y/N]: ",
        ]
        assert "  example.org: with subdomains" in transcript


@pytest.mark.parametrize("language", ["it", "en"])
def test_domain_loop_normalizes_each_domain_and_keeps_www(language):
    prompts, _, questions = domain_transcript([
        "https://Example.ORG/", "yes", "yes",
        "WWW.Example.NET.", "y", "yes",
        "https://bücher.example/", "y", "n",
    ], language)
    assert collect_websites(prompts) == (
        "example.org", "www.example.net", "xn--bcher-kva.example",
    )
    assert len(questions) == 9


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("invalid", [
    "", " \t ", "https://example.org/path", "*.example.org",
    "example.org,example.net", "https://user:secret@example.org/",
    "https://example.org/?secret=value", "127.0.0.1", "example.org:443",
])
def test_invalid_domain_reprompts_immediately_without_skipping_entry(language, invalid):
    prompts, transcript, questions = domain_transcript(
        [invalid, "example.org", "yes", "n"], language,
    )
    assert collect_websites(prompts) == ("example.org",)
    assert questions[0] == questions[1]
    assert len(questions) == 4
    error = transcript[transcript.index(questions[0] + invalid) + 1]
    if invalid.strip():
        assert error.startswith("Dominio non valido:" if language == "it" else "Invalid domain:")
    else:
        assert error.endswith("è obbligatorio" if language == "it" else "is required")
    assert "secret" not in error


@pytest.mark.parametrize("language", ["it", "en"])
def test_duplicate_canonical_host_requires_different_domain(language):
    prompts, transcript, questions = domain_transcript([
        "https://EXAMPLE.ORG./", "yes", "yes",
        "example.org", "example.net", "yes", "no",
    ], language)
    assert collect_websites(prompts) == ("example.org", "example.net")
    assert questions[3] == questions[4]
    assert any(
        "example.org è già stato inserito" in line if language == "it"
        else "example.org was already entered" in line for line in transcript
    )
    assert len(questions) == 7


@pytest.mark.parametrize("language", ["it", "en"])
def test_duplicate_cannot_overwrite_a_host_only_policy(language):
    prompts, transcript, questions = domain_transcript([
        "example.org", "no", "yes",
        "https://EXAMPLE.ORG./", "yes", "example.net", "yes", "no",
    ], language)
    with pytest.raises(CapabilityError) as caught:
        collect_websites(prompts)
    assert "example.org" in str(caught.value)
    assert "example.net" not in str(caught.value)
    assert len(questions) == 8
    assert "  example.org: " + ("solo questo host" if language == "it" else "only this host") in transcript


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("negative", ["n", "no", " NO ", "", " \t "])
def test_mixed_host_only_policy_is_summarized_then_blocked_before_terms(language, negative):
    prompts, transcript, questions = domain_transcript([
        "1", "2", "1", "1", "", "helper", "chatbot-dev", "chat-model", "",
        "example.org", negative, "yes", "https://example.net/", "yes", "no",
    ], language)
    discovery = FakeDiscovery()
    discovery.role_definition = Mock(side_effect=AssertionError("must stop before role lookup"))
    with pytest.raises(CapabilityError) as caught:
        run_wizard(discovery, prompts, ui_language=language)
    assert "example.org" in str(caught.value)
    assert "example.net" not in str(caught.value)
    assert not any("Accettare costi" in question or "Accept Bing" in question for question in questions)
    assert not any(value in str(caught.value) for value in ("sub-selected", "tenant-selected"))
    if language == "it":
        assert "questo installer non ha creato risorse" in str(caught.value)
        assert "  example.org: solo questo host" in transcript
        assert "  example.net: con sottodomini" in transcript
    else:
        assert "no resources were created by this installer" in str(caught.value)
        assert "  example.org: only this host" in transcript
        assert "  example.net: with subdomains" in transcript
    discovery.role_definition.assert_not_called()


@pytest.mark.parametrize("language", ["it", "en"])
def test_invalid_yes_no_repeats_same_question_and_does_not_move_domain(language):
    prompts, transcript, questions = domain_transcript([
        "example.org", "maybe", "1", "yes", "perhaps", "n",
    ], language)
    assert collect_websites(prompts) == ("example.org",)
    assert questions[1] == questions[2] == questions[3]
    assert questions[4] == questions[5]
    assert transcript.count("Rispondi sì o no" if language == "it" else "Answer yes or no") == 3


def test_domain_limit_is_100_distinct_not_number_of_attempts():
    answers = []
    for index in range(100):
        if index:
            answers.append(f"EXAMPLE{index - 1}.ORG.")
        answers.extend([f"example{index}.org", "yes"])
        if index != 99:
            answers.append("yes")
    prompts, transcript, questions = domain_transcript(answers)
    domains = collect_websites(prompts)
    assert len(domains) == 100
    assert domains[-1] == "example99.org"
    assert "Maximum of 100 distinct domains reached." in transcript
    assert len(questions) == len(answers)


@pytest.mark.parametrize("exception", [EOFError, StopIteration, KeyboardInterrupt])
@pytest.mark.parametrize("language", ["it", "en"])
def test_input_ending_is_cancelled_not_an_endless_domain_retry(exception, language):
    input_fn = Mock(side_effect=["", "bad/path", exception()])
    output = []
    with pytest.raises(WizardCancelled, match="annullata" if language == "it" else "cancelled"):
        collect_websites(ConsolePrompts(input_fn, output.append, language))
    assert input_fn.call_count == 3


@pytest.mark.parametrize("language", ["it", "en"])
def test_entire_wizard_uses_selected_language(language):
    prompts, transcript, questions = domain_transcript([
        "1", "2", "1", "1", "", "helper", "chatbot-dev", "chat-model", "no",
        "example.org", "yes", "no", "yes",
    ])
    config = run_wizard(FakeDiscovery(), prompts, ui_language=language)
    assert config.ui_language == language
    text = "\n".join(transcript)
    italian = [
        "Scegli un tenant", "Crea un nuovo gruppo di risorse", "Scegli una regione",
        "Scegli modello", "Capacità del modello", "Nome tecnico del chatbot",
        "Nome della distribuzione del modello", "Opzionale:", "Seleziona un numero",
        "Accettare costi", "Policy richieste per i domini:",
    ]
    english = [
        "Choose a signed-in", "Create a new resource group", "Choose an Azure region",
        "Choose a model", "Model capacity", "Chatbot technical name", "Model deployment name",
        "Optional:", "Select a number", "Accept Bing", "Requested domain policies:",
    ]
    expected, absent = (italian, english) if language == "it" else (english, italian)
    assert all(fragment in text for fragment in expected)
    assert all(fragment not in text for fragment in absent)
    assert not any(" / Select a number" in question for question in questions)


def test_prompt_instances_do_not_share_language_or_consent_defaults():
    italian_output, english_output = [], []
    italian = ConsolePrompts(Mock(side_effect=["sì", "", "x", "1"]), italian_output.append, "it")
    english = ConsolePrompts(Mock(side_effect=["sì", "yes", "", "x", "1"]), english_output.append, "en")
    assert italian.yes_no("Confermare?")
    assert english.yes_no("Confirm?")
    assert not italian.yes_no("Accettare?")
    assert not english.yes_no("Accept?")
    assert italian.select("Scelta", ["a"]) == 0
    assert english.select("Choice", ["a"]) == 0
    assert any(line.startswith("La selezione") for line in italian_output)
    assert any(line.startswith("Selection") for line in english_output)
    assert english.input.call_count == 5


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("default, answer, expected", [(None, "2", 1), (0, "", 0)])
def test_select_retries_malformed_values_and_shows_range(language, default, answer, expected):
    invalid = ["0", "-1", "3", "no", "1.5", "²", "9" * 5000]
    if default is None:
        invalid.append("")
    prompts, transcript, questions = domain_transcript([*invalid, answer], language)
    assert prompts.select("Choice", ["a", "b"], default_index=default) == expected
    assert len(questions) == len(invalid) + 1
    assert len(set(questions)) == 1
    assert any("1 a 2" in line if language == "it" else "1 to 2" in line for line in transcript[:4])
    assert sum(
        line.startswith("La selezione" if language == "it" else "Selection")
        for line in transcript
    ) == len(invalid)


@pytest.mark.parametrize("default", [-1, 2, 0.5, True, "1"])
def test_invalid_menu_default_is_not_a_user_retry(default):
    input_fn = Mock(side_effect=AssertionError("must not ask"))
    with pytest.raises(ConfigurationError, match="Default selection"):
        ConsolePrompts(input_fn).select("Choice", ["a", "b"], default)
    input_fn.assert_not_called()


def test_empty_provider_choices_are_not_a_user_retry():
    input_fn = Mock(side_effect=AssertionError("must not ask"))
    with pytest.raises(DiscoveryError, match="No choices"):
        ConsolePrompts(input_fn).select("Choice", [])
    input_fn.assert_not_called()


@pytest.mark.parametrize("default", ["", " \t ", "invalid"])
def test_invalid_text_defaults_fail_before_reading(default):
    input_fn = Mock(side_effect=AssertionError("must not ask"))

    def validate(value):
        raise ConfigurationError("Invalid default")

    with pytest.raises(ConfigurationError):
        ConsolePrompts(input_fn).text("Name", default, validator=validate)
    input_fn.assert_not_called()


@pytest.mark.parametrize("exception", [RuntimeError, OSError, DiscoveryError])
def test_unexpected_validator_failure_is_not_retried(exception):
    input_fn = Mock(return_value="valid")
    validator = Mock(side_effect=exception("provider failure"))
    with pytest.raises(exception, match="provider failure"):
        ConsolePrompts(input_fn).text("Name", validator=validator)
    input_fn.assert_called_once()
    validator.assert_called_once()


@pytest.mark.parametrize("method", ["text", "select", "yes_no"])
@pytest.mark.parametrize("exception", [EOFError, StopIteration, KeyboardInterrupt])
def test_retry_can_be_cancelled_without_looping(method, exception):
    input_fn = Mock(side_effect=["", exception()] if method == "text" else ["bad", exception()])
    prompts = ConsolePrompts(input_fn, lambda _: None)
    arguments = (["a"],) if method == "select" else ()
    with pytest.raises(WizardCancelled):
        getattr(prompts, method)("Question", *arguments)
    assert input_fn.call_count == 2


def test_two_full_wizards_keep_independent_languages_after_retries():
    instances = []
    for language in ("it", "en"):
        prompts, output = prompts_for([
            "1", "2", "1", "1", "", "Tor Vergata", "helper",
            "chatbot-dev", "chat-model", "", "example.org", "yes", "no", "yes",
        ])
        config = run_wizard(FakeDiscovery(), prompts, ui_language=language)
        assert config.ui_language == language
        instances.append((prompts, output))
    italian, english = instances
    assert italian[0].messages.language == "it"
    assert english[0].messages.language == "en"
    assert any("Nome tecnico del chatbot deve" in line for line in italian[1])
    assert not any("Chatbot technical name must" in line for line in italian[1])
    assert any("Chatbot technical name must" in line for line in english[1])
    assert not any("Nome tecnico del chatbot deve" in line for line in english[1])


@pytest.mark.parametrize("language", ["it", "en"])
def test_full_wizard_validates_every_field_before_advancing_without_rediscovery(language, monkeypatch):
    malformed_menu = ["bad", "0", "999", "²", "9" * 5000]
    steps = [
        ([*malformed_menu, ""], "1" if language == "it" else "2"),
        ([*malformed_menu, ""], "1"),
        ([*malformed_menu, ""], "1"),
        (["", "bad group", "a" * 91, "rg/bad"], "rg-valid"),
        ([*malformed_menu, ""], "1"),
        ([*malformed_menu, ""], "1"),
        (["0", "-1", "1.2", "text", "1", "21", "9" * 5000], "7"),
        (["", "Tor Vergata", "UPPER", "ab", "a" * 25], "helper-valid"),
        (["", "My University", "UPPER", "ab", "a" * 25], "install-valid"),
        (["", "chat model", "/route", "a" * 129], "chat-model"),
        (["maybe"], "no"),
        (["", "https://example.org/path"], "example.org"),
        (["maybe"], "yes"),
        (["maybe"], "no"),
        (["maybe"], "yes"),
    ]
    # Language has an Enter default; blank must accept it, not retry.
    steps[0] = (malformed_menu, steps[0][1])
    prompts, transcript, questions = domain_transcript(
        [value for invalid, valid in steps for value in [*invalid, valid]]
    )
    discovery = Mock(wraps=FakeDiscovery())
    discovery.models.return_value = [
        ModelChoice("live-model", "2026-01-01", "OpenAI", "GlobalStandard", 2, 20, 5)
    ]
    final_validation = Mock(wraps=InstallerConfig.__post_init__)
    monkeypatch.setattr(InstallerConfig, "__post_init__", lambda self: final_validation(self))
    config = run_wizard(discovery, prompts)
    assert config.ui_language == language
    assert config.chatbot_name == "helper-valid"
    assert config.environment_name == "install-valid"
    assert config.resource_group_name == "rg-valid"
    assert config.model_deployment_name == "chat-model"
    assert config.model_capacity == 7
    assert config.subscription_id == "sub-selected"
    assert config.location == "westeurope"
    assert config.model_name == "live-model"
    assert config.knowledge_mode is KnowledgeMode.OFF
    assert config.websites == ("example.org",)
    config.require_complete_install()
    final_validation.assert_called_once_with(config)
    for method in ("subscriptions", "resource_groups", "regions", "models", "role_definition"):
        getattr(discovery, method).assert_called_once()
    offset = 0
    for invalid, valid in steps:
        question = questions[offset]
        assert questions[offset:offset + len(invalid) + 1] == [question] * (len(invalid) + 1)
        for value in invalid:
            line = transcript.index(question + value)
            following = transcript.index(question + valid, line + 1)
            assert following > line + 1  # Error feedback occurs before the retry answer.
        offset += len(invalid) + 1
    assert offset == len(questions)
    text = "\n".join(transcript)
    name_error = (
        "Nome tecnico del chatbot deve contenere 3-24"
        if language == "it" else "Chatbot technical name must be 3-24"
    )
    assert name_error in text
    assert "chatbot_name" not in text and "environment_name" not in text
    for hint, question in [
        ("1-90", questions[sum(len(bad) + 1 for bad, _ in steps[:3])]),
        ("3-24", questions[sum(len(bad) + 1 for bad, _ in steps[:7])]),
        ("1-128", questions[sum(len(bad) + 1 for bad, _ in steps[:9])]),
        ("https://example.org/", questions[sum(len(bad) + 1 for bad, _ in steps[:11])]),
    ]:
        hint_line = next(index for index, line in enumerate(transcript) if hint in line)
        first_prompt = next(index for index, line in enumerate(transcript) if line.startswith(question))
        assert hint_line < first_prompt


@pytest.mark.parametrize("language", ["it", "en"])
def test_discovery_and_capacity_validation_errors_are_localized(language):
    prompts, _, _ = domain_transcript(["1", "2", "1"])
    discovery = FakeDiscovery()
    discovery.models = Mock(side_effect=DiscoveryError(
        "Azure returned invalid model capacity metadata: {field} must be a positive integer",
        field="default_capacity",
    ))
    with pytest.raises(DiscoveryError, match="metadati di capacità non validi" if language == "it" else "invalid model capacity metadata"):
        run_wizard(discovery, prompts, ui_language=language)


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


@pytest.fixture
def region_cli(monkeypatch):
    invocation = Mock(
        side_effect=lambda args: (["python", "-IBm", "azure.cli", *args[1:]], {"SAFE": "yes"})
    )
    run = Mock(return_value=Mock(returncode=0, stdout='{"value": []}', stderr=""))
    monkeypatch.setattr("azure_bing_assistant.wizard.azure_cli_invocation", invocation)
    monkeypatch.setattr("azure_bing_assistant.wizard.subprocess.run", run)
    return invocation, run


@pytest.mark.parametrize(
    ("subscription_id", "encoded_id"),
    [
        ("selected-subscription", "selected-subscription"),
        ("selected/subscription?#% value", "selected%2Fsubscription%3F%23%25%20value"),
    ],
)
def test_regions_use_selected_subscription_in_rest_url_and_token_scope(
    region_cli, subscription_id, encoded_id
):
    invocation, run = region_cli
    run.return_value.stdout = json.dumps(
        {
            "value": [
                {
                    "id": f"/subscriptions/{subscription_id}/locations/westeurope",
                    "name": "westeurope",
                    "displayName": "West Europe",
                    "regionalDisplayName": "(Europe) West Europe",
                    "metadata": {"regionType": "Physical"},
                },
                {"name": "brazilsouth", "displayName": ""},
                {"name": "eastus", "displayName": "East US"},
                {"name": "australiaeast"},
                {"name": "centralus", "displayName": None},
                {"displayName": "Missing name"},
            ]
        }
    )

    choices = AzureCliDiscovery().regions(subscription_id)

    assert choices == [
        RegionChoice("australiaeast", "australiaeast"),
        RegionChoice("brazilsouth", "brazilsouth"),
        RegionChoice("centralus", "centralus"),
        RegionChoice("eastus", "East US"),
        RegionChoice("westeurope", "West Europe"),
    ]
    args = [
        "az",
        "rest",
        "--method",
        "get",
        "--subscription",
        subscription_id,
        "--url",
        f"/subscriptions/{encoded_id}/locations?api-version=2022-12-01",
        "--output",
        "json",
    ]
    invocation.assert_called_once_with(args)
    run.assert_called_once_with(
        ["python", "-IBm", "azure.cli", *args[1:]],
        env={"SAFE": "yes"},
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("rows", [[], [{"displayName": "Missing name"}]])
def test_regions_reject_no_available_regions(region_cli, rows):
    _, run = region_cli
    run.return_value.stdout = json.dumps({"value": rows})

    with pytest.raises(DiscoveryError, match="Azure returned no available regions"):
        AzureCliDiscovery().regions("selected-subscription")

    run.assert_called_once()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "malformed",
        {},
        {"value": None},
        {"value": {}},
        {"value": "malformed"},
        {"value": [None]},
        {"value": [{"name": "eastus"}, "malformed"]},
    ],
)
def test_regions_reject_malformed_rest_responses(region_cli, payload):
    _, run = region_cli
    run.return_value.stdout = json.dumps(payload)

    with pytest.raises(DiscoveryError, match="Azure returned an invalid regions response"):
        AzureCliDiscovery().regions("selected-subscription")

    run.assert_called_once()


@pytest.mark.parametrize(
    ("returncode", "stdout", "detail"),
    [
        (1, '{"value": [{"name": "eastus"}]}', "could not return the requested choices"),
        (0, "not JSON", "returned invalid JSON"),
    ],
)
def test_regions_preserve_cli_errors_without_exposing_output(
    region_cli, returncode, stdout, detail
):
    _, run = region_cli
    run.return_value = Mock(
        returncode=returncode, stdout=stdout, stderr="sensitive-cli-output"
    )

    with pytest.raises(DiscoveryError, match=f"Azure region discovery failed: .*{detail}") as error:
        AzureCliDiscovery().regions("selected-subscription")

    assert isinstance(error.value.__cause__, DiscoveryError)
    assert "sensitive-cli-output" not in str(error.value)
    assert stdout not in str(error.value)
    run.assert_called_once()


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
