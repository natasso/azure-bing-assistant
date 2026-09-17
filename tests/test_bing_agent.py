"""Offline Bing Custom Search contracts using the installed Azure/OpenAI SDK models."""

import asyncio
import copy
import json
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import AgentDetails, WebSearchConfiguration, WebSearchTool, WebSearchToolFilters
from azure.core.credentials import AccessToken
from azure.core.pipeline.transport import HttpResponse, HttpTransport
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from openai.types.responses import Response

from app.backend import main as backend_main
from app.backend.config import AppSettings
from azure_bing_assistant.agent import (
    AgentResponse,
    AgentToolOrchestrator,
    FoundryAgentAdapter,
    FoundrySdkWriter,
    SearchDocumentSource,
    SourcePolicyError,
    VerifiedAgentContext,
    validate_response_evidence,
    validate_tool_policy,
)
from azure_bing_assistant.bing_binding import BingCustomSearchBinding


ENDPOINT = "https://offline.services.ai.azure.com/api/projects/project"
CONNECTION_ID = (
    "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/offline-rg"
    "/providers/Microsoft.CognitiveServices/accounts/offline/projects/project/connections/bing-custom"
)
BINDING = BingCustomSearchBinding(CONNECTION_ID, "approved-sites")
DOMAINS = ("approved.example",)
URL = "https://sub.approved.example/source?q=1"
DOCUMENT = SearchDocumentSource("offlinestorage", "documents")
DOCUMENT_URL = "https://offlinestorage.blob.core.windows.net/documents/handbook.pdf"
SEARCH_TOOL = {
    "type": "azure_ai_search",
    "azure_ai_search": {
        "indexes": [{"project_connection_id": "offline-search", "index_name": "documents"}],
    },
}


def web_tool(binding=BINDING):
    return WebSearchTool(
        filters=WebSearchToolFilters(allowed_domains=list(DOMAINS)),
        **(
            {"custom_search_configuration": WebSearchConfiguration(**binding.as_dict())}
            if binding is not None else {}
        ),
    ).as_dict()


def response_payload(search=False):
    tools = [web_tool()]
    output = [
        {
            "type": "web_search_call", "id": "web-1", "status": "completed",
            "action": {
                "type": "search", "query": "offline query",
                "sources": [{"type": "url", "url": URL}],
            },
        },
        {
            "type": "message", "id": "message-1", "status": "completed", "role": "assistant",
            "content": [{
                "type": "output_text", "text": "Offline answer",
                "annotations": [{
                    "type": "url_citation", "title": "Approved source", "url": URL,
                    "start_index": 0, "end_index": 7,
                }],
            }],
        },
    ]
    if search:
        tools.append(copy.deepcopy(SEARCH_TOOL))
        output.insert(0, {
            "type": "azure_ai_search_call", "id": "search-1", "status": "completed",
            "results": [{"url": DOCUMENT_URL}],
        })
        output[-1]["content"][0]["annotations"].append({
            "type": "url_citation", "title": "Handbook", "url": DOCUMENT_URL,
            "start_index": 0, "end_index": 7,
        })
    return {
        "id": "resp-bing", "object": "response", "created_at": 0, "status": "completed",
        "model": "offline-model", "parallel_tool_calls": True, "tool_choice": "auto",
        "tools": tools, "output": output,
    }


VERIFIED_AGENT = VerifiedAgentContext("offline-agent", "7", BINDING)
AGENT_REFERENCE = {"type": "agent_reference", "name": "offline-agent", "version": "7"}


def projected_response_payload(search=False):
    """Observed Foundry reflection shape, with synthetic identifiers and evidence."""
    payload = response_payload(search)
    payload["tools"][0].pop("custom_search_configuration")
    payload["tools"][0].update(
        search_context_size="medium", user_location=None,
        return_token_budget=10000, search_content_types=["text"],
    )
    payload["output"].insert(0, {"type": "reasoning", "id": "reasoning-1", "summary": []})
    for item in payload["output"]:
        item["agent_reference"] = dict(AGENT_REFERENCE)
        item["response_id"] = payload["id"]
    return payload


def test_binding_is_frozen_and_preserves_full_project_identity():
    assert BINDING.connection_name == "bing-custom"
    assert BINDING.as_dict() == {
        "project_connection_id": CONNECTION_ID, "instance_name": "approved-sites",
    }
    assert BingCustomSearchBinding(CONNECTION_ID.upper(), "approved-sites").identity == BINDING.identity
    assert BingCustomSearchBinding(CONNECTION_ID, "Approved-sites").identity != BINDING.identity
    with pytest.raises(FrozenInstanceError):
        BINDING.instance_name = "other"


