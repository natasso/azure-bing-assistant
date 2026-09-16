"""Offline contract checks: real SDK models/transports, never Azure or model inference."""

import asyncio
import copy
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import AgentDetails
from azure.core.credentials import AccessToken
from azure.core.pipeline.transport import HttpResponse, HttpTransport
from openai import AsyncOpenAI
from openai.types.responses import Response

from azure_bing_assistant.agent import (
    AgentToolOrchestrator,
    FoundryAgentAdapter,
    FoundrySdkWriter,
    SearchDocumentSource,
    SourcePolicyError,
    validate_response_evidence,
)
from azure_bing_assistant.config import ConfigurationError, InstallerConfig, validate_websites
from azure_bing_assistant.installer_messages import InstallerMessages


DOMAINS = ("approved.example", "xn--bcher-kva.example")
TOOLS = [{"type": "web_search", "filters": {"allowed_domains": list(DOMAINS)}}]
SEARCH_TOOL = {
    "type": "azure_ai_search",
    "azure_ai_search": {
        "indexes": [{"project_connection_id": "offline-search", "index_name": "documents"}],
    },
}
DOCUMENT_SOURCE = SearchDocumentSource("offlineprivate", "documents")
DOCUMENT_URL = "https://offlineprivate.blob.core.windows.net/documents/handbook.pdf?sig=synthetic"
VERSION = {
    "id": "offline-agent:7", "name": "offline-agent", "version": "7",
    "object": "agent.version", "created_at": 0, "metadata": {},
    "definition": {"kind": "prompt", "model": "offline-model", "tools": TOOLS},
}


class Credential:
    def get_token(self, *scopes, **kwargs):
        return AccessToken("offline-synthetic-token", int(time.time()) + 3600)


class JsonResponse(HttpResponse):
    def __init__(self, request, body, status=200):
        super().__init__(request, None)
        self.status_code = status
        self.headers = {"content-type": "application/json"}
        self._body = json.dumps(body).encode()

    def body(self):
        return self._body

    def json(self):
        return json.loads(self._body)


class AgentTransport(HttpTransport):
    def __init__(self, strip_filter=False):
        self.requests = []
        self.strip_filter = strip_filter

    def open(self):
        pass

    def close(self):
        pass

    def __exit__(self, *_):
        self.close()

    def send(self, request, **kwargs):
        self.requests.append(request)
        if "/connections/" in request.url:
            return JsonResponse(request, {
                "id": "offline-search-connection", "name": "search",
                "type": "AzureAISearch", "target": "https://offline.search.windows.net",
                "credentials": {"type": "NoAuthentication"},
            })
        assert request.method == "POST"
        definition = json.loads(request.body)["definition"]
        if self.strip_filter:
            definition["tools"][0].pop("filters", None)
        return JsonResponse(request, {**VERSION, "definition": definition})


@pytest.mark.parametrize("search", [False, True])
def test_real_sdk_agent_version_request_serializes_filtered_tool_without_bing_connection(search):
    transport = AgentTransport()
    with AIProjectClient(
        endpoint="https://offline.services.ai.azure.com/api/projects/project",
        credential=Credential(), transport=transport,
    ) as project:
        writer = FoundrySdkWriter(
            "https://offline.services.ai.azure.com/api/projects/project",
            Credential(), "offline-model", project_client=project,
        )
        AgentToolOrchestrator(writer, "offline-agent").configure_tools(
            DOMAINS,
            search_index_name="documents" if search else None,
            search_connection_name="search" if search else None,
        )
    request = transport.requests[-1]
    # Installed SDK 2.0.1 uses POST /agents/{name}/versions, not a guessed PUT.
    assert request.method == "POST"
    assert "/agents/offline-agent/versions" in request.url
    definition = json.loads(request.body)["definition"]
    assert definition["tools"][0] == TOOLS[0]
    assert len(definition["tools"]) == (2 if search else 1)
    assert len(transport.requests) == (2 if search else 1)
    assert "bing_grounding" not in json.dumps(definition)
    assert "web_search_preview" not in json.dumps(definition)
    if search:
        assert definition["tools"][1]["azure_ai_search"]["indexes"][0]["index_name"] == "documents"


def test_writer_rejects_service_that_drops_filter():
    transport = AgentTransport(strip_filter=True)
    with AIProjectClient(
        endpoint="https://offline.services.ai.azure.com/api/projects/project",
        credential=Credential(), transport=transport,
    ) as project:
        writer = FoundrySdkWriter(
            "https://offline.services.ai.azure.com/api/projects/project",
            Credential(), "offline-model", project_client=project,
        )
        with pytest.raises(SourcePolicyError):
            AgentToolOrchestrator(writer, "offline-agent").configure_tools(DOMAINS)
    assert len(transport.requests) == 1


