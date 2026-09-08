from pathlib import Path

from app.backend.config import AppSettings
from azure_bing_assistant.agent import transform_citations


def test_production_ignores_obsolete_application_auth_environment_switch():
    settings = AppSettings.from_environment({
        "APP_ENV": "production",
        "AUTH_BYPASS": "not-a-boolean",
    })

    assert settings.environment == "production"
    assert not hasattr(settings, "auth_bypass")


def test_citations_never_expose_raw_infrastructure_values():
    raw = [
        {
            "source": (
                "https://private-service.invalid/container/document.pdf"
                "?signature=credential"
            ),
            "title": "storage-account-name",
        }
    ]

    projected = transform_citations(raw)
    serialized = f"{projected[0].label} {projected[0].reference}"

    assert projected[0].label == "Document 1"
    assert projected[0].reference.startswith("documents/")
    for forbidden in ("https:", "private-service", "container", "signature", "credential", ".pdf"):
        assert forbidden not in serialized


def test_duplicate_citations_are_collapsed():
    citations = transform_citations([{"source": "same"}, {"source": "same"}])
    assert len(citations) == 1


def test_bing_public_citations_preserve_required_exact_url():
    url = "https://www.example.org/news/item?ref=bing"
    citations = transform_citations([{"type": "url_citation", "url": url}])
    query = transform_citations(
        [{"type": "bing_query", "url": "https://www.bing.com/search?q=example"}]
    )

    assert citations[0].reference == url
    assert query[0].reference == "https://www.bing.com/search?q=example"


def test_infrastructure_endpoint_is_rejected_even_if_marked_web():
    citations = transform_citations(
        [{"type": "url_citation", "url": "https://private.blob.core.windows.net/data"}]
    )
    assert citations == []


def test_no_custom_conversation_key_or_storage_infrastructure():
    root = Path(__file__).parents[1]
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".py", ".js", ".md", ".bicep", ".toml", ".yml", ".yaml"}
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
    ).lower()

    for forbidden in (
        "conversation_" + "signing_key",
        "continuation_" + "key_blob",
        "provision" + "-lock",
        "blob " + "lease",
        "x-ms-" + "lease",
        "aba_" + "session",
        "".join(("h", "m", "a", "c", "-", "s", "h", "a", "2", "5", "6")),
    ):
        assert forbidden not in text