@pytest.mark.parametrize("connection_id", [
    "", "bing-custom", "https://example.org/connection", "https://management.azure.com" + CONNECTION_ID,
    CONNECTION_ID + "/", CONNECTION_ID + "?api-version=1", CONNECTION_ID + "#fragment",
    CONNECTION_ID + "\n", CONNECTION_ID + "\t", CONNECTION_ID + "\x00", CONNECTION_ID + " ",
    " " + CONNECTION_ID, CONNECTION_ID.replace("/projects/project", ""),
    CONNECTION_ID.replace("11111111-2222-3333-4444-555555555555", "subscription"),
    CONNECTION_ID.replace("Microsoft.CognitiveServices", "Microsoft.MachineLearningServices"),
    CONNECTION_ID.replace("/project/", "/../"),
    CONNECTION_ID.replace("/project/", "/%70roject/"),
    CONNECTION_ID.replace("/project/", "/project\\other/"),
    CONNECTION_ID.replace("offline-rg", "offline-rg."),
    CONNECTION_ID.replace("bing-custom", "x" * 129),
    None, 1,
])
def test_binding_rejects_unscoped_or_unsafe_connection_identifiers(connection_id):
    with pytest.raises(ValueError):
        BingCustomSearchBinding(connection_id, "approved-sites")


@pytest.mark.parametrize("name", [
    "", "approved sites", " approved", "approved ", "approved\n", "../sites", "sites/path",
    "sites?key=value", "sites#fragment", "https://example.org", "\x00", "x" * 129, None, 1,
    "a", "9", "x" * 51, ".sites", "_sites", "-sites", "éxample", "aé", "a\t",
])
def test_binding_rejects_unsafe_configuration_names(name):
    with pytest.raises(ValueError):
        BingCustomSearchBinding(CONNECTION_ID, name)


@pytest.mark.parametrize("name", ["aB", "01", "A_", "9.", "z-", "Default", "Mixed_case.Name-9", "X" * 50])
def test_binding_accepts_portal_configuration_names_without_normalizing_case(name):
    binding = BingCustomSearchBinding(CONNECTION_ID, name)
    assert binding.instance_name == name
    assert binding.identity == (CONNECTION_ID.casefold(), name)
    assert binding.as_dict()["instance_name"] == name


@pytest.mark.parametrize("search", [False, True])
def test_orchestrator_serializes_additive_binding_and_retains_document_search(search):
    class Writer:
        def configure_agent(self, name, tools, instructions):
            assert name == "offline-agent"
            assert tools[0] == web_tool()
            assert len(tools) == (2 if search else 1)
            assert "authorized domains approved.example" in instructions
            if search:
                assert tools[1]["connection"] == "documents-connection"
            return "created"

    AgentToolOrchestrator(Writer(), "offline-agent").configure_tools(
        DOMAINS, "documents" if search else None, "documents-connection" if search else None,
        bing_custom_search=BINDING,
    )


class Credential:
    def get_token(self, *scopes, **kwargs):
        return AccessToken("offline-synthetic-token", 4102444800)


class JsonResponse(HttpResponse):
    def __init__(self, request, payload, status=200):
        super().__init__(request, None)
        self.status_code = status
        self.headers = {"content-type": "application/json"}
        self._body = json.dumps(payload).encode()

    def body(self):
        return self._body

    def json(self):
        return json.loads(self._body)


class BingTransport(HttpTransport):
    def __init__(self, connection_changes=None, mutate_definition=None, reject=False):
        self.requests = []
        self.connection_changes = connection_changes or {}
        self.mutate_definition = mutate_definition
        self.reject = reject

    def open(self):
        pass

    def close(self):
        pass

    def __exit__(self, *_):
        self.close()

    def send(self, request, **kwargs):
        self.requests.append(request)
        if "/connections/" in request.url:
            assert request.method == "GET"
            assert not any(
                value == ["true"] for key, value in parse_qs(urlsplit(request.url).query).items()
                if "credential" in key.lower()
            )
            if "/connections/bing-custom" in request.url:
                return JsonResponse(request, {
                    "id": CONNECTION_ID, "name": "bing-custom",
                    "type": "GroundingWithCustomSearch", "target": "https://api.bing.microsoft.com/",
                    "isDefault": False, "metadata": {},
                    **self.connection_changes,
                })
            assert "/connections/documents-connection" in request.url
            return JsonResponse(request, {
                "id": "offline-search", "name": "documents-connection",
                "type": "AzureAISearch", "target": "https://offline.search.windows.net",
            })
        assert request.method == "POST" and "/agents/offline-agent/versions" in request.url
        if self.reject:
            return JsonResponse(request, {"error": {"message": "PRIVATE_PROVIDER_BODY"}}, 400)
        definition = json.loads(request.body)["definition"]
        if self.mutate_definition is not None:
            self.mutate_definition(definition)
        return JsonResponse(request, {
            "id": "offline-agent:7", "name": "offline-agent", "version": "7",
            "object": "agent.version", "created_at": 0, "metadata": {}, "definition": definition,
        })


