import asyncio
from html.parser import HTMLParser

import httpx
import pytest
from fastapi.testclient import TestClient

from app.backend import main as backend_main
from app.backend.config import AppSettings, UIConfig
from app.backend.main import create_app
from azure_bing_assistant.agent import (
    AgentRequestTimeout,
    AgentResponse,
    InvalidPreviousResponse,
)


class FakeAgent:
    def __init__(self):
        self.calls = []

    async def respond(self, message, previous_response_id=None):
        self.calls.append((message, previous_response_id))
        return AgentResponse(
            text=f"Answer: {message}",
            citations=[{"source": "internal-source"}],
            response_id=f"response-{len(self.calls)}",
        )


class FrontendHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find(self, tag, **attributes):
        return [
            attrs
            for element_tag, attrs in self.elements
            if element_tag == tag
            and all(attrs.get(name) == value for name, value in attributes.items())
        ]


def parse_frontend(client):
    response = client.get("/")
    parser = FrontendHTMLParser()
    parser.feed(response.text)
    return response, parser


def test_first_turn_omits_previous_id_and_returns_next_id():
    agent = FakeAgent()
    app = create_app(AppSettings(environment="test"), agent)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "Question"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "Answer: Question",
        "citations": [{"label": "Documento 1", "reference": response.json()["citations"][0]["reference"]}],
        "previousResponseId": "response-1",
    }
    assert agent.calls == [("Question", None)]


def test_production_page_config_and_chat_need_no_visitor_credentials():
    agent = FakeAgent()
    app = create_app(AppSettings(environment="production"), agent)

    with TestClient(app) as client:
        page = client.get("/")
        config = client.get("/api/config")
        chat = client.post("/api/chat", json={"message": "Public question"})

    assert page.status_code == 200
    assert config.status_code == 200
    assert chat.status_code == 200
    assert chat.json()["message"] == "Answer: Public question"
    assert agent.calls == [("Public question", None)]


def test_second_turn_passes_exact_delivered_id_to_adapter():
    agent = FakeAgent()
    app = create_app(AppSettings(environment="test"), agent)
    with TestClient(app) as client:
        first = client.post("/api/chat", json={"message": "First"}).json()
        second = client.post(
            "/api/chat",
            json={"message": "Second", "previousResponseId": first["previousResponseId"]},
        )

    assert second.status_code == 200
    assert second.json()["previousResponseId"] == "response-2"
    assert agent.calls == [("First", None), ("Second", "response-1")]


def test_two_clients_are_independent_without_server_conversation_map():
    agent = FakeAgent()
    app = create_app(AppSettings(environment="test"), agent)
    with (
        TestClient(app) as tab_a,
        TestClient(app) as tab_b,
    ):
        first_a = tab_a.post("/api/chat", json={"message": "A1"}).json()
        first_b = tab_b.post("/api/chat", json={"message": "B1"}).json()
        tab_a.post(
            "/api/chat",
            json={"message": "A2", "previousResponseId": first_a["previousResponseId"]},
        )
        tab_b.post(
            "/api/chat",
            json={"message": "B2", "previousResponseId": first_b["previousResponseId"]},
        )

    assert agent.calls == [
        ("A1", None),
        ("B1", None),
        ("A2", "response-1"),
        ("B2", "response-2"),
    ]
    assert not any("conversation" in name.lower() for name in vars(app.state))


def test_fresh_app_instance_needs_no_shared_conversation_state():
    first_agent = FakeAgent()
    with TestClient(create_app(AppSettings(environment="test"), first_agent)) as client:
        delivered = client.post("/api/chat", json={"message": "First"}).json()

    restarted_agent = FakeAgent()
    with TestClient(create_app(AppSettings(environment="test"), restarted_agent)) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "After restart",
                "previousResponseId": delivered["previousResponseId"],
            },
        )

    assert response.status_code == 200
    assert restarted_agent.calls == [("After restart", "response-1")]