@pytest.mark.parametrize("status", [403, 429, 500])
def test_configuration_disables_sdk_default_retries_even_for_retryable_status(status):
    class Rejected(AgentTransport):
        def send(self, request, **kwargs):
            self.requests.append(request)
            return JsonResponse(request, {"error": {"message": "PRIVATE"}}, status=status)

    transport = Rejected()
    with AIProjectClient(
        endpoint="https://offline.services.ai.azure.com/api/projects/project",
        credential=Credential(), transport=transport,
    ) as project:
        writer = FoundrySdkWriter(
            "https://offline.services.ai.azure.com/api/projects/project",
            Credential(), "offline-model", project_client=project,
        )
        with pytest.raises(SourcePolicyError):
            AgentToolOrchestrator(writer, "offline-agent").configure_tools(DOMAINS)
    assert len(transport.requests) == 1


@pytest.mark.parametrize("connection_elapsed,expected_requests", [(7, 2), (20, 1)])
def test_configuration_deadline_includes_search_connection_and_never_posts_after_expiry(
    monkeypatch, connection_elapsed, expected_requests,
):
    now = [0]
    options = []
    monkeypatch.setattr("azure_bing_assistant.agent.time.monotonic", lambda: now[0])

    class BudgetTransport(AgentTransport):
        def send(self, request, **kwargs):
            options.append(kwargs)
            result = super().send(request, **kwargs)
            if "/connections/" in request.url:
                now[0] += connection_elapsed
            return result

    transport = BudgetTransport()
    with AIProjectClient(
        endpoint="https://offline.services.ai.azure.com/api/projects/project",
        credential=Credential(), transport=transport,
    ) as project:
        writer = FoundrySdkWriter(
            "https://offline.services.ai.azure.com/api/projects/project",
            Credential(), "offline-model", project_client=project, configuration_timeout=20,
        )
        def configure():
            return AgentToolOrchestrator(writer, "offline-agent").configure_tools(
                DOMAINS, search_index_name="documents", search_connection_name="search",
            )
        if expected_requests == 1:
            with pytest.raises(SourcePolicyError, match="time budget expired"):
                configure()
        else:
            configure()
    assert len(transport.requests) == expected_requests
    assert options[0]["connection_timeout"] == options[0]["read_timeout"] == 10
    if expected_requests == 2:
        assert options[1]["connection_timeout"] == options[1]["read_timeout"] == 6.5


def test_expired_configuration_budget_does_not_submit_agent():
    transport = AgentTransport()
    with AIProjectClient(
        endpoint="https://offline.services.ai.azure.com/api/projects/project",
        credential=Credential(), transport=transport,
    ) as project:
        writer = FoundrySdkWriter(
            "https://offline.services.ai.azure.com/api/projects/project",
            Credential(), "offline-model", project_client=project, configuration_timeout=0,
        )
        with pytest.raises(SourcePolicyError, match="time budget expired"):
            AgentToolOrchestrator(writer, "offline-agent").configure_tools(DOMAINS)
    assert not transport.requests


@pytest.mark.parametrize("status", [400, 401, 403, 429])
def test_search_connection_failure_preserves_explicit_http_cause_without_raw_provider_content(status):
    from azure_bing_assistant.installer_access import _is_forbidden
    class Rejected(AgentTransport):
        def send(self, request, **kwargs):
            self.requests.append(request)
            return JsonResponse(request, {"error": {"message": "PRIVATE_PROVIDER_BODY"}}, status=status)

    transport = Rejected()
    with AIProjectClient(
        endpoint="https://offline.services.ai.azure.com/api/projects/project",
        credential=Credential(), transport=transport,
    ) as project:
        writer = FoundrySdkWriter(
            "https://offline.services.ai.azure.com/api/projects/project",
            Credential(), "offline-model", project_client=project,
        )
        with pytest.raises(SourcePolicyError) as caught:
            AgentToolOrchestrator(writer, "offline-agent").configure_tools(
                DOMAINS, search_index_name="documents", search_connection_name="search",
            )
    assert len(transport.requests) == 1 and transport.requests[0].method == "GET"
    assert "PRIVATE" not in str(caught.value)
    assert _is_forbidden(caught.value) == (status == 403)