def configure(transport, search=False):
    with AIProjectClient(endpoint=ENDPOINT, credential=Credential(), transport=transport) as project:
        writer = FoundrySdkWriter(ENDPOINT, Credential(), "offline-model", project_client=project)
        AgentToolOrchestrator(writer, "offline-agent").configure_tools(
            DOMAINS, "documents" if search else None, "documents-connection" if search else None,
            bing_custom_search=BINDING,
        )


@pytest.mark.parametrize("search", [False, True])
def test_real_sdk_serializes_custom_search_configuration_without_loading_keys(search):
    transport = BingTransport()
    configure(transport, search)
    assert len(transport.requests) == (3 if search else 2)
    definition = json.loads(transport.requests[-1].body)["definition"]
    assert definition["tools"] == [web_tool()] + ([SEARCH_TOOL] if search else [])
    assert all("listsecrets" not in request.url.lower() for request in transport.requests)
    assert not any("key" in request.url.lower() for request in transport.requests)


@pytest.mark.parametrize("changes", [
    {"id": CONNECTION_ID.replace("/project/", "/other-project/")},
    {"id": CONNECTION_ID.replace("11111111", "99999999")},
    {"id": "bing-custom"}, {"id": None}, {"name": "other"}, {"name": None},
    {"type": "GroundingWithBingSearch"}, {"type": "GroundingWithBingCustomSearch"},
    {"type": "ApiKey"}, {"type": None},
    {"target": None}, {"target": "https://evil.example/"},
    {"target": "https://api.bing.microsoft.com.evil.example/"},
    {"target": "https://api.bing.microsoft.com/?key=value"},
    {"target": "https://user@api.bing.microsoft.com/"},
    {"target": "http://api.bing.microsoft.com/"},
])
def test_writer_verifies_scoped_connection_metadata_before_creating_version(changes):
    transport = BingTransport(connection_changes=changes)
    with pytest.raises(SourcePolicyError):
        configure(transport)
    assert len(transport.requests) == 1


def test_writer_uses_verified_full_connection_id_with_arm_case_insensitive_identity():
    uppercase = CONNECTION_ID.upper()
    transport = BingTransport(connection_changes={"id": uppercase, "name": "BING-CUSTOM"})
    configure(transport)
    definition = json.loads(transport.requests[-1].body)["definition"]
    assert definition["tools"][0]["custom_search_configuration"]["project_connection_id"] == uppercase


def test_writer_never_reads_connection_credentials():
    class Connection:
        id = CONNECTION_ID
        name = "bing-custom"
        type = "GroundingWithCustomSearch"
        target = "https://api.bing.microsoft.com/"

        @property
        def credentials(self):
            raise AssertionError("Connection keys must not be read")

    class Connections:
        def get(self, name, *, include_credentials, **kwargs):
            assert name == "bing-custom"
            assert include_credentials is False
            return Connection()

    def create_version(**kwargs):
        return SimpleNamespace(name="offline-agent", version="7", definition=kwargs["definition"])

    project = SimpleNamespace(
        connections=Connections(), agents=SimpleNamespace(create_version=create_version),
    )
    writer = FoundrySdkWriter(ENDPOINT, Credential(), "offline-model", project_client=project)
    AgentToolOrchestrator(writer, "offline-agent").configure_tools(DOMAINS, bing_custom_search=BINDING)


