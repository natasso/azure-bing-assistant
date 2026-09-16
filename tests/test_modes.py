import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_search_module_is_conditionally_deployed():
    source = Path("infra/main.bicep").read_text(encoding="utf-8")
    assert "if (knowledgeMode == 'searchBlob')" in source
    assert "knowledgeMode == 'searchBlob' ? searchBlob!.outputs" in source


def test_off_mode_has_no_search_or_storage_module_resources():
    source = Path("infra/main.bicep").read_text(encoding="utf-8")
    module_start = source.index("module searchBlob")
    assert "if (knowledgeMode == 'searchBlob')" in source[module_start : module_start + 120]


def test_storage_disables_public_blob_and_shared_key():
    source = Path("infra/modules/search-blob.bicep").read_text(encoding="utf-8")
    assert "allowBlobPublicAccess: false" in source
    assert "allowSharedKeyAccess: false" in source
    assert "disableLocalAuth: true" in source


def test_bing_grounding_and_model_are_required_in_both_modes():
    main = Path("infra/main.bicep").read_text(encoding="utf-8")
    foundry = Path("infra/modules/foundry.bicep").read_text(encoding="utf-8")
    assert "module bing" not in main
    assert "BING_CONNECTION_NAME" not in main
    assert not Path("infra/modules/bing.bicep").exists()
    assert "@allowed([\n  true\n])\n#disable-next-line no-unused-params\nparam bingTermsAccepted bool" in main
    assert "accounts/deployments@2025-06-01" in foundry
    assert "accounts/projects@2025-06-01'" in foundry
    assert "accounts/projects@2025-06-01-preview" not in foundry
    assert "identity: {\n    type: 'SystemAssigned'\n  }" in foundry


@pytest.fixture(scope="module", params=("foundry", "main"))
def compiled_foundry_template(request):
    compiler = shutil.which("bicep")
    if compiler is None:
        azure_config = Path(os.environ.get("AZURE_CONFIG_DIR", Path.home() / ".azure"))
        installed = azure_config / "bin" / ("bicep.exe" if os.name == "nt" else "bicep")
        if not installed.is_file():
            pytest.skip("Local Bicep compiler not installed; no download or Azure login")
        compiler = str(installed)

    infra = Path(__file__).resolve().parents[1] / "infra"
    source = infra / "modules" / "foundry.bicep" if request.param == "foundry" else infra / "main.bicep"
    result = subprocess.run(
        [compiler, "build", str(source), "--stdout", "--no-restore"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    template = json.loads(result.stdout)
    if request.param == "main":
        foundry = next(
            resource for resource in template["resources"]
            if resource["type"] == "Microsoft.Resources/deployments"
            and resource["name"] == "foundry"
        )
        template = foundry["properties"]["template"]
    return template


def test_compiled_foundry_serializes_account_child_writes(compiled_foundry_template):
    resources = {
        resource["type"]: resource for resource in compiled_foundry_template["resources"]
    }
    account_type = "Microsoft.CognitiveServices/accounts"
    account_id = f"[resourceId('{account_type}', parameters('accountName'))]"
    project_id = f"[resourceId('{account_type}/projects', parameters('accountName'), 'project')]"

    assert set(resources) == {
        account_type,
        f"{account_type}/projects",
        f"{account_type}/deployments",
        "Microsoft.Authorization/roleAssignments",
        "Microsoft.Resources/deployments",
    }
    assert resources[account_type].get("dependsOn", []) == []
    assert resources[f"{account_type}/projects"]["dependsOn"] == [account_id]
    assert set(resources[f"{account_type}/deployments"]["dependsOn"]) == {
        account_id, project_id,
    }
    assignments = [
        resource for resource in compiled_foundry_template["resources"]
        if resource["type"] == "Microsoft.Authorization/roleAssignments"
    ]
    assert len(assignments) == 1
    web_assignment = assignments[0]
    assert web_assignment["dependsOn"] == [account_id]
    assert web_assignment["properties"]["principalId"] == "[parameters('webPrincipalId')]"
    project_module = resources["Microsoft.Resources/deployments"]
    assert project_module["name"] == "project-access"
    assert project_id in project_module["dependsOn"]
    assert "identity.principalId" in project_module["properties"]["parameters"]["projectPrincipalId"]["value"]
    assert project_module["properties"]["parameters"]["roleDefinitionId"]["value"] == "[parameters('cognitiveUserRoleDefinitionId')]"
    project_assignment, = project_module["properties"]["template"]["resources"]
    assert project_assignment["type"] == "Microsoft.Authorization/roleAssignments"
    assert project_assignment["properties"] == {
        "roleDefinitionId": "[parameters('roleDefinitionId')]",
        "principalId": "[parameters('projectPrincipalId')]",
        "principalType": "ServicePrincipal",
    }
    assert project_assignment["scope"] == "[format('Microsoft.CognitiveServices/accounts/{0}', parameters('accountName'))]"