@pytest.mark.parametrize("status", [401, 403, 400, 429, 500])
@pytest.mark.parametrize("language", ["it", "en"])
def test_writer_reports_safe_localized_auth_errors_without_capability_assumptions(status, language):
    class RejectedTransport(AgentTransport):
        def send(self, request, **kwargs):
            self.requests.append(request)
            return JsonResponse(request, {"error": {
                "code": "UserError",
                "message": "PRIVATE_PROVIDER_BODY api-key=SYNTHETIC_SECRET",
            }}, status=status)

    transport = RejectedTransport()
    with AIProjectClient(
        endpoint="https://offline.services.ai.azure.com/api/projects/project",
        credential=Credential(), transport=transport, retry_total=0,
    ) as project:
        writer = FoundrySdkWriter(
            "https://offline.services.ai.azure.com/api/projects/project",
            Credential(), "offline-model", project_client=project,
        )
        with pytest.raises(SourcePolicyError) as caught:
            AgentToolOrchestrator(writer, "offline-agent").configure_tools(DOMAINS)

    text = InstallerMessages(language)(str(caught.value))
    assert caught.value.__cause__.status_code == status
    assert len(transport.requests) == 1
    assert json.loads(transport.requests[0].body)["definition"]["tools"] == TOOLS
    if status == 401:
        assert ("tenant" in text and "Foundry User" not in text)
        assert ("Verifica l'accesso Azure" if language == "it" else "Check Azure sign-in") in text
    elif status == 403:
        assert "Foundry User" in text and "agents/write" in text
        assert ("propagazione" if language == "it" else "propagate") in text
    else:
        assert "Foundry User" not in text
        assert ("vincolo sui domini" if language == "it" else "domain restriction") in text
    assert not any(value in text for value in (
        "PRIVATE_PROVIDER_BODY", "SYNTHETIC_SECRET", "model/region",
    ))


def response_payload():
    return {
        "id": "resp-offline", "object": "response", "created_at": 0,
        "status": "completed", "model": "offline-model", "tools": copy.deepcopy(TOOLS),
        "parallel_tool_calls": True, "tool_choice": "auto",
        "output": [
            {"type": "web_search_call", "id": "ws-offline", "status": "completed",
             "action": {"type": "search", "query": "offline synthetic query",
                        "queries": ["offline synthetic query"],
                        "sources": [{"type": "url", "url": "https://sub.approved.example/path?q=1"}]}},
            {"type": "message", "id": "msg-offline", "status": "completed", "role": "assistant",
             "content": [{"type": "output_text", "text": "Offline synthetic answer",
                          "annotations": [{"type": "url_citation", "start_index": 0, "end_index": 4,
                                           "title": "Offline", "url": "https://sub.approved.example/path?q=1"}]}]},
        ],
    }


def test_real_openai_response_source_shape_and_exact_urls():
    response = Response.model_validate(response_payload())
    assert validate_response_evidence(response, DOMAINS, False) == (
        ["https://sub.approved.example/path?q=1"], True,
    )


@pytest.mark.parametrize("url", [
    "https://approved.example.evil.org/path", "https://evil.org/redirected",
    "https://approved.example@evil.org", "javascript:alert(1)", "https://127.0.0.1/",
    "https://localhost/", "https://approved.example:443/path", "//approved.example/path",
    "https://approved.example\\@evil.org/", "https://approved.example/\nsecret",
])
@pytest.mark.parametrize("action_type", ["search", "open_page", "find_in_page"])
def test_outside_or_malformed_sources_fail_entire_response(url, action_type):
    payload = response_payload()
    action = {"type": action_type}
    if action_type == "search":
        action["query"] = "offline synthetic query"
        action["sources"] = [{"type": "url", "url": url}]
    else:
        action["url"] = url
        if action_type == "find_in_page":
            action["pattern"] = "test"
    payload["output"][0]["action"] = action
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(Response.model_validate(payload), DOMAINS, False)


@pytest.mark.parametrize("mutation", [
    lambda p: p["tools"][0].pop("filters"),
    lambda p: p["tools"][0].update(type="web_search_preview"),
    lambda p: p["tools"].append({"type": "bing_grounding"}),
    lambda p: p["tools"][0]["filters"].update(allowed_domains=["evil.org"]),
    lambda p: p["output"][0]["action"].pop("sources"),
    lambda p: p["output"][0]["action"].update(sources=[{"type": "unknown", "url": "https://approved.example/"}]),
    lambda p: p["output"][0]["action"].update(type="unknown"),
    lambda p: p["output"][0]["action"].update(redirect_url="https://external.example"),
    lambda p: p["output"][1]["content"][0]["annotations"][0].update(url="https://evil.org"),
    lambda p: p.update(status="incomplete"),
])
def test_missing_or_unexpected_enforcement_metadata_fails(mutation):
    payload = response_payload()
    mutation(payload)
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(Response.model_construct(**payload), DOMAINS, False)


