import json
import logging
import time
from types import SimpleNamespace

import pytest
from azure.core.credentials import AccessToken
from azure.core.pipeline.transport import HttpResponse, HttpTransport

from azure_bing_assistant.agent import AgentToolOrchestrator, FoundrySdkWriter
from azure_bing_assistant.search_blob import (
    AzureRestClient,
    SearchBlobOrchestrator,
    SearchBlobSettings,
    SearchSetupError,
)


TOKEN = "synthetic-token-value"


class StaticCredential:
    def __init__(self, token=TOKEN):
        self.token = token
        self.scopes = []

    def get_token(self, *scopes, **kwargs):
        self.scopes.append(scopes)
        return AccessToken(self.token, int(time.time()) + 3600)


class MockResponse(HttpResponse):
    def __init__(self, request, body=b"{}", status=200, headers=None, reason=None):
        super().__init__(request, None)
        self.status_code = status
        self.headers = headers or {}
        self.reason = reason
        self._body = body

    def body(self):
        return self._body


class RecordingTransport(HttpTransport):
    def __init__(self, failure=None, response_factory=None):
        self.failure = failure
        self.response_factory = response_factory
        self.requests = []
        self.options = []
        self.closed = False

    def open(self):
        pass

    def close(self):
        self.closed = True

    def __exit__(self, *args):
        self.close()

    def send(self, request, **kwargs):
        self.requests.append(request)
        self.options.append(kwargs)
        if self.failure:
            raise self.failure(request)
        if self.response_factory:
            return self.response_factory(request)
        payload = json.loads(request.body)
        return MockResponse(request, json.dumps({"name": payload["name"]}).encode())


class RecordingClient:
    def __init__(self):
        self.calls = []

    def put(self, path, payload):
        self.calls.append((path, payload))
        return {"name": payload["name"]} if "name" in payload else {"status": "updated"}

    def configure_agent(self, agent_name, tools, instructions):
        self.calls.append((agent_name, {"tools": tools, "instructions": instructions}))
        return "updated"


def test_managed_identity_index_and_indexer_configuration():
    client = RecordingClient()
    settings = SearchBlobSettings(
        index_name="documents",
        indexer_name="documents-indexer",
        data_source_name="documents-source",
        storage_resource_id="/subscriptions/configured-at-runtime/resourceGroups/example/providers/storage",
        container_name="documents",
    )

    SearchBlobOrchestrator(client, settings).configure()

    assert [call[0] for call in client.calls] == [
        "/indexes/documents",
        "/datasources/documents-source",
        "/indexers/documents-indexer",
    ]
    data_source = client.calls[1][1]
    assert data_source["credentials"]["connectionString"].startswith("ResourceId=")
    assert "AccountKey" not in str(data_source)


def test_search_token_reaches_azure_core_transport_without_disclosure(caplog):
    credential = StaticCredential()
    transport = RecordingTransport()
    settings = SearchBlobSettings(
        index_name="documents",
        indexer_name="documents-indexer",
        data_source_name="documents-source",
        storage_resource_id="/subscriptions/example/resourceGroups/example/providers/storage",
        container_name="documents",
    )

    with caplog.at_level(logging.DEBUG):
        result = SearchBlobOrchestrator(
            AzureRestClient(
                "https://example.search.windows.net",
                credential,
                "2024-07-01",
                transport=transport,
            ),
            settings,
        ).configure()

    assert len(transport.requests) == 3
    assert result is None
    assert TOKEN not in repr(result)
    assert credential.scopes == [("https://search.azure.com/.default",)] * 3
    assert transport.options == [
        {"connection_timeout": 30, "read_timeout": 30}
    ] * 3
    for request in transport.requests:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["Content-Type"] == "application/json"
        assert request.url.startswith("https://example.search.windows.net/")
        assert request.url.endswith("?api-version=2024-07-01")
        assert TOKEN not in request.url
        assert TOKEN.encode() not in request.body
    assert TOKEN not in caplog.text