def test_invalid_or_expired_previous_id_returns_bounded_generic_error():
    class InvalidAgent(FakeAgent):
        async def respond(self, message, previous_response_id=None):
            raise InvalidPreviousResponse("sensitive upstream detail")

    app = create_app(AppSettings(environment="test"), InvalidAgent())
    opaque = "opaque-sensitive-id"
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"message": "Again", "previousResponseId": opaque},
        )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "The previous response is unavailable.",
        "code": "invalid_previous_response",
    }
    assert opaque not in response.text


def test_previous_id_has_only_conservative_transport_validation():
    agent = FakeAgent()
    app = create_app(AppSettings(environment="test"), agent)
    valid = "provider:id/with+opaque.characters_="
    with TestClient(app) as client:
        accepted = client.post(
            "/api/chat",
            json={"message": "Follow up", "previousResponseId": valid},
        )
        oversized = client.post(
            "/api/chat",
            json={"message": "Follow up", "previousResponseId": "x" * 4097},
        )
        unsafe = client.post(
            "/api/chat",
            json={"message": "Follow up", "previousResponseId": "line\nbreak"},
        )

    assert accepted.status_code == 200
    assert agent.calls[0][1] == valid
    assert oversized.status_code == 422
    assert unsafe.status_code == 422
    assert "x" * 4097 not in oversized.text
    assert "line" not in unsafe.text


def test_legacy_message_only_request_and_response_fields_remain_compatible():
    app = create_app(AppSettings(environment="test"), FakeAgent())
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "Legacy"})

    assert response.status_code == 200
    assert response.json()["message"] == "Answer: Legacy"
    assert isinstance(response.json()["citations"], list)


def test_unconfigured_timeout_and_configured_adapter_paths(monkeypatch):
    with TestClient(create_app(AppSettings(environment="test"))) as client:
        assert client.post("/api/chat", json={"message": "Question"}).status_code == 503

    class TimeoutAgent(FakeAgent):
        async def respond(self, message, previous_response_id=None):
            raise AgentRequestTimeout()

    with TestClient(create_app(AppSettings(environment="test"), TimeoutAgent())) as client:
        assert client.post("/api/chat", json={"message": "Question"}).status_code == 504

    captured = {}

    class RuntimeAgent(FakeAgent):
        def __init__(self, endpoint, agent_name, timeout_seconds):
            super().__init__()
            captured.update(endpoint=endpoint, agent_name=agent_name, timeout=timeout_seconds)

    monkeypatch.setattr(backend_main, "FoundryAgentAdapter", RuntimeAgent)
    settings = AppSettings(
        environment="test",
        foundry_project_endpoint="https://example.services.ai.azure.com/api/projects/project",
        chatbot_name="generic-assistant",
    )
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/chat", json={"message": "Question"}).status_code == 200
    assert captured["agent_name"] == "generic-assistant"


def test_caller_cancellation_propagates_without_server_registry():
    class CancellableAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.cancelled = False

        async def respond(self, message, previous_response_id=None):
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    async def exercise():
        agent = CancellableAgent()
        app = create_app(AppSettings(environment="test"), agent)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            request = asyncio.create_task(client.post("/api/chat", json={"message": "Wait"}))
            await agent.started.wait()
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            await asyncio.sleep(0)
        return agent, app

    agent, app = asyncio.run(exercise())
    assert agent.cancelled is True
    assert not any("request" in name.lower() for name in vars(app.state))


def test_config_ui_static_assets_accessibility_and_no_upload():
    settings = AppSettings(
        environment="test",
        ui_config=UIConfig(
            product_name="Test Product",
            assistant_name="Test Assistant",
            suggested_questions=["Q1", "Q2"],
        ),
    )
    app = create_app(settings, FakeAgent())
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "knowledgeMode": "off"}
        config = client.get("/api/config").json()
        response, parser = parse_frontend(client)
        css = client.get("/styles.css")
        js = client.get("/app.js")
        upload_responses = [
            client.post(path, files={"file": ("document.txt", b"content")})
            for path in ("/upload", "/api/upload", "/api/uploads", "/api/files")
        ]

    assert config["productName"] == "Test Product"
    assert config["language"] == "it"
    assert config["suggestedQuestions"] == ["Q1", "Q2"]
    assert config["knowledgeMode"] == "off"
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert parser.find("html", lang="it")
    assert parser.find("dialog", id="chat-dialog", **{"aria-labelledby": "dialog-title"})
    assert parser.find("div", role="log", **{"aria-live": "polite"})
    assert parser.find("textarea", id="message", maxlength="8000")
    assert not parser.find("input", type="file")
    assert css.headers["content-type"] == "text/css; charset=utf-8"
    assert js.headers["content-type"] == "text/javascript; charset=utf-8"
    assert all(item.status_code == 404 for item in upload_responses)


