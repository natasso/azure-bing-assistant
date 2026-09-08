import pytest

from azure_bing_assistant.ingestion import document_upload_guidance


def test_document_guidance_uses_login_auth_and_portal_destination():
    guidance = document_upload_guidance("rg-chatbot", "storageexample", "documents")

    assert "Data storage > Containers > documents" in guidance
    assert "az storage blob upload-batch" in guidance
    assert "--auth-mode login" in guidance
    assert "--account-name storageexample" in guidance
    assert "no upload endpoint" in guidance
    assert "account-key" not in guidance.lower()


def test_document_guidance_rejects_shell_metacharacters():
    with pytest.raises(ValueError):
        document_upload_guidance("rg-chatbot", "storage;example", "documents")