def test_greeting_and_no_results_are_not_fake_grounding():
    payload = response_payload()
    payload["output"] = [payload["output"][1]]
    payload["output"][0]["content"][0].update(text="Hello", annotations=[])
    assert validate_response_evidence(Response.model_validate(payload), DOMAINS, False) == ([], False)
    payload = response_payload()
    payload["output"][0]["action"]["sources"] = []
    payload["output"][1]["content"][0].update(text="No relevant information found", annotations=[])
    assert validate_response_evidence(Response.model_validate(payload), DOMAINS, False) == ([], True)


def test_bing_query_link_is_not_external_source_evidence():
    payload = response_payload()
    payload["output"][1]["content"][0]["annotations"].append(
        {"type": "bing_query", "url": "https://www.bing.com/search?q=offline"}
    )
    sources, _ = validate_response_evidence(Response.model_construct(**payload), DOMAINS, False)
    assert "https://www.bing.com/search?q=offline" not in sources


class Agents:
    def __init__(self, tools=None):
        self.tools = TOOLS if tools is None else tools
        self.names = []

    async def get(self, *, agent_name):
        self.names.append(agent_name)
        latest = copy.deepcopy(VERSION)
        latest["definition"]["tools"] = self.tools
        return AgentDetails({
            "id": "offline-agent", "object": "agent", "name": "offline-agent",
            "versions": {"latest": latest},
        })


@pytest.mark.parametrize("tools", [[], [{"type": "bing_grounding"}],
                                    [{"type": "web_search"}], TOOLS])
def test_runtime_verifies_latest_and_pins_that_immutable_version_before_inference(tools):
    requests = []
    agents = Agents(tools)

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response_payload())

    async def exercise():
        client = AsyncOpenAI(
            api_key="offline-synthetic-key", base_url="https://offline.example/openai/v1/",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0,
        )
        adapter = FoundryAgentAdapter(
            "https://offline.services.ai.azure.com/api/projects/project", "offline-agent",
            openai_client=client, allowed_domains=DOMAINS,
            project_client=SimpleNamespace(agents=agents),
        )
        try:
            if tools == TOOLS:
                result = await adapter.respond("Question", "resp-previous")
                assert result.consulted_sources == ["https://sub.approved.example/path?q=1"]
            else:
                with pytest.raises(SourcePolicyError):
                    await adapter.respond("Question")
        finally:
            await adapter.close()
    asyncio.run(exercise())
    assert agents.names == ["offline-agent"]
    if tools == TOOLS:
        assert requests[0]["agent_reference"] == {"type": "agent_reference", "name": "offline-agent", "version": "7"}
        assert requests[0]["include"] == ["web_search_call.action.sources"]
        assert requests[0]["previous_response_id"] == "resp-previous"
        assert "tools" not in requests[0]  # no assumptions about merging request tools
    else:
        assert requests == []


def test_service_rejection_never_retries_with_unfiltered_tools():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "Unsupported filtered tool", "type": "invalid_request_error"}})

    async def exercise():
        client = AsyncOpenAI(
            api_key="offline-synthetic-key",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0,
        )
        adapter = FoundryAgentAdapter(
            "https://offline.services.ai.azure.com/api/projects/project", "offline-agent",
            openai_client=client, allowed_domains=DOMAINS,
            project_client=SimpleNamespace(agents=Agents()),
        )
        try:
            with pytest.raises(SourcePolicyError):
                await adapter.respond("Question", "resp-previous")
        finally:
            await adapter.close()
    asyncio.run(exercise())
    assert len(requests) == 1


@pytest.mark.parametrize("action_type", ["open_page", "find_in_page"])
def test_allowed_open_and_find_urls_are_evidence_without_rewriting(action_type):
    payload = response_payload()
    action = {"type": action_type, "url": "https://sub.approved.example/path?q=1"}
    if action_type == "find_in_page":
        action["pattern"] = "offline"
    payload["output"][0]["action"] = action
    assert validate_response_evidence(Response.model_validate(payload), DOMAINS, False) == (
        ["https://sub.approved.example/path?q=1"], True,
    )


def test_reported_external_redirect_on_open_page_is_not_hidden():
    payload = response_payload()
    payload["output"][0]["action"] = {
        "type": "open_page", "url": "https://sub.approved.example/path",
        "sources": [{"type": "url", "url": "https://external.example/redirect-target"}],
    }
    with pytest.raises(SourcePolicyError):
        validate_response_evidence(Response.model_validate(payload), DOMAINS, False)