def test_bing_connection_lookup_cannot_outlive_configuration_deadline(monkeypatch):
    now = [0]
    monkeypatch.setattr("azure_bing_assistant.agent.time.monotonic", lambda: now[0])

    class SlowLookup(BingTransport):
        def send(self, request, **kwargs):
            result = super().send(request, **kwargs)
            now[0] = 61
            return result

    transport = SlowLookup()
    with pytest.raises(SourcePolicyError, match="time budget expired"):
        configure(transport)
    assert len(transport.requests) == 1


@pytest.mark.parametrize("mutation", [
    lambda t: t.pop("custom_search_configuration"),
    lambda t: t.update(custom_search_configuration=None),
    lambda t: t["custom_search_configuration"].update(project_connection_id="bing-custom"),
    lambda t: t["custom_search_configuration"].update(instance_name="Approved-sites"),
    lambda t: t["custom_search_configuration"].update(project_connection_id=CONNECTION_ID.replace("/project/", "/other/")),
    lambda t: t.pop("filters"),
    lambda t: t["filters"].update(allowed_domains=["evil.example"]),
])
def test_writer_rejects_dropped_or_changed_binding_and_domains(mutation):
    transport = BingTransport(mutate_definition=lambda d: mutation(d["tools"][0]))
    with pytest.raises(SourcePolicyError):
        configure(transport)
    assert len(transport.requests) == 2


def test_custom_search_provider_rejection_has_no_unfiltered_retry():
    transport = BingTransport(reject=True)
    with pytest.raises(SourcePolicyError) as caught:
        configure(transport)
    assert len(transport.requests) == 2
    assert "PRIVATE" not in str(caught.value)
    assert json.loads(transport.requests[-1].body)["definition"]["tools"] == [web_tool()]


@pytest.mark.parametrize("extra", [
    {"type": "bing_custom_search_preview"}, {"type": "function", "name": "run"},
    {"type": "web_search"}, {"type": "azure_ai_search"},
])
def test_writer_checks_all_tool_types_and_duplicates_before_connection_lookup(extra):
    transport = BingTransport()
    with AIProjectClient(endpoint=ENDPOINT, credential=Credential(), transport=transport) as project:
        writer = FoundrySdkWriter(ENDPOINT, Credential(), "offline-model", project_client=project)
        with pytest.raises((SourcePolicyError, ValueError)):
            writer.configure_agent(
                "offline-agent",
                [web_tool(), {"type": "azure_ai_search", "index": "documents", "connection": "search"}, extra],
                "Offline instructions",
            )
    assert not transport.requests


def test_policy_legacy_rejects_custom_and_custom_rejects_legacy():
    validate_tool_policy([web_tool(None)], DOMAINS, False)
    validate_tool_policy([web_tool()], DOMAINS, False, bing_custom_search=BINDING)
    with pytest.raises(SourcePolicyError):
        validate_tool_policy([web_tool()], DOMAINS, False)
    with pytest.raises(SourcePolicyError):
        validate_tool_policy([web_tool(None)], DOMAINS, False, bing_custom_search=BINDING)


def test_tool_policy_compares_full_arm_id_case_insensitively():
    tool = web_tool()
    tool["custom_search_configuration"]["project_connection_id"] = CONNECTION_ID.upper()
    validate_tool_policy([tool], DOMAINS, False, bing_custom_search=BINDING)


@pytest.mark.parametrize("configuration", [
    {}, [], "bing-custom", {"project_connection_id": CONNECTION_ID},
    {**BINDING.as_dict(), "connection": "other"},
    {**BINDING.as_dict(), "instance_name": "Approved-sites"},
    {**BINDING.as_dict(), "project_connection_id": CONNECTION_ID.replace("/project/", "/other/")},
])
def test_policy_rejects_missing_malformed_or_different_custom_bindings(configuration):
    tool = web_tool()
    tool["custom_search_configuration"] = configuration
    with pytest.raises(SourcePolicyError):
        validate_tool_policy([tool], DOMAINS, False, bing_custom_search=BINDING)


@pytest.mark.parametrize("search", [False, True])
def test_actual_response_models_keep_binding_sources_and_optional_document_provenance(search):
    payload = response_payload(search)
    # Azure-specific search calls are model extras in OpenAI's response parser.
    response = Response.model_construct(**payload) if search else Response.model_validate(payload)
    documents = set()
    assert validate_response_evidence(
        response, DOMAINS, search, bing_custom_search=BINDING,
        document_source=DOCUMENT if search else None, document_urls=documents,
    ) == ([URL], True)
    assert documents == ({DOCUMENT_URL} if search else set())