def test_owned_transport_is_closed(monkeypatch):
    transport = RecordingTransport()
    monkeypatch.setattr(
        "azure_bing_assistant.search_blob.RequestsTransport", lambda: transport
    )

    AzureRestClient(
        "https://example.search.windows.net",
        StaticCredential(),
        "2024-07-01",
    ).put("/indexes/documents", {"name": "documents"})

    assert transport.closed is True


def test_transport_error_cannot_expose_authorization_header(caplog):
    credential = StaticCredential()
    transport = RecordingTransport(
        failure=lambda request: RuntimeError(f"failed with {dict(request.headers)}")
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(SearchSetupError) as caught:
        AzureRestClient(
            "https://example.search.windows.net",
            credential,
            "2024-07-01",
            transport=transport,
        ).put("/indexes/documents", {"name": "documents"})

    assert str(caught.value) == "Azure Search request failed"
    assert TOKEN not in str(caught.value)
    assert caught.value.__context__ is None
    assert TOKEN not in caplog.text


def test_token_acquisition_failure_sends_no_request(caplog):
    class FailingCredential:
        def get_token(self, *scopes, **kwargs):
            raise RuntimeError(f"credential failure: {TOKEN}")

    transport = RecordingTransport()
    with caplog.at_level(logging.DEBUG), pytest.raises(SearchSetupError) as caught:
        AzureRestClient(
            "https://example.search.windows.net",
            FailingCredential(),
            "2024-07-01",
            transport=transport,
        ).put("/indexes/documents", {"name": "documents"})

    assert transport.requests == []
    assert TOKEN not in str(caught.value)
    assert caught.value.__context__ is None
    assert TOKEN not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_search_http_failure_reports_only_safe_diagnostics(
    status, caplog, capsys
):
    request_id = f"req-{status}"
    body_secret = "body-secret-value"
    reason_secret = "reason-secret-value"
    transport = RecordingTransport(
        response_factory=lambda request: MockResponse(
            request,
            body=json.dumps(
                {"error": {"message": body_secret, "authorization": TOKEN}}
            ).encode(),
            status=status,
            headers={
                "X-MS-REQUEST-ID" if status == 401 else "x-ms-request-id": request_id
            },
            reason=reason_secret,
        )
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(SearchSetupError) as caught:
        AzureRestClient(
            "https://example.search.windows.net",
            StaticCredential(),
            "2024-07-01",
            transport=transport,
        ).put("/indexes/documents", {"name": "documents"})

    assert str(caught.value) == (
        f"Azure Search request failed (status={status}, request_id={request_id})"
    )
    captured = capsys.readouterr()
    public_text = "\n".join(
        (str(caught.value), repr(caught.value), captured.out, captured.err, caplog.text)
    )
    for forbidden in (
        TOKEN,
        body_secret,
        reason_secret,
        "Authorization",
        "Content-Type",
        "api-version",
        "example.search.windows.net",
        "documents",
    ):
        assert forbidden not in public_text
    assert caught.value.__context__ is None


def test_search_http_failure_handles_missing_request_id_safely(caplog, capsys):
    transport = RecordingTransport(
        response_factory=lambda request: MockResponse(
            request,
            body=b'{"error":{"message":"body-secret-value"}}',
            status=500,
        )
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(SearchSetupError) as caught:
        AzureRestClient(
            "https://example.search.windows.net",
            StaticCredential(),
            "2024-07-01",
            transport=transport,
        ).put("/indexes/documents", {"name": "documents"})

    assert str(caught.value) == "Azure Search request failed (status=500)"
    captured = capsys.readouterr()
    public_text = "\n".join(
        (str(caught.value), repr(caught.value), captured.out, captured.err, caplog.text)
    )
    assert "body-secret-value" not in public_text
    assert "documents" not in public_text


@pytest.mark.parametrize(
    "request_id",
    [
        "request id with spaces",
        "request\r\ninjected",
        "\x1b[31mrequest",
        "r" * 129,
    ],
)
def test_search_http_failure_omits_unsafe_request_id(
    request_id, caplog, capsys
):
    transport = RecordingTransport(
        response_factory=lambda request: MockResponse(
            request,
            body=b'{"secret":"body-secret-value"}',
            status=403,
            headers={"x-ms-request-id": request_id},
        )
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(SearchSetupError) as caught:
        AzureRestClient(
            "https://example.search.windows.net",
            StaticCredential(),
            "2024-07-01",
            transport=transport,
        ).put("/indexes/documents", {"name": "documents"})

    captured = capsys.readouterr()
    public_text = "\n".join(
        (str(caught.value), repr(caught.value), captured.out, captured.err, caplog.text)
    )
    assert str(caught.value) == "Azure Search request failed (status=403)"
    assert request_id not in public_text
    assert "body-secret-value" not in public_text


@pytest.mark.parametrize("token", ["", None, "not a bearer token", "bad\r\nheader"])
def test_invalid_token_sends_no_request(token):
    transport = RecordingTransport()

    with pytest.raises(SearchSetupError) as caught:
        AzureRestClient(
            "https://example.search.windows.net",
            StaticCredential(token),
            "2024-07-01",
            transport=transport,
        ).put("/indexes/documents", {"name": "documents"})

    assert transport.requests == []
    if token:
        assert token not in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.search.windows.net",
        "https://user@example.search.windows.net",
        "https://example.search.windows.net.evil.invalid",
        "https://example.search.windows.net/path",
    ],
)
def test_search_client_rejects_non_search_origins(endpoint):
    with pytest.raises(ValueError):
        AzureRestClient(endpoint, StaticCredential(), "2024-07-01")


def test_search_client_rejects_cross_origin_request_path():
    credential = StaticCredential()
    transport = RecordingTransport()

    with pytest.raises(ValueError):
        AzureRestClient(
            "https://example.search.windows.net",
            credential,
            "2024-07-01",
            transport=transport,
        ).put("https://evil.invalid/indexes/documents", {"name": "documents"})

    assert credential.scopes == []
    assert transport.requests == []


def test_agent_search_tool_uses_managed_identity():
    client = RecordingClient()
    AgentToolOrchestrator(client).configure_tools(
        "bing-connection",
        search_index_name="documents",
        search_connection_name="search-connection",
    )

    payload = client.calls[0][1]
    assert payload["tools"][0]["type"] == "bing_grounding"
    assert payload["tools"][1]["authentication"] == "managedIdentity"


def test_agent_always_has_bing_when_search_is_off():
    client = RecordingClient()
    AgentToolOrchestrator(client).configure_tools(
        "bing-connection",
        advisory_sites=("https://docs.example.org",),
    )

    payload = client.calls[0][1]
    assert payload["tools"] == [
        {"type": "bing_grounding", "connection": "bing-connection"}
    ]
    assert "advisory" in payload["instructions"]
    assert "does not accept file uploads" in payload["instructions"]
    assert "Do not claim that Bing was used" in payload["instructions"]
    assert "Answer in the user's language" in payload["instructions"]


def test_search_tool_wording_treats_indexed_documents_as_unconfirmed():
    client = RecordingClient()
    AgentToolOrchestrator(client).configure_tools(
        "bing-connection",
        search_index_name="documents",
        search_connection_name="search-connection",
    )

    instructions = client.calls[0][1]["instructions"]
    assert "administrator-indexed documents" in instructions
    assert "until retrieval confirms it" in instructions


def test_official_sdk_writer_creates_confirmed_agent_version():
    captured = {}

    class Connections:
        def get(self, name):
            return SimpleNamespace(id=f"connection:{name}")

    class Agents:
        def create_version(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(version="1")

    writer = FoundrySdkWriter.__new__(FoundrySdkWriter)
    writer.project = SimpleNamespace(connections=Connections(), agents=Agents())
    writer.model_deployment_name = "chat-model"

    status = writer.configure_agent(
        "assistant",
        [{"type": "bing_grounding", "connection": "bing-connection"}],
        "Use Bing.",
    )

    assert status == "created"
    assert captured["agent_name"] == "assistant"
    assert captured["definition"].model == "chat-model"
    assert type(captured["definition"].tools[0]).__name__ == "BingGroundingTool"


class ClosingResource:
    def __init__(self, name, events, failure=None):
        self.name = name
        self.events = events
        self.failure = failure

    def close(self):
        self.events.append(self.name)
        if self.failure:
            raise self.failure


def test_foundry_writer_closes_owned_client_then_credential_idempotently(
    monkeypatch,
):
    events = []
    credential = ClosingResource("credential", events)
    project = ClosingResource("project_client", events)
    monkeypatch.setattr(
        "azure.ai.projects.AIProjectClient",
        lambda *, endpoint, credential: project,
    )
    writer = FoundrySdkWriter(
        "https://example.services.ai.azure.com/api/projects/project",
        credential,
        "chat-model",
        owns_credential=True,
    )

    with writer:
        pass
    writer.close()

    assert events == ["project_client", "credential"]


def test_foundry_writer_does_not_close_injected_non_owned_resources():
    events = []
    credential = ClosingResource("credential", events)
    project = ClosingResource("project_client", events)

    writer = FoundrySdkWriter(
        "https://example.services.ai.azure.com/api/projects/project",
        credential,
        "chat-model",
        project_client=project,
    )
    writer.close()

    assert events == []


def test_foundry_writer_closes_credential_after_client_construction_failure(
    monkeypatch,
):
    events = []
    credential = ClosingResource("credential", events)
    primary = RuntimeError("client construction failed")

    def fail_construction(**kwargs):
        raise primary

    monkeypatch.setattr("azure.ai.projects.AIProjectClient", fail_construction)

    with pytest.raises(RuntimeError) as caught:
        FoundrySdkWriter(
            "https://example.services.ai.azure.com/api/projects/project",
            credential,
            "chat-model",
            owns_credential=True,
        )

    assert caught.value is primary
    assert events == ["credential"]


def test_foundry_writer_surfaces_safe_cleanup_only_failure():
    events = []
    credential = ClosingResource("credential", events)
    project = ClosingResource(
        "project_client",
        events,
        RuntimeError("project-client-secret"),
    )
    writer = FoundrySdkWriter(
        "https://example.services.ai.azure.com/api/projects/project",
        credential,
        "chat-model",
        project_client=project,
        owns_credential=True,
        owns_project_client=True,
    )

    with pytest.raises(RuntimeError) as caught:
        with writer:
            pass

    assert str(caught.value) == "Foundry SDK cleanup failed (project_client)"
    assert "project-client-secret" not in repr(caught.value)
    assert events == ["project_client", "credential"]


def test_foundry_writer_preserves_primary_when_cleanup_also_fails():
    events = []
    credential = ClosingResource(
        "credential",
        events,
        RuntimeError("credential-cleanup-secret"),
    )
    project = ClosingResource(
        "project_client",
        events,
        RuntimeError("project-cleanup-secret"),
    )
    writer = FoundrySdkWriter(
        "https://example.services.ai.azure.com/api/projects/project",
        credential,
        "chat-model",
        project_client=project,
        owns_credential=True,
        owns_project_client=True,
    )
    primary = RuntimeError("Foundry operation failed")

    with pytest.raises(RuntimeError) as caught:
        with writer:
            raise primary

    assert caught.value is primary
    assert events == ["project_client", "credential"]
    assert caught.value.__notes__ == ["Foundry SDK cleanup also failed"]
    assert "cleanup-secret" not in repr(caught.value)


def test_runtime_webapp_receives_generic_foundry_project_endpoint():
    from pathlib import Path

    source = Path("infra/modules/webapp.bicep").read_text(encoding="utf-8")
    assert "name: 'FOUNDRY_PROJECT_ENDPOINT'" in source
    assert "https://${foundryName}.services.ai.azure.com/api/projects/project" in source