@pytest.mark.parametrize("values", [
    [], [""], ["example.org", ""], ["*.example.org"], ["https://example.org/department"],
    ["https://user@example.org"], ["https://example.org:443"], ["example.org:"],
    ["https://example.org?"], ["https://example.org#"], ["http://example.org"],
    ["127.0.0.1"], ["10.0.0.1"], ["[::1]"], ["localhost"], ["host.local"],
    ["host.internal"], ["example.org\\path"], ["example.org/pa\nth"], [123],
    [f"d{i}.example.org" for i in range(101)],
])
def test_invalid_domain_inputs_are_rejected(values):
    with pytest.raises(ConfigurationError):
        validate_websites(values)


def test_domain_normalization_is_stable_and_does_not_guess_www():
    assert validate_websites([
        "HTTPS://Approved.Example./", "approved.example", "bücher.example", "www.approved.example",
    ]) == (*DOMAINS, "www.approved.example")
    assert len(validate_websites(["approved.example"] * 101)) == 1


@pytest.mark.parametrize("mode", ["off", "searchBlob"])
def test_domain_configuration_roundtrips_immutable_config_bicep_app_and_api(mode):
    from fastapi.testclient import TestClient
    from app.backend.config import AppSettings
    from app.backend.main import create_app
    from azure_bing_assistant.provision import _deployment_parameters

    config = InstallerConfig.from_values(mode, environ={
        "WEB_GROUNDING_SITES": "https://Approved.Example./,bücher.example,approved.example",
        "UI_LANGUAGE": "en",
    })
    environment = config.azd_environment_values()
    parameters = _deployment_parameters(config)
    assert config.websites == DOMAINS
    assert parameters["webGroundingSites"]["value"] == environment["WEB_GROUNDING_SITES"]
    assert environment["WEB_GROUNDING_SITES"] == ",".join(DOMAINS)
    settings = AppSettings.from_environment({
        **environment,
        "FOUNDRY_PROJECT_ENDPOINT": "https://offline.services.ai.azure.com/api/projects/project",
    })
    assert settings.allowed_domains == DOMAINS
    with TestClient(create_app(settings)) as client:
        payload = client.get("/api/config").json()
    assert payload["allowedDomains"] == list(DOMAINS)
    assert payload["websiteEnforcement"] == "allowed_domains"
    assert payload["includesSubdomains"] is True
    assert payload["knowledgeMode"] == mode


@pytest.mark.parametrize("value", ["", "https://example.org/path", "*.example.org", "localhost",
                                  "https://example.org?x=1", "127.0.0.1",
                                  ",".join(f"d{i}.example.org" for i in range(101))])
def test_invalid_cli_domain_config_makes_no_write(monkeypatch, value):
    from unittest.mock import Mock
    from azure_bing_assistant import cli

    runner = Mock(side_effect=AssertionError("No environment or resource writes permitted"))
    monkeypatch.setattr(cli, "AzdRunner", runner)
    monkeypatch.setenv("WEB_GROUNDING_SITES", value)
    assert cli.main(["deploy", "--environment", "offline-example"]) == 2
    runner.assert_not_called()


def test_missing_domains_fail_before_post_deploy_and_old_bing_settings_cannot_enable_web(monkeypatch):
    from unittest.mock import Mock
    from azure_bing_assistant import cli

    writer = Mock()
    monkeypatch.setattr(cli, "_configure_post_deploy", writer)
    config = InstallerConfig.from_values("off", environ={})
    with pytest.raises(ConfigurationError, match="allowed domain"):
        cli._deploy_application(Mock(), config, {"BING_CONNECTION_NAME": "old-broad-bing"})
    writer.assert_not_called()


def test_policy_error_is_actionable_generic_and_does_not_leak_answer_or_source():
    from fastapi.testclient import TestClient
    from app.backend.config import AppSettings
    from app.backend.main import create_app

    class Rejected:
        async def respond(self, message, previous_response_id=None):
            raise SourcePolicyError("https://sensitive-outside.example/untrusted")

    with TestClient(create_app(AppSettings(allowed_domains=DOMAINS), Rejected())) as client:
        response = client.post("/api/chat", json={"message": "Question"})
    assert response.status_code == 503
    assert response.json()["code"] == "source_policy_unverified"
    assert "administrator" in response.json()["detail"]
    assert "message" not in response.json()
    assert "previousResponseId" not in response.json()
    assert "sensitive" not in response.text


def test_runtime_source_configuration_missing_does_not_claim_ready():
    from fastapi.testclient import TestClient
    from app.backend.config import AppSettings
    from app.backend.main import create_app

    with TestClient(create_app(AppSettings())) as client:
        config = client.get("/api/config").json()
        assert config["allowedDomains"] == []
        assert config["websiteEnforcement"] is None
        assert client.post("/api/chat", json={"message": "Question"}).status_code == 503