@pytest.mark.parametrize("mutation", [
    lambda p: p["tools"][0].pop("custom_search_configuration"),
    lambda p: p["tools"][0]["custom_search_configuration"].update(instance_name="other"),
    lambda p: p["tools"][0]["filters"].update(allowed_domains=["evil.example"]),
    lambda p: p["output"][0]["action"].pop("sources"),
    lambda p: p["output"][0]["action"].update(sources=[{"type": "url", "url": "https://evil.example/source"}]),
    lambda p: p["output"][0]["action"].update(redirect_url="https://evil.example/source"),
    lambda p: p["output"][1]["content"][0]["annotations"][0].update(url="https://evil.example/source"),
    lambda p: p.update(status="incomplete"),
])
def test_custom_binding_never_weakens_response_source_policy(mutation):
    payload = response_payload()
    mutation(payload)
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_construct(**payload), DOMAINS, False, bing_custom_search=BINDING,
        )


@pytest.mark.parametrize("mutation", [
    lambda p: p["output"].pop(0),
    lambda p: p["output"][0].update(results=[]),
    lambda p: p["output"][0].update(status="in_progress"),
])
def test_custom_search_does_not_exempt_private_document_urls_without_provenance(mutation):
    payload = response_payload(search=True)
    mutation(payload)
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_construct(**payload), DOMAINS, True,
            bing_custom_search=BINDING, document_source=DOCUMENT,
        )


@pytest.mark.parametrize("root_reference", [False, True])
@pytest.mark.parametrize("search", [False, True])
def test_projected_response_requires_verified_context_and_preserves_metadata(root_reference, search):
    payload = projected_response_payload(search)
    if root_reference:
        payload["agent_reference"] = dict(AGENT_REFERENCE)
    response = Response.model_construct(**payload) if search else Response.model_validate(payload)
    before = response.model_dump(warnings=False)
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            response, DOMAINS, search, bing_custom_search=BINDING,
            document_source=DOCUMENT if search else None,
        )
    documents = set()
    assert validate_response_evidence(
        response, DOMAINS, search, bing_custom_search=BINDING,
        verified_agent=VERIFIED_AGENT,
        document_source=DOCUMENT if search else None, document_urls=documents,
    ) == ([URL], True)
    assert documents == ({DOCUMENT_URL} if search else set())
    assert response.model_dump(warnings=False) == before
    assert "custom_search_configuration" not in before["tools"][0]


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(output=[]),
    lambda p: p["output"].append("malformed"),
    lambda p: [item.pop("agent_reference") for item in p["output"]],
    lambda p: p["output"][0].pop("agent_reference"),
    lambda p: p["output"][1].pop("agent_reference"),
    lambda p: p["output"][2].pop("agent_reference"),
    lambda p: p["output"][0].update(agent_reference=None),
    lambda p: p["output"][1].update(agent_reference={}),
    lambda p: p["output"][2].update(agent_reference="offline-agent:7"),
    lambda p: p["output"][0]["agent_reference"].pop("version"),
    lambda p: p["output"][1]["agent_reference"].update(version="8"),
    lambda p: p["output"][1]["agent_reference"].update(version=7),
    lambda p: p["output"][1]["agent_reference"].update(name="other-agent"),
    lambda p: p["output"][1]["agent_reference"].update(type="agent"),
    lambda p: p["output"][1]["agent_reference"].update(type=None),
    lambda p: p["output"][1]["agent_reference"].update(project="other-project"),
    lambda p: p.update(agent_reference=None),
    lambda p: p.update(agent_reference={**AGENT_REFERENCE, "version": "8"}),
    lambda p: p.update(agent_reference={**AGENT_REFERENCE, "name": "other-agent"}),
    lambda p: p.update(agent_reference={**AGENT_REFERENCE, "type": "agent"}),
    lambda p: p["output"][1].update(response_id="other-response"),
    lambda p: p["output"][1].update(response_id=None),
])
def test_projected_response_rejects_missing_partial_or_conflicting_attribution(mutation):
    payload = projected_response_payload()
    mutation(payload)
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_construct(**payload), DOMAINS, False,
            bing_custom_search=BINDING, verified_agent=VERIFIED_AGENT,
        )


def test_root_agent_reference_cannot_replace_missing_per_item_attribution():
    payload = projected_response_payload()
    payload["agent_reference"] = dict(AGENT_REFERENCE)
    for item in payload["output"]:
        item.pop("agent_reference")
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_validate(payload), DOMAINS, False,
            bing_custom_search=BINDING, verified_agent=VERIFIED_AGENT,
        )


