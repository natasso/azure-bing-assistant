"""Exercise the documented branding commands locally, never running Azure CLI."""

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import pytest

from app.backend.config import AppSettings


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows native-argument regression")
PROBE = r"""
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
record = {"args": args}
operation = "settings" if args[:4] == ["webapp", "config", "appsettings", "set"] else "restart"
if operation == "settings":
    path = Path(args[args.index("--settings") + 1][1:])
    raw = path.read_bytes()
    record.update(path=str(path), bom=raw.startswith(b"\xef\xbb\xbf"),
                  settings=json.loads(raw.decode("utf-8")))
with Path(os.environ["BRANDING_PROBE_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(record, ensure_ascii=True) + "\n")
sys.exit(17 if os.environ.get("BRANDING_PROBE_FAILURE") == operation else 0)
"""
CLI_PARSER_PROBE = r"""
import json
import socket
import sys
from types import SimpleNamespace
from unittest.mock import patch

def deny_network(*args, **kwargs):
    raise AssertionError("Network is forbidden in this offline test")

with patch.object(socket.socket, "connect", deny_network), \
     patch.object(socket.socket, "connect_ex", deny_network):
    from azure.cli.core.commands import _expand_file_prefixed_files
    from azure.cli.command_modules.appservice import custom

    args = _expand_file_prefixed_files(["--settings", "@" + sys.argv[1]])
    values = json.loads(args[1])
    original = SimpleNamespace(properties={"UI_LANGUAGE": "en", "UNRELATED": "keep"})
    def capture_update(*args):
        assert args[3] == "update_application_settings"
        return args[4]
    with patch.object(custom, "_generic_site_operation", return_value=original), \
         patch.object(custom, "web_client_factory", return_value=object()), \
         patch.object(custom, "is_centauri_functionapp", return_value=False), \
         patch.object(custom, "_generic_settings_operation", side_effect=capture_update), \
         patch.object(custom, "_build_app_settings_output", side_effect=lambda values, *a, **k: values):
        result = custom.update_app_settings(
            SimpleNamespace(cli_ctx=object()), "example-group", "example-app",
            settings=[args[1]],
        )
    assert result == {"UI_LANGUAGE": "en", "UNRELATED": "keep", **values}
    print(json.dumps(result, ensure_ascii=True))
"""


def _branding_block(language):
    text = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    blocks = [
        block for block in re.findall(r"```powershell\n(.*?)```", text, re.S)
        if "$UiQuestions = @(" in block
    ]
    assert len(blocks) == 2
    return blocks[0 if language == "it" else 1]


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _run_branding(shell, language, count, transport, failure=""):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"{shell} not installed")
    with TemporaryDirectory(prefix=".branding proof [local] ", dir=ROOT) as directory:
        work = Path(directory)
        probe = work / "argv probe.py"
        probe.write_text(PROBE, encoding="utf-8")
        command = f"& {_literal(sys.executable)} {_literal(probe)}"
        if transport == "cmd":
            wrapper = work / "az probe.cmd"
            wrapper.write_text(
                f'@echo off\n"{sys.executable}" "{probe}" %*\n', encoding="utf-8"
            )
            command = f"& {_literal(wrapper)}"
        block = _branding_block(language)
        questions = re.search(r"\$UiQuestions = @\(\n(.*?)\n\)", block, re.S)
        assert questions
        expected = re.findall(r"'([^']*)'", questions[1])[:count]
        # Also exercise JSON quotes and accented text across native argv boundaries.
        if count == 1:
            expected = ['Dov\'è il servizio "Orientamento"?']
        block = block[:questions.start()] + (
            "$UiQuestions = @(" + ",".join(_literal(q) for q in expected) + ")"
        ) + block[questions.end():]
        assert len(re.findall(r"(?m)^  az ", block)) == 2
        block = re.sub(r"(?m)^  az ", lambda _: f"  {command} ", block)
        assert not re.search(r"(?m)^\s*az ", block)
        script = (
            "$ErrorActionPreference = 'Stop'\n"
            f"Set-Location -LiteralPath {_literal(work)}\n"
            "Write-Output ('PowerShell=' + $PSVersionTable.PSVersion)\n"
            + block
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        log = work / "argv.jsonl"
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            cwd=work,
            env={**os.environ, "BRANDING_PROBE_LOG": str(log),
                 "BRANDING_PROBE_FAILURE": failure},
            capture_output=True, text=True, timeout=30,
        )
        assert log.exists(), result.stderr
        records = [
            json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
        ]
        assert ("PowerShell=5.1." if shell == "powershell" else "PowerShell=7.") in result.stdout
        assert (result.returncode != 0) == bool(failure), result.stderr
        assert len(records) == (1 if failure == "settings" else 2)
        record = records[0]
        assert record["args"] == [
            "webapp", "config", "appsettings", "set",
            "--subscription", "REPLACE_WITH_SUBSCRIPTION_ID",
            "--resource-group", "REPLACE_WITH_RESOURCE_GROUP",
            "--name", "REPLACE_WITH_APP_SERVICE_NAME",
            "--settings", "@" + record["path"], "--output", "none",
        ]
        assert " " in record["path"]
        assert not record["bom"]
        assert not Path(record["path"]).exists()
        assert not list(work.glob("ui settings *.json"))
        values = record["settings"]
        assert len(values) == 7 and all(key.startswith("UI_") for key in values)
        assert "UI_LANGUAGE" not in values
        assert all(isinstance(value, str) for value in values.values())
        assert json.loads(values["UI_SUGGESTED_QUESTIONS"]) == expected
        ui = AppSettings.from_environment({"UI_LANGUAGE": language, **values}).ui_config
        assert ui.language == language
        assert ui.suggested_questions == expected
        assert ui.organization_name == (
            "Università Esempio" if language == "it" else "Example University"
        )
        if count == 0:
            assert values["UI_SUGGESTED_QUESTIONS"] == "[]"
        return values


@pytest.mark.parametrize("shell", ["powershell", "pwsh"])
@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("count", [2, 1, 0])
@pytest.mark.parametrize("transport", ["native", "cmd"])
def test_branding_json_survives_native_arguments(shell, language, count, transport):
    _run_branding(shell, language, count, transport)


@pytest.mark.parametrize("shell", ["powershell", "pwsh"])
@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("failure", ["settings", "restart"])
def test_branding_failure_stops_and_removes_file(shell, language, failure):
    _run_branding(shell, language, 2, "cmd", failure)


def test_installed_azure_cli_expands_file_and_merges_dictionary_offline():
    az = shutil.which("az")
    if not az or Path(az).suffix.lower() != ".cmd":
        pytest.skip("Windows Azure CLI installation not available")
    cli_python = Path(az).parent.parent / "python.exe"
    if not cli_python.is_file():
        pytest.skip("Azure CLI bundled interpreter not available")
    values = _run_branding("powershell", "it", 2, "cmd")
    with TemporaryDirectory(prefix=".cli parser proof ", dir=ROOT) as directory:
        settings = Path(directory) / "ui settings.json"
        settings.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [str(cli_python), "-IB", "-c", CLI_PARSER_PROBE, str(settings)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        merged = json.loads(result.stdout)
        assert merged == {"UI_LANGUAGE": "en", "UNRELATED": "keep", **values}
        assert AppSettings.from_environment(merged).ui_config.language == "en"