def test_supported_sdk_get_version_method_shape_is_real():
    import inspect
    from azure.ai.projects.aio.operations import AgentsOperations
    from azure.ai.projects.models import AgentObjectVersions

    assert "agent_name" in inspect.signature(AgentsOperations.get).parameters
    assert "agent_version" in inspect.signature(AgentsOperations.get_version).parameters
    assert "latest" in AgentObjectVersions.__annotations__


def search_response_payload(shape="inline", *, web=False, domains=DOMAINS):
    payload = response_payload()
    payload["tools"] = [
        {"type": "web_search", "filters": {"allowed_domains": list(domains)}},
        copy.deepcopy(SEARCH_TOOL),
    ]
    call = {
        "type": "azure_ai_search_call", "id": "ais-offline",
        "call_id": "search-offline", "status": "completed",
    }
    if shape == "inline":
        # azure-ai-projects 2.0.1 _responses_instrumentor.py recognizes results[].url.
        call["results"] = [{"url": DOCUMENT_URL, "title": "Private", "content": "Document text"}]
        search_items = [call]
    else:
        # Official Azure.AI.Extensions.OpenAI generated AzureAISearchToolCallOutput:
        # call_id, status, output (object/string/array), no typed citation-result join.
        call["arguments"] = '{"query":"offline"}'
        search_items = [call, {
            "type": "azure_ai_search_call_output", "id": "ais-output",
            "call_id": "search-offline", "status": "completed",
            "output": "Opaque service-produced document result",
        }]
        if shape == "remote":
            # Projects 2.0.1 _responses_instrumentor.py handles these envelopes
            # with the native tool discriminator in `name`, not an invented URL join.
            call.update(type="remote_function_call", name="azure_ai_search_call")
            search_items[1].update(
                type="remote_function_call_output", name="azure_ai_search_call_output",
            )
    message = payload["output"][-1]
    annotation = {
        "type": "url_citation", "url": DOCUMENT_URL,
        "title": "Private endpoint and SAS must not be displayed", "start_index": 0, "end_index": 4,
    }
    if web:
        message["content"][0]["annotations"].insert(0, annotation)
        payload["output"] = [*search_items, *payload["output"]]
    else:
        message["content"][0]["annotations"] = [annotation]
        payload["output"] = [*search_items, message]
    return payload


def search_api_response(payload, *, domains=DOMAINS, source=DOCUMENT_SOURCE, search=True, tools=None):
    from fastapi.testclient import TestClient
    from app.backend.config import AppSettings
    from app.backend.main import create_app

    requests = []
    parsed = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    sdk = AsyncOpenAI(
        api_key="offline-synthetic-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0,
    )
    create = sdk.responses.create

    async def capture(**kwargs):
        response = await create(**kwargs)
        assert isinstance(response, Response)
        parsed.append(response)
        return response

    sdk.responses.create = capture
    adapter = FoundryAgentAdapter(
        "https://offline.services.ai.azure.com/api/projects/project", "offline-agent",
        openai_client=sdk, allowed_domains=domains, search_enabled=search,
        document_source=source,
        project_client=SimpleNamespace(agents=Agents(payload["tools"] if tools is None else tools)),
    )
    with TestClient(create_app(AppSettings(allowed_domains=domains), adapter)) as client:
        result = client.post("/api/chat", json={"message": "Offline question"})
    return result, parsed, requests


@pytest.mark.parametrize("shape", ["inline", "separate", "remote"])
@pytest.mark.parametrize("document_host_allowed", [False, True])
def test_real_sdk_search_only_url_citation_becomes_opaque_api_document(shape, document_host_allowed, recwarn):
    domains = (*DOMAINS, "offlineprivate.blob.core.windows.net") if document_host_allowed else DOMAINS
    payload = search_response_payload(shape, domains=domains)
    result, parsed, requests = search_api_response(payload, domains=domains)
    assert result.status_code == 200
    call_type = "remote_function_call" if shape == "remote" else "azure_ai_search_call"
    assert parsed[0].model_dump(warnings=False)["output"][0]["type"] == call_type
    if shape != "inline":
        assert parsed[0].model_dump(warnings=False)["output"][1]["type"] == call_type + "_output"
    body = result.json()
    assert body["citations"][0]["label"] == "Documento 1"
    assert body["citations"][0]["reference"].startswith("documents/")
    assert body["consultedSources"] == []
    assert body["webSearchUsed"] is False
    assert "offlineprivate" not in result.text
    assert "sig=" not in result.text
    assert "Private endpoint" not in result.text
    assert requests[0]["agent_reference"]["version"] == "7"
    assert not any("Pydantic serializer" in str(warning.message) for warning in recwarn)