@pytest.mark.parametrize("configuration", [
    None, {}, [], "bing-custom", {"project_connection_id": CONNECTION_ID},
    {**BINDING.as_dict(), "instance_name": "other"},
    {**BINDING.as_dict(), "instance_name": "Approved-sites"},
    {**BINDING.as_dict(), "project_connection_id": CONNECTION_ID.replace("/project/", "/other/")},
    {**BINDING.as_dict(), "extra": "unexpected"},
])
def test_matching_agent_references_never_override_explicit_wrong_or_malformed_binding(configuration):
    payload = projected_response_payload()
    payload["tools"][0]["custom_search_configuration"] = configuration
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_construct(**payload), DOMAINS, False,
            bing_custom_search=BINDING, verified_agent=VERIFIED_AGENT,
        )


def test_complete_binding_does_not_override_contradictory_agent_reference():
    payload = projected_response_payload()
    payload["tools"][0]["custom_search_configuration"] = BINDING.as_dict()
    payload["agent_reference"] = {**AGENT_REFERENCE, "version": "8"}
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_validate(payload), DOMAINS, False,
            bing_custom_search=BINDING, verified_agent=VERIFIED_AGENT,
        )


@pytest.mark.parametrize("context", [
    AGENT_REFERENCE, ("offline-agent", "7"), True,
    VerifiedAgentContext("offline-agent", "7", BingCustomSearchBinding(CONNECTION_ID, "other")),
])
def test_projected_response_needs_typed_context_for_the_expected_binding(context):
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_validate(projected_response_payload()), DOMAINS, False,
            bing_custom_search=BINDING, verified_agent=context,
        )


def test_verified_context_is_immutable():
    with pytest.raises(FrozenInstanceError):
        VERIFIED_AGENT.version = "8"


@pytest.mark.parametrize("mutation", [
    lambda p: p["tools"][0].pop("filters"),
    lambda p: p["tools"][0]["filters"].update(allowed_domains=["evil.example"]),
    lambda p: p["tools"].append({"type": "function", "name": "unsafe"}),
    lambda p: p["tools"][0].update(type="web_search_preview"),
    lambda p: p["output"][1]["action"].pop("sources"),
    lambda p: p["output"][1]["action"].update(sources=[{"type": "url", "url": "https://evil.example"}]),
    lambda p: p["output"][1]["action"].update(redirect_url="https://evil.example"),
    lambda p: p["output"][2]["content"][0]["annotations"][0].update(url="https://evil.example"),
    lambda p: p.update(status="incomplete"),
])
def test_verified_agent_projection_never_weakens_tool_or_source_policy(mutation):
    payload = projected_response_payload()
    mutation(payload)
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_construct(**payload), DOMAINS, False,
            bing_custom_search=BINDING, verified_agent=VERIFIED_AGENT,
        )


def test_verified_agent_projection_still_requires_document_provenance():
    payload = projected_response_payload(search=True)
    payload["output"][1]["results"] = []
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(
            Response.model_construct(**payload), DOMAINS, True,
            bing_custom_search=BINDING, verified_agent=VERIFIED_AGENT, document_source=DOCUMENT,
        )


def test_legacy_response_does_not_require_agent_reference_or_accept_unexpected_bing_binding():
    payload = response_payload()
    payload["tools"][0].pop("custom_search_configuration")
    assert validate_response_evidence(Response.model_validate(payload), DOMAINS, False) == ([URL], True)
    payload = projected_response_payload()
    payload["tools"][0]["custom_search_configuration"] = BINDING.as_dict()
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(Response.model_validate(payload), DOMAINS, False)


class Agents:
    def __init__(self, tools):
        self.tools = tools

    async def get(self, *, agent_name):
        return AgentDetails({
            "id": agent_name, "name": agent_name, "object": "agent",
            "versions": {"latest": {
                "id": agent_name + ":7", "name": agent_name, "version": "7",
                "object": "agent.version", "created_at": 0, "metadata": {},
                "definition": {"kind": "prompt", "model": "offline-model", "tools": self.tools},
            }},
        })


