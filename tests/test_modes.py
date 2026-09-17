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
    assert "module bing 'modules/bing.bicep' = if (webSearchProvider == 'bingCustomSearch')" in main
    assert "BING_CONNECTION_NAME" not in main
    assert Path("infra/modules/bing.bicep").is_file()
    assert "@allowed([\n  true\n])\n#disable-next-line no-unused-params\nparam bingTermsAccepted bool" in main
    assert "accounts/deployments@2025-06-01" in foundry
    assert "accounts/projects@2025-06-01'" in foundry
    assert "accounts/projects@2025-06-01-preview" not in foundry
    assert "identity: {\n    type: 'SystemAssigned'\n  }" in foundry


def _compile_bicep(source):
    compiler = shutil.which("bicep")
    if compiler is None:
        azure_config = Path(os.environ.get("AZURE_CONFIG_DIR", Path.home() / ".azure"))
        installed = azure_config / "bin" / ("bicep.exe" if os.name == "nt" else "bicep")
        if not installed.is_file():
            pytest.skip("Local Bicep compiler not installed; no download or Azure login")
        compiler = str(installed)

    result = subprocess.run(
        [compiler, "build", str(source), "--stdout", "--no-restore"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def compiled_main_template():
    return _compile_bicep(Path(__file__).resolve().parents[1] / "infra" / "main.bicep")


@pytest.fixture(scope="module", params=("foundry", "main"))
def compiled_foundry_template(request):
    if request.param == "main":
        template = request.getfixturevalue("compiled_main_template")
        foundry = next(
            resource for resource in template["resources"]
            if resource["type"] == "Microsoft.Resources/deployments"
            and resource["name"] == "foundry"
        )
        return foundry["properties"]["template"]
    return _compile_bicep(Path(__file__).resolve().parents[1] / "infra" / "modules" / "foundry.bicep")


def test_compiled_custom_search_has_conditional_resources_and_keyless_outputs(compiled_main_template):
    modules = {
        resource["name"]: resource for resource in compiled_main_template["resources"]
        if resource["type"] == "Microsoft.Resources/deployments"
    }
    bing = modules["bing-custom-search"]
    connection = modules["bing-custom-search-connection"]
    for module in (bing, connection):
        assert module["condition"] == "[equals(parameters('webSearchProvider'), 'bingCustomSearch')]"
        assert "knowledgeMode" not in module["condition"]
    account, configuration = bing["properties"]["template"]["resources"]
    assert account["kind"] == "Bing.GroundingCustomSearch"
    assert account["sku"] == {"name": "G2"}
    assert account["location"] == "global"
    assert configuration["apiVersion"] == "2025-05-01-preview"
    policy = configuration["properties"]
    assert policy["blockedDomains"] == [] and policy["pinnedDomains"] == []
    assert policy["copy"][0]["input"] == {
        "domain": "[format('https://{0}', parameters('allowedDomains')[copyIndex('allowedDomains')])]",
        "includeSubPages": True, "boostLevel": "Default",
    }
    connection_resource, = connection["properties"]["template"]["resources"]
    settings = connection_resource["properties"]
    assert settings["category"] == "GroundingWithCustomSearch"
    assert settings["authType"] == "ApiKey"
    assert settings["credentials"]["key"] == (
        "[listKeys(resourceId('Microsoft.Bing/accounts', parameters('bingAccountName')), '2020-06-10').key1]"
    )
    for template in (
        compiled_main_template, bing["properties"]["template"], connection["properties"]["template"],
    ):
        assert "listKeys" not in json.dumps(template["outputs"])
        assert "credentials" not in json.dumps(template["outputs"])
    for name in ("RESOURCE_ID", "CONNECTION_ID", "INSTANCE_NAME"):
        assert "bingCustomSearch" in compiled_main_template["outputs"]["BING_CUSTOM_SEARCH_" + name]["value"]
    web = modules["webapp"]
    assert "bing-custom-search" not in json.dumps(web.get("dependsOn"))
    assert "bingCustomSearchConnectionId" in web["properties"]["parameters"]
    assert "bingCustomSearchInstanceName" in web["properties"]["parameters"]


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
    # Bicep versions emit either a relative scope or the equivalent full resource ID.
    assert project_assignment["scope"] in {
        "[format('Microsoft.CognitiveServices/accounts/{0}', parameters('accountName'))]",
        account_id,
    }
