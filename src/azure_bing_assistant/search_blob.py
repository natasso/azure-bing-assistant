"""Managed-identity search index and Blob indexer orchestration."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from azure.core.pipeline import Pipeline
from azure.core.pipeline.policies import BearerTokenCredentialPolicy
from azure.core.pipeline.transport import HttpRequest, HttpTransport, RequestsTransport


_SEARCH_SCOPE = "https://search.azure.com/.default"
_SEARCH_HOST = re.compile(
    r"[a-z0-9][a-z0-9-]{1,58}[a-z0-9]\.search\.windows\.net"
)
_BEARER_TOKEN = re.compile(r"[A-Za-z0-9\-._~+/]+={0,}")
_AZURE_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", re.ASCII)


class TokenProvider(Protocol):
    def get_token(self, *scopes: str, **kwargs: Any) -> Any: ...


class SearchSetupError(RuntimeError):
    """Raised when Azure does not explicitly confirm search setup."""


def _search_failure_message(response: Any | None) -> str:
    details: list[str] = []
    try:
        status = response.status_code
    except Exception:
        status = None
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        details.append(f"status={status}")

    try:
        request_id = next(
            (
                value
                for name, value in response.headers.items()
                if isinstance(name, str) and name.lower() == "x-ms-request-id"
            ),
            None,
        )
    except Exception:
        request_id = None
    if isinstance(request_id, str) and _AZURE_REQUEST_ID.fullmatch(request_id):
        details.append(f"request_id={request_id}")

    suffix = f" ({', '.join(details)})" if details else ""
    return f"Azure Search request failed{suffix}"


class _SearchBearerTokenPolicy(BearerTokenCredentialPolicy):
    def on_request(self, request: Any) -> None:
        super().on_request(request)
        authorization = request.http_request.headers.get("Authorization", "")
        token = getattr(self._token, "token", None)
        if (
            not isinstance(token, str)
            or not _BEARER_TOKEN.fullmatch(token)
            or authorization != f"Bearer {token}"
        ):
            request.http_request.headers.pop("Authorization", None)
            raise ValueError("credential returned an invalid access token")


class AzureRestClient:
    def __init__(
        self,
        endpoint: str,
        credential: TokenProvider,
        api_version: str,
        scope: str = _SEARCH_SCOPE,
        transport: HttpTransport[HttpRequest, Any] | None = None,
    ) -> None:
        parsed = urlparse(endpoint)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("endpoint must be an Azure Search HTTPS origin") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not _SEARCH_HOST.fullmatch(parsed.hostname.lower())
            or parsed.username
            or parsed.password
            or port
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("endpoint must be an Azure Search HTTPS origin")
        self.endpoint = endpoint.rstrip("/") + "/"
        self.credential = credential
        self.api_version = api_version
        self.scope = scope
        self._transport = transport
        self._hostname = parsed.hostname.lower()

    def _send(self, request: HttpRequest) -> Any:
        policies = [_SearchBearerTokenPolicy(self.credential, self.scope)]
        options = {"connection_timeout": 30, "read_timeout": 30}
        if self._transport is not None:
            return Pipeline(transport=self._transport, policies=policies).run(
                request, **options
            ).http_response
        with RequestsTransport() as transport:
            return Pipeline(transport=transport, policies=policies).run(
                request, **options
            ).http_response

    def _write(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        separator = "&" if "?" in path else "?"
        url = urljoin(self.endpoint, path.lstrip("/")) + separator + "api-version=" + self.api_version
        parsed_url = urlparse(url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.hostname.lower() != self._hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.port
        ):
            raise ValueError("request path must remain on the Azure Search endpoint")
        request = HttpRequest(
            method,
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = None
        failure_message = None
        try:
            response = self._send(request)
            response.raise_for_status()
            body = response.body()
        except Exception:
            failure_message = _search_failure_message(response)
        if failure_message is not None:
            raise SearchSetupError(failure_message) from None
        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise SearchSetupError("Azure REST response was not valid JSON") from exc

    def put(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._write("PUT", path, payload)


@dataclass(frozen=True)
class SearchBlobSettings:
    index_name: str
    indexer_name: str
    data_source_name: str
    storage_resource_id: str
    container_name: str

    def __post_init__(self) -> None:
        for value in (
            self.index_name,
            self.indexer_name,
            self.data_source_name,
            self.storage_resource_id,
            self.container_name,
        ):
            if not value or any(character.isspace() for character in value):
                raise ValueError("search setup values must be nonblank and contain no whitespace")


class SearchBlobOrchestrator:
    def __init__(self, client: AzureRestClient, settings: SearchBlobSettings) -> None:
        self.client = client
        self.settings = settings

    def configure(self) -> None:
        s = self.settings
        operations = [
            (
                f"/indexes/{s.index_name}",
                {
                    "name": s.index_name,
                    "fields": [
                        {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
                        {"name": "content", "type": "Edm.String", "searchable": True},
                        {"name": "source", "type": "Edm.String", "filterable": True},
                    ],
                },
            ),
            (
                f"/datasources/{s.data_source_name}",
                {
                    "name": s.data_source_name,
                    "type": "azureblob",
                    "credentials": {
                        "connectionString": f"ResourceId={s.storage_resource_id};"
                    },
                    "container": {"name": s.container_name},
                },
            ),
            (
                f"/indexers/{s.indexer_name}",
                {
                    "name": s.indexer_name,
                    "dataSourceName": s.data_source_name,
                    "targetIndexName": s.index_name,
                    "parameters": {"configuration": {"dataToExtract": "contentAndMetadata"}},
                    "fieldMappings": [
                        {"sourceFieldName": "metadata_storage_path", "targetFieldName": "id"},
                        {"sourceFieldName": "metadata_storage_name", "targetFieldName": "source"},
                    ],
                },
            ),
        ]
        for path, payload in operations:
            response = self.client.put(path, payload)
            if response.get("name") != payload["name"]:
                raise SearchSetupError(f"Azure did not confirm creation of {payload['name']}")