@pytest.mark.parametrize("mismatch", [None, "agent", "response"])
@pytest.mark.parametrize("search", [False, True])
@pytest.mark.parametrize("projected", [False, True])
def test_adapter_verifies_both_bindings_and_preserves_pinned_version_continuation_and_citations(
    mismatch, search, projected,
):
    payload = projected_response_payload(search) if projected else response_payload(search)
    tools = copy.deepcopy(response_payload(search)["tools"])
    if mismatch == "agent":
        tools[0]["custom_search_configuration"]["instance_name"] = "other"
    elif mismatch == "response":
        payload["tools"][0]["custom_search_configuration"] = {**BINDING.as_dict(), "instance_name": "other"}
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    async def exercise():
        client = AsyncOpenAI(
            api_key="offline-synthetic-token",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0,
        )
        adapter = FoundryAgentAdapter(
            ENDPOINT, "offline-agent", openai_client=client, allowed_domains=DOMAINS,
            search_enabled=search, document_source=DOCUMENT if search else None,
            bing_custom_search=BINDING, project_client=SimpleNamespace(agents=Agents(tools)),
        )
        try:
            if mismatch:
                with pytest.raises(SourcePolicyError):
                    await adapter.respond("Question", "opaque:previous/id")
            else:
                result = await adapter.respond("Question", "opaque:previous/id")
                assert result.response_id == "resp-bing"
                assert result.text == "Offline answer"
                assert result.consulted_sources == [URL]
                assert result.web_search_used is True
                assert len(result.citations) == (2 if search else 1)
                if search:
                    assert result.citations[-1]["type"] == "file_citation"
        finally:
            await adapter.close()

    asyncio.run(exercise())
    assert len(requests) == (0 if mismatch == "agent" else 1)
    if requests:
        assert requests[0]["agent_reference"] == {
            "type": "agent_reference", "name": "offline-agent", "version": "7",
        }
        assert requests[0]["include"] == ["web_search_call.action.sources"]
        assert requests[0]["previous_response_id"] == "opaque:previous/id"
        assert "tools" not in requests[0]


@pytest.mark.parametrize("failure", [
    "unbound-agent", "wrong-version", "wrong-agent", "missing-reference", "changed-search-index",
])
def test_adapter_does_not_trust_projected_response_from_stale_or_unattributed_agent(failure):
    search = failure == "changed-search-index"
    payload = projected_response_payload(search)
    tools = copy.deepcopy(response_payload(search)["tools"])
    if failure == "unbound-agent":
        tools[0].pop("custom_search_configuration")
    elif failure == "wrong-version":
        for item in payload["output"]:
            item["agent_reference"]["version"] = "6"
    elif failure == "wrong-agent":
        for item in payload["output"]:
            item["agent_reference"]["name"] = "other-agent"
    elif failure == "missing-reference":
        payload["output"][-1].pop("agent_reference")
    elif failure == "changed-search-index":
        payload["tools"][1]["azure_ai_search"]["indexes"][0]["index_name"] = "other-documents"
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    async def exercise():
        client = AsyncOpenAI(
            api_key="offline-synthetic-token",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0,
        )
        adapter = FoundryAgentAdapter(
            ENDPOINT, "offline-agent", openai_client=client, allowed_domains=DOMAINS,
            search_enabled=search, document_source=DOCUMENT if search else None,
            bing_custom_search=BINDING, project_client=SimpleNamespace(agents=Agents(tools)),
        )
        try:
            with pytest.raises(SourcePolicyError):
                await adapter.respond("Question", "opaque:previous/id")
        finally:
            await adapter.close()

    asyncio.run(exercise())
    assert len(requests) == (0 if failure == "unbound-agent" else 1)
    if requests:
        assert requests[0]["agent_reference"] == AGENT_REFERENCE
        assert requests[0]["previous_response_id"] == "opaque:previous/id"


@pytest.mark.parametrize("env", [{}, {
    "BING_CUSTOM_SEARCH_CONNECTION_ID": "", "BING_CUSTOM_SEARCH_INSTANCE_NAME": "",
}])
def test_empty_environment_pair_preserves_legacy_mode(env):
    assert AppSettings.from_environment(env).bing_custom_search is None


