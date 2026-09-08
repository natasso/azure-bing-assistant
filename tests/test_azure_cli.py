from __future__ import annotations

import json
import subprocess

import pytest

from azure_bing_assistant import azure_cli


def test_windows_cmd_launcher_uses_bundled_python_without_a_shell(tmp_path):
    installation = tmp_path / "Program Files" / "Azure CLI"
    cmd = installation / "wbin" / "az.cmd"
    expected_python = installation / "python.exe"
    cmd.parent.mkdir(parents=True)
    cmd.touch()
    expected_python.touch()

    launcher = azure_cli.resolve_azure_cli_command(
        which=lambda name: str(cmd),
        platform_name="nt",
    )

    assert launcher == [str(expected_python), "-IBm", "azure.cli"]


def test_invocation_preserves_special_arguments_as_distinct_argv(monkeypatch):
    launcher = [r"C:\Program Files\Azure CLI\python.exe", "-IBm", "azure.cli"]
    monkeypatch.setattr(azure_cli, "resolve_azure_cli_command", lambda: launcher)
    special = 'https://example.org/a&b|c%20d/"quoted"/città'

    argv, environment = azure_cli.azure_cli_invocation(
        ["az", "command", "--value", special],
        environ={"KEEP": "yes"},
    )

    assert argv == [*launcher, "command", "--value", special]
    assert environment == {"KEEP": "yes", "AZ_INSTALLER": "MSI"}


def test_real_azure_cli_launcher_executes_read_only_version():
    try:
        argv, environment = azure_cli.azure_cli_invocation(
            ["az", "version", "--output", "json"]
        )
    except azure_cli.AzureCliResolutionError as exc:
        pytest.skip(str(exc))

    completed = subprocess.run(
        argv,
        env=environment,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["azure-cli"]
