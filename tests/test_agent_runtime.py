import asyncio
import inspect
from types import SimpleNamespace

import pytest

from azure_bing_assistant.agent import (
    AgentRequestTimeout,
    FoundryAgentAdapter,
    extract_foundry_response,
    transform_citations,
)

SEARCH_TOOL = {
    "type": "azure_ai_search",
    "azure_ai_search": {
        "indexes": [{"project_connection_id": "offline-search", "index_name": "documents"}],
    },
}


class FakeResponse:
    id = "resp-1"
    output_text = "Answer   \n"

    def model_dump(self, **kwargs):
        return {
            "status": "completed",
            "tools": [
                {"type": "web_search", "filters": {"allowed_domains": ["example.org"]}},
                SEARCH_TOOL,
            ],
            "output": [
                {
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {"type": "search", "sources": [{"type": "url", "url": "https://www.example.org/reference"}]},
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "title": "Public source",
                                    "url": "https://www.example.org/reference",
                                },
                                {
                                    "type": "file_citation",
                                    "title": "Truncated display title…",
                                    "source": "Truncated display title…",
                                    "filename": "handbook.pdf",
                                },
                                {
                                    "type": "file_citation",
                                    "title": "No stable source",
                                    "filename": "truncated…",
                                },
                            ]
                        }
                    ],
                }
            ]
        }


class FakeResponses:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


class FakeOpenAIClient:
    def __init__(self):
        self.responses = FakeResponses()
        self.closed = False

    async def close(self):
        self.closed = True


class FakeAgents:
    async def get(self, *, agent_name):
        from azure.ai.projects.models import PromptAgentDefinition, WebSearchTool, WebSearchToolFilters
        definition = PromptAgentDefinition(
            model="offline-model",
            tools=[WebSearchTool(filters=WebSearchToolFilters(allowed_domains=["example.org"])),
                   SEARCH_TOOL],
        )
        latest = SimpleNamespace(name=agent_name, version="7", definition=definition)
        return SimpleNamespace(name=agent_name, versions=SimpleNamespace(latest=latest))


def runtime_adapter(endpoint, agent_name, **kwargs):
    return FoundryAgentAdapter(
        endpoint, agent_name, allowed_domains=("example.org",), search_enabled=True,
        project_client=SimpleNamespace(agents=FakeAgents()) if "openai_client" in kwargs else None,
        **kwargs,
    )


def test_foundry_response_reuses_annotation_contract_and_cleans_markers():
    text, raw = extract_foundry_response(FakeResponse())
    citations = transform_citations(raw)

    assert text == "Answer"
    assert raw[1]["source"] == "handbook.pdf"
    assert "source" not in raw[2]
    assert citations[0].label == "Public source"
    assert citations[0].reference == "https://www.example.org/reference"
    assert citations[1].label == "Document 2"
    assert citations[1].reference.startswith("documents/")
    assert "handbook.pdf" not in citations[1].reference


def test_runtime_adapter_uses_proven_agent_reference_response_call():
    client = FakeOpenAIClient()
    adapter = runtime_adapter(
        "https://example.services.ai.azure.com/api/projects/project",
        "generic-assistant",
        openai_client=client,
    )

    result = asyncio.run(adapter.respond("Question", previous_response_id="resp-0"))

    assert result.text == "Answer"
    assert result.response_id == "resp-1"
    assert len(result.citations) == 3
    assert client.responses.calls == [
        {
            "input": "Question",
            "previous_response_id": "resp-0",
            "timeout": 90.0,
            "include": ["web_search_call.action.sources"],
            "extra_body": {
                "agent_reference": {
                    "type": "agent_reference",
                    "name": "generic-assistant",
                    "version": "7",
                }
            },
        }
    ]


def test_runtime_adapter_timeout_cancels_async_sdk_call():
    class SlowResponses(FakeResponses):
        def __init__(self):
            super().__init__()
            self.cancelled = False

        async def create(self, **kwargs):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    client = FakeOpenAIClient()
    client.responses = SlowResponses()
    adapter = runtime_adapter(
        "https://example.services.ai.azure.com/api/projects/project",
        "generic-assistant",
        openai_client=client,
        timeout_seconds=0.01,
    )

    with pytest.raises(AgentRequestTimeout):
        asyncio.run(adapter.respond("Question"))

    assert client.responses.cancelled is True


def test_runtime_adapter_closes_injected_client():
    client = FakeOpenAIClient()
    adapter = runtime_adapter(
        "https://example.services.ai.azure.com/api/projects/project",
        "generic-assistant",
        openai_client=client,
    )

    async def exercise():
        await adapter.close()

    asyncio.run(exercise())

    assert client.responses.calls == []
    assert client.closed is True


def test_installed_async_sdk_exposes_the_runtime_contract():
    from azure.ai.projects.aio import AIProjectClient
    from openai.resources.responses.responses import AsyncResponses

    project_signature = inspect.signature(AIProjectClient.get_openai_client)
    create_signature = inspect.signature(AsyncResponses.create)

    assert "kwargs" in project_signature.parameters
    assert "input" in create_signature.parameters
    assert "previous_response_id" in create_signature.parameters
    assert "extra_body" in create_signature.parameters
    assert "timeout" in create_signature.parameters
    assert inspect.iscoroutinefunction(AsyncResponses.create)


def test_async_runtime_client_constructs_without_network():
    adapter = runtime_adapter(
        "https://example.services.ai.azure.com/api/projects/project",
        "generic-assistant",
    )

    client = adapter._client()

    assert client.responses is not None
    asyncio.run(adapter.close())


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.services.ai.azure.com/api/projects/project",
        "https://user@example.services.ai.azure.com/api/projects/project",
        "https://example.services.ai.azure.com/api/projects/project?secret=value",
        "https://example.services.ai.azure.com:8443/api/projects/project",
        "https://example.invalid/api/projects/project",
    ],
)
def test_runtime_adapter_rejects_unsafe_endpoints(endpoint):
    with pytest.raises(ValueError):
        runtime_adapter(endpoint, "generic-assistant", openai_client=FakeOpenAIClient())
