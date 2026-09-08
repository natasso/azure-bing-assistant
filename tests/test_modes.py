from pathlib import Path


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
    bing = Path("infra/modules/bing.bicep").read_text(encoding="utf-8")

    assert "module bing" in main
    assert "@allowed([\n  true\n])\nparam bingTermsAccepted bool" in main
    assert "accounts/deployments@2025-06-01" in foundry
    assert "accounts/projects@2025-06-01'" in foundry
    assert "accounts/projects@2025-06-01-preview" not in foundry
    assert "identity: {\n    type: 'SystemAssigned'\n  }" in foundry
    assert "kind: 'Bing.Grounding'" in bing
    assert "listKeys(" in bing
    assert "output" not in "\n".join(
        line for line in bing.splitlines() if "key:" in line
    )
