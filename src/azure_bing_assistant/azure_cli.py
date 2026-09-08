"""Cross-platform Azure CLI subprocess invocation."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Mapping, Sequence


class AzureCliResolutionError(RuntimeError):
    """Raised when Azure CLI cannot be launched without a command shell."""


def resolve_azure_cli_command(
    *,
    which: Callable[[str], str | None] = shutil.which,
    platform_name: str = os.name,
) -> list[str]:
    executable = which("az")
    if not executable:
        raise AzureCliResolutionError("Azure CLI executable was not found")

    path = Path(executable)
    if platform_name != "nt" or path.suffix.lower() not in {".cmd", ".bat"}:
        return [str(path)]

    bundled_python = path.parent.parent / "python.exe"
    if not bundled_python.is_file():
        raise AzureCliResolutionError(
            "Azure CLI Windows launcher has no bundled Python executable"
        )
    return [str(bundled_python), "-IBm", "azure.cli"]


def azure_cli_invocation(
    args: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    if not args or args[0] != "az":
        raise ValueError("Azure CLI arguments must start with 'az'")
    launcher = resolve_azure_cli_command()
    environment = dict(os.environ if environ is None else environ)
    if launcher[-2:] == ["-IBm", "azure.cli"]:
        environment["AZ_INSTALLER"] = "MSI"
    return [*launcher, *args[1:]], environment