@pytest.mark.parametrize("env", [
    {"BING_CUSTOM_SEARCH_CONNECTION_ID": CONNECTION_ID},
    {"BING_CUSTOM_SEARCH_INSTANCE_NAME": "approved-sites"},
    {"BING_CUSTOM_SEARCH_CONNECTION_ID": CONNECTION_ID, "BING_CUSTOM_SEARCH_INSTANCE_NAME": ""},
    {"BING_CUSTOM_SEARCH_CONNECTION_ID": "", "BING_CUSTOM_SEARCH_INSTANCE_NAME": "approved-sites"},
    {"BING_CUSTOM_SEARCH_CONNECTION_ID": "bing-custom", "BING_CUSTOM_SEARCH_INSTANCE_NAME": "approved-sites"},
    {"BING_CUSTOM_SEARCH_CONNECTION_ID": CONNECTION_ID, "BING_CUSTOM_SEARCH_INSTANCE_NAME": "unsafe\n"},
    {"BING_CUSTOM_SEARCH_CONNECTION_ID": " ", "BING_CUSTOM_SEARCH_INSTANCE_NAME": " "},
])
def test_runtime_environment_rejects_partial_or_malformed_custom_search(env):
    with pytest.raises(ValueError):
        AppSettings.from_environment(env)


@pytest.mark.parametrize("provider,custom", [
    ("filteredWebSearch", False), ("bingCustomSearch", True),
])
def test_explicit_runtime_provider_accepts_matching_binding(provider, custom):
    env = {"WEB_SEARCH_PROVIDER": provider}
    if custom:
        env.update(
            BING_CUSTOM_SEARCH_CONNECTION_ID=CONNECTION_ID,
            BING_CUSTOM_SEARCH_INSTANCE_NAME="approved-sites",
        )
    assert AppSettings.from_environment(env).bing_custom_search == (BINDING if custom else None)


@pytest.mark.parametrize("pair", [
    {},
    {"BING_CUSTOM_SEARCH_CONNECTION_ID": "", "BING_CUSTOM_SEARCH_INSTANCE_NAME": ""},
])
def test_explicit_bing_provider_cannot_silently_fall_back_to_legacy(pair):
    with pytest.raises(ValueError, match="WEB_SEARCH_PROVIDER"):
        AppSettings.from_environment({"WEB_SEARCH_PROVIDER": "bingCustomSearch", **pair})


def test_explicit_legacy_provider_rejects_configured_bing_binding():
    with pytest.raises(ValueError, match="WEB_SEARCH_PROVIDER"):
        AppSettings.from_environment({
            "WEB_SEARCH_PROVIDER": "filteredWebSearch",
            "BING_CUSTOM_SEARCH_CONNECTION_ID": CONNECTION_ID,
            "BING_CUSTOM_SEARCH_INSTANCE_NAME": "approved-sites",
        })


@pytest.mark.parametrize("provider", ["", " ", "unknown", "BingCustomSearch", "bingCustomSearch\n"])
@pytest.mark.parametrize("custom", [False, True])
def test_invalid_explicit_runtime_provider_fails_even_with_a_valid_binding(provider, custom):
    env = {"WEB_SEARCH_PROVIDER": provider}
    if custom:
        env.update(
            BING_CUSTOM_SEARCH_CONNECTION_ID=CONNECTION_ID,
            BING_CUSTOM_SEARCH_INSTANCE_NAME="approved-sites",
        )
    with pytest.raises(ValueError, match="WEB_SEARCH_PROVIDER"):
        AppSettings.from_environment(env)


@pytest.mark.parametrize("custom", [False, True])
def test_app_wires_binding_and_only_exposes_nonsecret_provider_descriptor(monkeypatch, custom):
    captured = {}

    class Adapter:
        def __init__(self, endpoint, agent_name, **kwargs):
            captured.update(kwargs)

        async def respond(self, message, previous_response_id=None):
            return AgentResponse(text="Offline", citations=[], response_id="response-1")

    monkeypatch.setattr(backend_main, "FoundryAgentAdapter", Adapter)
    env = {
        "APP_ENV": "test", "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT,
        "CHATBOT_NAME": "offline-agent", "WEB_GROUNDING_SITES": ",".join(DOMAINS),
    }
    if custom:
        env.update(
            BING_CUSTOM_SEARCH_CONNECTION_ID=CONNECTION_ID,
            BING_CUSTOM_SEARCH_INSTANCE_NAME="approved-sites",
        )
    settings = AppSettings.from_environment(env)
    with TestClient(backend_main.create_app(settings)) as client:
        response = client.get("/api/config")
        assert response.json()["webSearchProvider"] == (
            "bingCustomSearch" if custom else "filteredWebSearch"
        )
        assert CONNECTION_ID not in response.text
        assert "approved-sites" not in response.text
        assert "connection_id" not in response.text
        assert client.post("/api/chat", json={"message": "Question"}).status_code == 200
    assert captured["bing_custom_search"] == (BINDING if custom else None)
