"""Agent-tool orchestration and safe citation projection."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Protocol
from urllib.parse import urlsplit


class AgentVersionWriter(Protocol):
    def configure_agent(
        self,
        agent_name: str,
        tools: list[dict[str, Any]],
        instructions: str,
    ) -> str: ...


@dataclass(frozen=True)
class SafeCitation:
    label: str
    reference: str


@dataclass(frozen=True)
class AgentResponse:
    text: str
    citations: list[dict[str, Any]]
    response_id: str


class AgentRequestTimeout(RuntimeError):
    """Raised when a Foundry response exceeds the application deadline."""


class InvalidPreviousResponse(RuntimeError):
    """Raised when Foundry cannot continue from the supplied response identifier."""


_CITATION_MARKER = re.compile(r"[\u3010\[][0-9]+:[0-9]+\u2020?source[\u3011\]]")
_STABLE_SOURCE_FIELDS = (
    "filename",
    "file_name",
    "blob_name",
    "blob_path",
    "file_path",
    "source_path",
    "file_id",
)


def _stable_source_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or "\u2026" in candidate or candidate.endswith("..."):
        return None
    return candidate


def _provider_label(citation: dict[str, Any]) -> str | None:
    for field in ("title", "label"):
        value = citation.get(field)
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if (
            candidate
            and len(candidate) <= 160
            and not any(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in candidate
            )
        ):
            return candidate
    return None


def extract_foundry_response(response: Any) -> tuple[str, list[dict[str, Any]]]:
    """Extract clean response text and annotation metadata from a Foundry response."""
    text = str(getattr(response, "output_text", "") or "")
    try:
        payload = response.model_dump()
    except (AttributeError, TypeError, ValueError):
        payload = {}

    annotations: list[dict[str, Any]] = []
    for item in payload.get("output", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            for annotation in content.get("annotations") or []:
                if not isinstance(annotation, dict):
                    continue
                normalized = dict(annotation)
                source = _stable_source_value(normalized.get("source"))
                if source:
                    normalized["source"] = source
                else:
                    normalized.pop("source", None)
                    if not normalized.get("url") and not normalized.get("id"):
                        stable_source = next(
                            (
                                _stable_source_value(normalized.get(key))
                                for key in _STABLE_SOURCE_FIELDS
                                if _stable_source_value(normalized.get(key))
                            ),
                            None,
                        )
                        if stable_source:
                            normalized["source"] = stable_source
                annotations.append(normalized)

    text = _CITATION_MARKER.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    return text, annotations


def transform_citations(
    raw: list[dict[str, Any]],
    *,
    language: str = "en",
) -> list[SafeCitation]:
    """Project untrusted citations to opaque, document-relative references."""
    if language not in {"it", "en"}:
        raise ValueError("language must be 'it' or 'en'")
    labels = {
        "bing": "Ricerca Bing" if language == "it" else "Bing search",
        "web": "Fonte web" if language == "it" else "Web source",
        "document": "Documento" if language == "it" else "Document",
    }
    safe: list[SafeCitation] = []
    seen: set[str] = set()
    for citation in raw:
        source = str(citation.get("source") or citation.get("url") or citation.get("id") or "")
        if not source:
            continue
        provider_label = _provider_label(citation)
        citation_type = str(citation.get("type") or "")
        if citation_type in {"web", "url_citation", "bing_query"}:
            parsed = urlsplit(source)
            try:
                port = parsed.port
            except ValueError:
                continue
            try:
                address = ip_address(parsed.hostname or "")
            except ValueError:
                address = None
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or port
                or address is not None
                or "." not in parsed.hostname
                or parsed.hostname.lower().endswith(
                    (
                        ".blob.core.windows.net",
                        ".search.windows.net",
                        ".services.ai.azure.com",
                        ".openai.azure.com",
                    )
                )
            ):
                continue
            if citation_type == "bing_query" and parsed.hostname.lower() != "www.bing.com":
                continue
            if source in seen:
                continue
            seen.add(source)
            safe.append(
                SafeCitation(
                    label=(
                        provider_label
                        or (
                            labels["bing"]
                            if citation_type == "bing_query"
                            else f"{labels['web']} {len(safe) + 1}"
                        )
                    ),
                    reference=source,
                )
            )
            continue
        reference_id = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
        if reference_id in seen:
            continue
        seen.add(reference_id)
        safe.append(
            SafeCitation(
                label=f"{labels['document']} {len(safe) + 1}",
                reference=f"documents/{reference_id}",
            )
        )
    return safe


class AgentToolOrchestrator:
    def __init__(self, client: AgentVersionWriter, agent_name: str = "assistant") -> None:
        self.client = client
        self.agent_name = agent_name

    def configure_tools(
        self,
        bing_connection_name: str,
        advisory_sites: tuple[str, ...] = (),
        search_index_name: str | None = None,
        search_connection_name: str | None = None,
    ) -> None:
        if not bing_connection_name:
            raise ValueError("Bing connection name is required")
        if bool(search_index_name) != bool(search_connection_name):
            raise ValueError("search index and connection must be supplied together")
        tools: list[dict[str, Any]] = [
            {
                "type": "bing_grounding",
                "connection": bing_connection_name,
            }
        ]
        if search_index_name and search_connection_name:
            tools.append(
                {
                    "type": "azure_ai_search",
                    "index": search_index_name,
                    "connection": search_connection_name,
                    "authentication": "managedIdentity",
                }
            )
        instructions = (
            "Use Grounding with Bing Search for current public information. "
            "Do not claim that Bing was used for a specific answer unless the "
            "returned evidence supports that claim. "
            "Answer in the user's language unless the user asks for another language. "
            "The chat interface does not accept file uploads, so do not ask the user "
            "to upload or attach a file."
        )
        if search_index_name:
            instructions += (
                " Azure AI Search is configured for administrator-indexed documents. "
                "Do not imply that a particular document is available until retrieval "
                "confirms it."
            )
        if advisory_sites:
            instructions += (
                " Prefer these sites when Bing returns them: "
                + ", ".join(advisory_sites)
                + ". This preference is advisory and does not restrict Bing results."
            )
        status = self.client.configure_agent(
            self.agent_name,
            tools,
            instructions,
        )
        if status not in {"created", "updated", "succeeded"}:
            raise RuntimeError("Foundry did not confirm agent-tool configuration")


class FoundrySdkWriter:
    """Official Azure AI Projects SDK boundary for creating an agent version."""

    def __init__(
        self,
        endpoint: str,
        credential: Any | None,
        model_deployment_name: str,
        *,
        project_client: Any | None = None,
        owns_credential: bool = False,
        owns_project_client: bool = False,
    ) -> None:
        try:
            self.project = project_client
            self.credential = credential
            self._owns_project_client = owns_project_client
            self._owns_credential = owns_credential
            self._closed = False
            if not endpoint.startswith("https://") or not model_deployment_name:
                raise ValueError("Foundry endpoint and model deployment are required")
            if self.credential is None:
                try:
                    from azure.identity import DefaultAzureCredential
                except ImportError as exc:
                    raise RuntimeError(
                        "azure-identity is required for agent setup"
                    ) from exc
                self.credential = DefaultAzureCredential()
                self._owns_credential = True
            if self.project is None:
                try:
                    from azure.ai.projects import AIProjectClient
                except ImportError as exc:
                    raise RuntimeError(
                        "azure-ai-projects is required for agent setup"
                    ) from exc
                self.project = AIProjectClient(
                    endpoint=endpoint,
                    credential=self.credential,
                )
                self._owns_project_client = True
            self.model_deployment_name = model_deployment_name
        except BaseException as exc:
            try:
                self.close()
            except Exception:
                exc.add_note("Foundry SDK cleanup also failed")
            raise

    def __enter__(self) -> FoundrySdkWriter:
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> bool:
        try:
            self.close()
        except Exception:
            if exc is not None:
                exc.add_note("Foundry SDK cleanup also failed")
                return False
            raise
        return False

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        failures: list[str] = []
        resources = (
            ("project_client", getattr(self, "project", None), self._owns_project_client),
            ("credential", getattr(self, "credential", None), self._owns_credential),
        )
        for name, resource, owned in resources:
            if not owned or resource is None:
                continue
            try:
                resource.close()
            except Exception:
                failures.append(name)
        if failures:
            raise RuntimeError(
                f"Foundry SDK cleanup failed ({', '.join(failures)})"
            ) from None

    def configure_agent(
        self,
        agent_name: str,
        tools: list[dict[str, Any]],
        instructions: str,
    ) -> str:
        from azure.ai.projects.models import (
            AISearchIndexResource,
            AzureAISearchTool,
            AzureAISearchToolResource,
            BingGroundingSearchConfiguration,
            BingGroundingSearchToolParameters,
            BingGroundingTool,
            PromptAgentDefinition,
        )

        sdk_tools: list[Any] = []
        for tool in tools:
            connection = self.project.connections.get(tool["connection"])
            if tool["type"] == "bing_grounding":
                sdk_tools.append(
                    BingGroundingTool(
                        bing_grounding=BingGroundingSearchToolParameters(
                            search_configurations=[
                                BingGroundingSearchConfiguration(
                                    project_connection_id=connection.id
                                )
                            ]
                        )
                    )
                )
            elif tool["type"] == "azure_ai_search":
                sdk_tools.append(
                    AzureAISearchTool(
                        azure_ai_search=AzureAISearchToolResource(
                            indexes=[
                                AISearchIndexResource(
                                    project_connection_id=connection.id,
                                    index_name=tool["index"],
                                )
                            ]
                        )
                    )
                )
            else:
                raise ValueError("Unsupported Foundry tool type")
        result = self.project.agents.create_version(
            agent_name=agent_name,
            definition=PromptAgentDefinition(
                model=self.model_deployment_name,
                instructions=instructions,
                tools=sdk_tools,
            ),
            description="Configured chatbot agent",
        )
        if not getattr(result, "version", None):
            raise RuntimeError("Foundry did not return an agent version")
        return "created"


class FoundryAgentAdapter:
    """Managed-identity runtime adapter using the proven Foundry Responses contract."""

    def __init__(
        self,
        endpoint: str,
        agent_name: str,
        credential: Any | None = None,
        openai_client: Any | None = None,
        timeout_seconds: float = 90.0,
    ) -> None:
        parsed = urlsplit(endpoint)
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.lower().endswith(".services.ai.azure.com")
            or parsed.username
            or parsed.password
            or port
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"/api/projects/[A-Za-z0-9][A-Za-z0-9._-]*/?", parsed.path)
            or not agent_name
            or timeout_seconds <= 0
        ):
            raise ValueError("A valid Foundry project endpoint and agent name are required")
        self.endpoint = endpoint.rstrip("/")
        self.agent_name = agent_name
        self.credential = credential
        self.openai_client = openai_client
        self.timeout_seconds = timeout_seconds
        self._project_client: Any | None = None
        self._owns_credential = False

    def _client(self) -> Any:
        if self.openai_client is None:
            try:
                from azure.ai.projects.aio import AIProjectClient
                from azure.identity.aio import DefaultAzureCredential
            except ImportError as exc:
                raise RuntimeError(
                    "azure-ai-projects and azure-identity are required at runtime"
                ) from exc
            if self.credential is None:
                self.credential = DefaultAzureCredential()
                self._owns_credential = True
            self._project_client = AIProjectClient(
                endpoint=self.endpoint,
                credential=self.credential,
            )
            self.openai_client = self._project_client.get_openai_client()
        return self.openai_client

    async def respond(
        self,
        message: str,
        previous_response_id: str | None = None,
    ) -> AgentResponse:
        kwargs: dict[str, Any] = {
            "input": message,
            "extra_body": {
                "agent_reference": {
                    "type": "agent_reference",
                    "name": self.agent_name,
                }
            },
            "timeout": self.timeout_seconds,
        }
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id
        try:
            from openai import APIError, BadRequestError, NotFoundError

            async with asyncio.timeout(self.timeout_seconds):
                response = await self._client().responses.create(**kwargs)
        except TimeoutError as exc:
            raise AgentRequestTimeout("The Foundry agent request timed out") from exc
        except (BadRequestError, NotFoundError) as exc:
            if previous_response_id:
                raise InvalidPreviousResponse(
                    "The previous Foundry response is unavailable"
                ) from exc
            raise RuntimeError("The Foundry agent request failed") from exc
        except APIError as exc:
            raise RuntimeError("The Foundry agent request failed") from exc
        text, citations = extract_foundry_response(response)
        response_id = str(getattr(response, "id", "") or "")
        if not text:
            raise RuntimeError("The Foundry agent returned an empty response")
        if not response_id:
            raise RuntimeError("The Foundry agent omitted the response identifier")
        return AgentResponse(text=text, citations=citations, response_id=response_id)

    async def close(self) -> None:
        resources = [self.openai_client, self._project_client]
        if self._owns_credential:
            resources.append(self.credential)
        closed: set[int] = set()
        for resource in resources:
            if resource is None or id(resource) in closed:
                continue
            closed.add(id(resource))
            close = getattr(resource, "close", None)
            if close is None:
                continue
            result = close()
            if inspect.isawaitable(result):
                await result
