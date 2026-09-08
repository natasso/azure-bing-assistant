"""FastAPI entry point."""

from __future__ import annotations

import asyncio
import inspect
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from azure_bing_assistant.agent import (
    AgentRequestTimeout,
    AgentResponse,
    FoundryAgentAdapter,
    InvalidPreviousResponse,
    transform_citations,
)

from .config import AppSettings


class AgentAdapter(Protocol):
    async def respond(
        self,
        message: str,
        previous_response_id: str | None = None,
    ) -> AgentResponse: ...


class UnconfiguredAgent:
    async def respond(
        self,
        message: str,
        previous_response_id: str | None = None,
    ) -> AgentResponse:
        raise RuntimeError("The cloud agent adapter is not configured")


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(min_length=1, max_length=8000)
    previous_response_id: str | None = Field(
        default=None,
        alias="previousResponseId",
        min_length=1,
        max_length=4096,
    )

    @field_validator("previous_response_id")
    @classmethod
    def validate_previous_response_id(cls, value: str | None) -> str | None:
        if value is not None and not _valid_response_id(value):
            raise ValueError("previousResponseId contains unsafe transport characters")
        return value


async def _close_resource(resource: Any) -> None:
    close = getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _valid_response_id(value: str) -> bool:
    return (
        0 < len(value) <= 4096
        and not any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    )


def create_app(
    settings: AppSettings | None = None,
    agent: AgentAdapter | None = None,
) -> FastAPI:
    current = settings or AppSettings.from_environment()
    adapter: AgentAdapter
    if agent is not None:
        adapter = agent
    elif current.foundry_project_endpoint and current.chatbot_name:
        adapter = FoundryAgentAdapter(
            current.foundry_project_endpoint,
            current.chatbot_name,
            timeout_seconds=current.agent_timeout_seconds,
        )
    else:
        adapter = UnconfiguredAgent()
    frontend = Path(__file__).resolve().parents[1] / "frontend"

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        del application
        try:
            yield
        finally:
            await _close_resource(adapter)

    application = FastAPI(
        title="Azure Bing Assistant",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del request, error
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})

    @application.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "knowledgeMode": current.knowledge_mode,
        })

    @application.get("/api/config")
    async def config() -> JSONResponse:
        ui = current.ui_config
        return JSONResponse({
            "language": ui.language,
            "productName": ui.product_name,
            "organizationName": ui.organization_name,
            "assistantName": ui.assistant_name,
            "welcomeTitle": ui.welcome_title,
            "welcomeSubtitle": ui.welcome_subtitle,
            "disclaimer": ui.disclaimer,
            "suggestedQuestions": ui.suggested_questions,
            "knowledgeMode": current.knowledge_mode,
        })

    async def run_turn(payload: ChatRequest, request: Request) -> AgentResponse | None:
        task = asyncio.create_task(
            adapter.respond(
                payload.message,
                previous_response_id=payload.previous_response_id,
            )
        )
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.05)
                if not task.done() and await request.is_disconnected():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    return None
            return await task
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise

    @application.post("/api/chat")
    async def chat(payload: ChatRequest, request: Request) -> JSONResponse:
        try:
            result = await run_turn(payload, request)
        except InvalidPreviousResponse:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "The previous response is unavailable.",
                    "code": "invalid_previous_response",
                },
            )
        except AgentRequestTimeout:
            return JSONResponse(
                status_code=504,
                content={"detail": "The cloud agent timed out."},
            )
        except RuntimeError:
            return JSONResponse(
                status_code=503,
                content={"detail": "The cloud agent is unavailable."},
            )

        if result is None or await request.is_disconnected():
            return JSONResponse(
                status_code=499,
                content={"detail": "Request cancelled."},
            )
        if not _valid_response_id(result.response_id):
            return JSONResponse(
                status_code=503,
                content={"detail": "The cloud agent returned an invalid response."},
            )
        citations = [
            {"label": citation.label, "reference": citation.reference}
            for citation in transform_citations(
                result.citations,
                language=current.ui_config.language,
            )
        ]
        return JSONResponse({
            "message": result.text,
            "citations": citations,
            "previousResponseId": result.response_id,
        })

    async def uploads_unsupported(request: Request) -> JSONResponse:
        del request
        return JSONResponse(status_code=404, content={"detail": "Uploads are unsupported."})

    for path in ("/upload", "/uploads", "/api/upload", "/api/uploads", "/api/files"):
        application.add_api_route(
            path,
            uploads_unsupported,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            include_in_schema=False,
        )

    @application.get("/")
    async def index() -> FileResponse:
        return FileResponse(frontend / "index.html")

    @application.get("/app.js")
    async def javascript() -> FileResponse:
        return FileResponse(frontend / "app.js", media_type="text/javascript")

    @application.get("/styles.css")
    async def styles() -> FileResponse:
        return FileResponse(frontend / "styles.css", media_type="text/css")

    return application


app = create_app()