@pytest.mark.parametrize("shape", ["inline", "separate", "remote"])
def test_mixed_search_and_web_preserves_public_citation_and_private_projection(shape):
    result, _, _ = search_api_response(search_response_payload(shape, web=True))
    assert result.status_code == 200
    body = result.json()
    assert len(body["citations"]) == 2
    assert body["citations"][0]["reference"].startswith("documents/")
    assert body["citations"][1] == {
        "label": "Offline", "reference": "https://sub.approved.example/path?q=1",
    }
    assert body["consultedSources"] == ["https://sub.approved.example/path?q=1"]
    assert body["webSearchUsed"] is True
    assert "offlineprivate" not in result.text


@pytest.mark.parametrize("url", [
    "https://outside.example/private",
    "https://offlineprivate.blob.core.windows.net.evil.example/documents/private",
    "https://otherprivate.blob.core.windows.net/documents/private",
    "https://offlineprivate.blob.core.windows.net/documents-other/private",
    "https://offlineprivate.blob.core.windows.net/documents/../other/private",
    "https://offlineprivate.blob.core.windows.net/documents/%2e%2e/other/private",
    "https://offlineprivate.blob.core.windows.net/documents/",
    "https://offlineprivate.blob.core.windows.net:443/documents/private",
])
@pytest.mark.parametrize("web", [False, True])
def test_search_call_cannot_relabel_arbitrary_url_as_document(url, web):
    payload = search_response_payload(web=web)
    payload["output"][0]["results"][0]["url"] = url
    payload["output"][-1]["content"][0]["annotations"][0]["url"] = url
    result, _, _ = search_api_response(payload)
    assert result.status_code == 503
    assert result.json()["code"] == "source_policy_unverified"
    assert "message" not in result.json()
    assert url not in result.text


@pytest.mark.parametrize("mutation", [
    lambda p: p["output"].pop(0),
    lambda p: p["output"][0].pop("results"),
    lambda p: p["output"][0].update(results=[]),
    lambda p: p["output"][0].update(status="failed"),
    lambda p: (p["output"][0].pop("id"), p["output"][0].pop("call_id")),
    lambda p: p["output"][0]["results"][0].update(url=DOCUMENT_URL.replace("handbook.pdf", "other.pdf")),
])
def test_search_enabled_without_completed_provenance_fails(mutation):
    payload = search_response_payload()
    mutation(payload)
    result, _, _ = search_api_response(payload)
    assert result.status_code == 503


@pytest.mark.parametrize("mutation", [
    lambda p: p["output"][1].update(call_id="unrelated"),
    lambda p: p["output"][1].update(status="failed"),
    lambda p: p["output"][1].update(output=None),
    lambda p: p["output"].pop(0),
])
def test_separate_search_output_must_match_completed_call(mutation):
    payload = search_response_payload("separate")
    mutation(payload)
    result, _, _ = search_api_response(payload)
    assert result.status_code == 503


@pytest.mark.parametrize("field", ["index_name", "project_connection_id"])
def test_response_search_identity_must_match_pinned_agent(field):
    payload = search_response_payload()
    tools = copy.deepcopy(payload["tools"])
    payload["tools"][1]["azure_ai_search"]["indexes"][0][field] = "untrusted"
    result, _, _ = search_api_response(payload, tools=tools)
    assert result.status_code == 503


def test_search_url_without_configured_private_source_fails():
    result, _, _ = search_api_response(search_response_payload(), source=None)
    assert result.status_code == 503


@pytest.mark.parametrize("citation", [
    {"type": "file_citation", "file_id": "private-file", "filename": "private.pdf", "index": 0},
    {"type": "url_citation", "url": DOCUMENT_URL, "title": "Private", "start_index": 0, "end_index": 4},
])
def test_search_disabled_rejects_injected_document_citations(citation):
    payload = response_payload()
    payload["output"] = [payload["output"][-1]]
    payload["output"][0]["content"][0]["annotations"] = [citation]
    result, _, _ = search_api_response(payload, search=False)
    assert result.status_code == 503


