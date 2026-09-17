"""Nonsecret identity of a project-scoped Bing Custom Search configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass


_CONNECTION_ID = re.compile(
    r"/subscriptions/(?P<subscription>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})"
    r"/resourceGroups/(?P<group>[^/]+)"
    r"/providers/Microsoft\.CognitiveServices/accounts/(?P<account>[^/]+)"
    r"/projects/(?P<project>[^/]+)/connections/(?P<connection>[^/]+)",
    re.IGNORECASE | re.ASCII,
)
# Matches the Microsoft_Bing_Api portal configuration-name validator.
_INSTANCE_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{1,49}", re.ASCII)


@dataclass(frozen=True)
class BingCustomSearchBinding:
    """A full ARM connection ID and a case-sensitive, safe configuration name."""

    connection_id: str
    instance_name: str

    def __post_init__(self) -> None:
        # Local import keeps the shared binding usable by installer configuration.
        from .config import validate_azure_name, validate_resource_group

        match = (
            _CONNECTION_ID.fullmatch(self.connection_id)
            if isinstance(self.connection_id, str) else None
        )
        if match is None:
            raise ValueError("Bing Custom Search requires a project-scoped ARM connection ID")
        validate_resource_group(match["group"], "Bing Custom Search resource group")
        if match["group"].endswith("."):
            raise ValueError("Bing Custom Search resource group cannot end with a period")
        for name in ("account", "project", "connection"):
            validate_azure_name(f"Bing Custom Search {name}", match[name])
        if not isinstance(self.instance_name, str) or not _INSTANCE_NAME.fullmatch(self.instance_name):
            raise ValueError(
                "Bing Custom Search instance name must be 2-50 ASCII letters, digits, "
                "underscores, periods, or hyphens and start with a letter or digit"
            )

    @property
    def connection_name(self) -> str:
        """The project-local lookup name; never an alternative identity."""
        return self.connection_id.rsplit("/", 1)[1]

    @property
    def identity(self) -> tuple[str, str]:
        """ARM IDs are case-insensitive; configuration names are not."""
        return self.connection_id.casefold(), self.instance_name

    def as_dict(self) -> dict[str, str]:
        """Serialize the SDK WebSearchConfiguration wire contract."""
        return {
            "project_connection_id": self.connection_id,
            "instance_name": self.instance_name,
        }
