"""Strict subprocess boundary for Azure Developer CLI."""

from __future__ import annotations

import os
import json
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence

from .azure_cli import AzureCliResolutionError, azure_cli_invocation


class AzdError(RuntimeError):
    """Raised when an Azure CLI or azd command cannot complete."""


_SECRET_MARKERS = ("secret", "password", "token", "key", "credential")


def redact(value: str) -> str:
    lowered = value.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        if "=" in value:
            return f"{value.split('=', 1)[0]}=<redacted>"
        return "<redacted>"
    return value


def redact_argv(argv: Sequence[str]) -> list[str]:
    result: list[str] = []
    redact_next = False
    for item in argv:
        if redact_next:
            result.append("<redacted>")
            redact_next = False
            continue
        result.append(redact(item))
        redact_next = item.lstrip("-").lower() in _SECRET_MARKERS
    return result


def redact_environment(values: Mapping[str, str]) -> dict[str, str]:
    return {
        key: "<redacted>" if any(m in key.lower() for m in _SECRET_MARKERS) else value
        for key, value in values.items()
    }


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    stdout: str


class AzdRunner:
    def __init__(self, cwd: str, environment: Mapping[str, str] | None = None) -> None:
        self.cwd = cwd
        self.environment = dict(environment or {})

    def run(self, args: Sequence[str]) -> CommandResult:
        if not args or args[0] != "azd":
            raise ValueError("AzdRunner only permits azd commands")
        argv = list(args)
        env = os.environ.copy()
        env.update(self.environment)
        try:
            completed = subprocess.run(
                argv,
                cwd=self.cwd,
                env=env,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=900,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AzdError(f"Unable to execute {redact_argv(argv)!r}: {type(exc).__name__}") from exc
        if completed.returncode:
            detail = redact((completed.stderr or completed.stdout or "azd failed").strip())
            raise AzdError(
                f"Command {redact_argv(argv)!r} exited {completed.returncode}: {detail}"
            )
        return CommandResult(redact_argv(argv), redact(completed.stdout.strip()))

    def get_environment_values(self, environment_name: str) -> dict[str, str]:
        argv = [
            "azd",
            "env",
            "get-values",
            "--environment",
            environment_name,
            "--output",
            "json",
        ]
        try:
            completed = subprocess.run(
                argv,
                cwd=self.cwd,
                env=os.environ.copy(),
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AzdError("Unable to read azd deployment outputs") from exc
        if completed.returncode:
            raise AzdError("azd could not provide deployment outputs")
        try:
            values = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AzdError("azd deployment outputs were not valid JSON") from exc
        if not isinstance(values, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in values.items()
        ):
            raise AzdError("azd deployment outputs had an unexpected shape")
        return values

    def ensure_environment(self, environment_name: str) -> None:
        try:
            completed = subprocess.run(
                ["azd", "env", "list", "--output", "json"],
                cwd=self.cwd,
                env=os.environ.copy(),
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AzdError("Unable to inspect azd environments") from exc
        if completed.returncode:
            raise AzdError("azd could not list deployment environments")
        try:
            rows = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AzdError("azd environment list was not valid JSON") from exc
        if not isinstance(rows, list):
            raise AzdError("azd environment list had an unexpected shape")
        existing = {
            str(row.get("Name") or row.get("name"))
            for row in rows
            if isinstance(row, dict)
        }
        if environment_name not in existing:
            self.run(["azd", "env", "new", environment_name, "--no-prompt"])


class AzureCliRunner:
    def __init__(self, cwd: str) -> None:
        self.cwd = cwd

    def run(self, args: Sequence[str]) -> CommandResult:
        if not args or args[0] != "az":
            raise ValueError("AzureCliRunner only permits Azure CLI commands")
        logical_argv = list(args)
        try:
            argv, environment = azure_cli_invocation(args)
            completed = subprocess.run(
                argv,
                cwd=self.cwd,
                env=environment,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (AzureCliResolutionError, OSError, subprocess.TimeoutExpired) as exc:
            detail = (
                str(exc)
                if isinstance(exc, AzureCliResolutionError)
                else type(exc).__name__
            )
            raise AzdError(
                f"Unable to execute {redact_argv(logical_argv)!r}: {detail}"
            ) from exc
        if completed.returncode:
            detail = redact(
                (completed.stderr or completed.stdout or "Azure CLI failed").strip()
            )
            raise AzdError(
                f"Command {redact_argv(argv)!r} exited {completed.returncode}: {detail}"
            )
        return CommandResult(redact_argv(argv), completed.stdout.strip())


class AppServiceSettingsSynchronizer:
    _SETTING_NAMES = (
        "CHATBOT_NAME",
        "WEB_GROUNDING_SITES",
        "KNOWLEDGE_MODE",
        "UI_LANGUAGE",
    )

    def __init__(self, cwd: str, runner: AzureCliRunner | None = None) -> None:
        self.runner = runner or AzureCliRunner(cwd)

    def synchronize(
        self,
        subscription_id: str,
        resource_group: str,
        web_app_name: str,
        settings: Mapping[str, str],
    ) -> bool:
        desired = {name: settings[name] for name in self._SETTING_NAMES}
        query = (
            "[?name=='CHATBOT_NAME' || name=='WEB_GROUNDING_SITES' || "
            "name=='KNOWLEDGE_MODE' || name=='UI_LANGUAGE']."
            "{name:name,value:value}"
        )
        result = self.runner.run(
            [
                "az",
                "webapp",
                "config",
                "appsettings",
                "list",
                "--resource-group",
                resource_group,
                "--name",
                web_app_name,
                "--subscription",
                subscription_id,
                "--query",
                query,
                "--output",
                "json",
                "--only-show-errors",
            ]
        )
        try:
            rows = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AzdError("Azure CLI returned invalid App Service settings JSON") from exc
        if not isinstance(rows, list) or not all(
            isinstance(row, dict)
            and isinstance(row.get("name"), str)
            and isinstance(row.get("value"), str)
            for row in rows
        ):
            raise AzdError("Azure CLI returned unexpected App Service settings")
        current = {row["name"]: row["value"] for row in rows}
        changed = {
            name: value for name, value in desired.items() if current.get(name) != value
        }
        if not changed:
            return False
        self.runner.run(
            [
                "az",
                "webapp",
                "config",
                "appsettings",
                "set",
                "--resource-group",
                resource_group,
                "--name",
                web_app_name,
                "--subscription",
                subscription_id,
                "--settings",
                *(f"{name}={value}" for name, value in changed.items()),
                "--output",
                "none",
                "--only-show-errors",
            ]
        )
        return True