@pytest.mark.parametrize("action_type", ["search", "open_page", "find_in_page"])
@pytest.mark.parametrize("host_allowed", [False, True])
def test_private_source_identity_never_exempts_web_actions(action_type, host_allowed):
    domains = (*DOMAINS, "offlineprivate.blob.core.windows.net") if host_allowed else DOMAINS
    payload = search_response_payload(web=True, domains=domains)
    action = {"type": action_type}
    if action_type == "search":
        action.update(query="offline", sources=[{"type": "url", "url": DOCUMENT_URL}])
    else:
        action["url"] = DOCUMENT_URL
        if action_type == "find_in_page":
            action["pattern"] = "offline"
    payload["output"][1]["action"] = action
    result, _, _ = search_api_response(payload, domains=domains)
    assert result.status_code == 503


def test_validated_public_url_cannot_be_overridden_by_annotation_source():
    payload = response_payload()
    payload["output"][-1]["content"][0]["annotations"][0]["source"] = "https://outside.example/override"
    result, _, _ = search_api_response(payload, search=False)
    assert result.status_code == 503
    assert result.json()["code"] == "source_policy_unverified"
    assert "override" not in result.text


def test_mixed_private_document_and_external_web_citation_fails_entire_answer():
    payload = search_response_payload(web=True)
    payload["output"][-1]["content"][0]["annotations"][1]["url"] = "https://outside.example/untrusted"
    result, _, _ = search_api_response(payload)
    assert result.status_code == 503
    assert result.json()["code"] == "source_policy_unverified"
    assert "message" not in result.json()
    assert "citations" not in result.json()


def test_allowed_url_with_search_call_but_no_document_identity_or_web_call_fails():
    payload = search_response_payload()
    url = "https://approved.example/handbook"
    payload["output"][0]["results"][0]["url"] = url
    payload["output"][-1]["content"][0]["annotations"][0]["url"] = url
    result, _, _ = search_api_response(payload)
    assert result.status_code == 503


@pytest.mark.parametrize("shape", ["inline", "separate", "remote"])
def test_disabled_search_rejects_search_call_output(shape):
    payload = search_response_payload(shape)
    payload["tools"] = copy.deepcopy(TOOLS)
    result, _, _ = search_api_response(payload, search=False)
    assert result.status_code == 503


@pytest.mark.parametrize("item_index", [0, 1])
@pytest.mark.parametrize("name", [None, "azure_ai_search", "bing_grounding_call", "arbitrary"])
def test_remote_envelope_requires_exact_search_discriminator(item_index, name):
    payload = search_response_payload("remote")
    payload["output"][item_index]["name"] = name
    result, _, _ = search_api_response(payload)
    assert result.status_code == 503


@pytest.mark.parametrize("storage", [
    {"STORAGE_ACCOUNT_NAME": "offlineprivate"},
    {"STORAGE_CONTAINER_NAME": "documents"},
    {"STORAGE_ACCOUNT_NAME": "bad.example", "STORAGE_CONTAINER_NAME": "documents"},
    {"STORAGE_ACCOUNT_NAME": "offlineprivate", "STORAGE_CONTAINER_NAME": "documents/other"},
])
def test_invalid_trusted_storage_settings_fail_locally(storage):
    from app.backend.config import AppSettings

    with pytest.raises(ValueError, match="document storage"):
        AppSettings.from_environment({"KNOWLEDGE_MODE": "searchBlob", **storage})


def test_trusted_storage_config_flows_from_existing_deployment_values_to_adapter(monkeypatch):
    from fastapi.testclient import TestClient
    from app.backend.config import AppSettings
    from app.backend import main
    from azure_bing_assistant.cli import ResolvedDeployConfig
    from azure_bing_assistant.config import KnowledgeMode

    config = InstallerConfig.from_values(KnowledgeMode.SEARCH_BLOB.value, environ={
        "WEB_GROUNDING_SITES": ",".join(DOMAINS),
    })
    resolved = ResolvedDeployConfig(
        config, "https://offline.services.ai.azure.com/api/projects/project", "offline-app",
        storage_account_name="offlineprivate", storage_container_name="documents",
    )
    settings = AppSettings.from_environment({
        **resolved.app_settings,
        "FOUNDRY_PROJECT_ENDPOINT": resolved.foundry_project_endpoint,
    })
    assert settings.document_source == DOCUMENT_SOURCE
    captured = {}

    class Adapter:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(main, "FoundryAgentAdapter", Adapter)
    with TestClient(main.create_app(settings)) as client:
        result = client.get("/api/config")
    assert captured["document_source"] == DOCUMENT_SOURCE
    assert captured["search_enabled"] is True
    assert "offlineprivate" not in result.text
    assert "STORAGE_" not in result.text
    assert AppSettings.from_environment({
        "KNOWLEDGE_MODE": "off",
        "STORAGE_ACCOUNT_NAME": "ignored-invalid",
        "STORAGE_CONTAINER_NAME": "ignored-invalid",
    }).document_source is None