@pytest.mark.parametrize("mode", ["off", "searchBlob"])
def test_config_reports_bing_baseline_and_optional_document_mode(mode):
    settings = AppSettings.from_environment({
        "APP_ENV": "test",
        "KNOWLEDGE_MODE": mode,
    })

    with TestClient(create_app(settings, FakeAgent())) as client:
        config = client.get("/api/config").json()

    assert config["knowledgeMode"] == mode
    assert config["welcomeSubtitle"] == (
        "Fai una domanda sulle informazioni aggiornate disponibili sul web."
    )
    assert "document" not in config["welcomeSubtitle"].lower()


def test_search_mode_preserves_explicit_ui_text_and_empty_suggestions():
    settings = AppSettings.from_environment({
        "APP_ENV": "test",
        "KNOWLEDGE_MODE": "searchBlob",
        "UI_WELCOME_SUBTITLE": "Ask about approved internal guidance.",
        "UI_SUGGESTED_QUESTIONS": "[]",
    })

    with TestClient(create_app(settings, FakeAgent())) as client:
        config = client.get("/api/config").json()

    assert config["knowledgeMode"] == "searchBlob"
    assert config["welcomeSubtitle"] == "Ask about approved internal guidance."
    assert config["suggestedQuestions"] == []


@pytest.mark.parametrize(
    ("language", "assistant", "welcome", "citation"),
    [
        ("it", "Assistente", "Come posso aiutarti?", "Documento 1"),
        ("en", "Assistant", "How can I help?", "Document 1"),
    ],
)
def test_api_uses_complete_localized_defaults_and_source_labels(
    language, assistant, welcome, citation
):
    settings = AppSettings.from_environment({
        "APP_ENV": "test",
        "UI_LANGUAGE": language,
    })
    with TestClient(create_app(settings, FakeAgent())) as client:
        config = client.get("/api/config").json()
        response = client.post("/api/chat", json={"message": "Test"}).json()

    assert config["language"] == language
    assert config["assistantName"] == assistant
    assert config["welcomeTitle"] == welcome
    assert len(config["suggestedQuestions"]) == 5
    assert response["citations"][0]["label"] == citation


def test_language_switch_preserves_literal_overrides_and_explicit_empty_suggestions():
    environment = {
        "APP_ENV": "test",
        "UI_LANGUAGE": "en",
        "UI_ASSISTANT_NAME": "Assistente personalizzato",
        "UI_WELCOME_TITLE": "Titolo letterale",
        "UI_SUGGESTED_QUESTIONS": "[]",
    }

    config = AppSettings.from_environment(environment).ui_config

    assert config.language == "en"
    assert config.assistant_name == "Assistente personalizzato"
    assert config.welcome_title == "Titolo letterale"
    assert config.suggested_questions == []


def test_html_resources_are_local_and_has_no_inline_handlers():
    app = create_app(AppSettings(environment="test"), FakeAgent())
    with TestClient(app) as client:
        _, parser = parse_frontend(client)

    resources = [
        attrs.get(attribute)
        for tag, attrs in parser.elements
        for attribute in ("src", "href")
        if tag in {"script", "link", "img"} and attrs.get(attribute)
    ]
    assert all(resource.startswith("/") or resource.startswith("data:") for resource in resources)
    assert all(
        not any(name.lower().startswith("on") for name in attrs)
        for _, attrs in parser.elements
    )


def test_message_length_is_bounded():
    app = create_app(AppSettings(environment="test"), FakeAgent())
    with TestClient(app) as client:
        assert client.post("/api/chat", json={"message": ""}).status_code == 422
        assert client.post("/api/chat", json={"message": "x" * 8000}).status_code == 200
        assert client.post("/api/chat", json={"message": "x" * 8001}).status_code == 422
