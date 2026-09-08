import pytest

from azure_bing_assistant.config import (
    ConfigurationError,
    InstallerConfig,
    KnowledgeMode,
)


@pytest.mark.parametrize("mode", ["off", "searchBlob"])
def test_supported_modes(mode):
    assert InstallerConfig.from_values(mode, environ={}).knowledge_mode.value == mode


@pytest.mark.parametrize("mode", ["", "search", "OFF", "crawler", "nfs"])
def test_unsupported_mode_fails(mode):
    with pytest.raises(ConfigurationError):
        InstallerConfig.from_values(mode, environ={})


def test_invalid_environment_variable_is_validated():
    with pytest.raises(ConfigurationError):
        InstallerConfig.from_values("off", environ={"AZURE_ENV_NAME": "../unsafe"})


def test_explicit_empty_identifier_is_not_defaulted():
    with pytest.raises(ConfigurationError):
        InstallerConfig.from_values("off", environment_name="", environ={})


def test_invalid_boolean_environment_is_not_silently_false():
    with pytest.raises(ConfigurationError):
        InstallerConfig.from_values(
            "off",
            environ={"CREATE_RESOURCE_GROUP": "sometimes"},
        )


def test_strict_websites_fail_closed_without_supported_integration():
    with pytest.raises(ConfigurationError, match="not provisioned"):
        InstallerConfig(
            environment_name="chatbot-dev",
            location="westeurope",
            knowledge_mode=KnowledgeMode.OFF,
            strict_websites=True,
        )


def test_runtime_foundry_configuration_is_paired_and_validated():
    from app.backend.config import AppSettings

    with pytest.raises(ValueError, match="configured together"):
        AppSettings(
            environment="test",
            foundry_project_endpoint=(
                "https://example.services.ai.azure.com/api/projects/project"
            ),
        )
    with pytest.raises(ValueError, match="safe HTTPS"):
        AppSettings(
            environment="test",
            foundry_project_endpoint="https://example.invalid/api/projects/project",
            chatbot_name="generic-assistant",
        )

    settings = AppSettings.from_environment(
        {
            "APP_ENV": "test",
            "FOUNDRY_PROJECT_ENDPOINT": (
                "https://example.services.ai.azure.com/api/projects/project"
            ),
            "CHATBOT_NAME": "generic-assistant",
        }
    )
    assert settings.chatbot_name == "generic-assistant"


def test_runtime_ui_environment_is_bounded_and_deterministic():
    from app.backend.config import AppSettings

    settings = AppSettings.from_environment(
        {
            "APP_ENV": "test",
            "UI_PRODUCT_NAME": " Product ",
            "UI_ORGANIZATION_NAME": " Example Org ",
            "UI_ASSISTANT_NAME": " Helper ",
            "UI_WELCOME_TITLE": " Welcome ",
            "UI_WELCOME_SUBTITLE": " Ask a safe question. ",
            "UI_DISCLAIMER": " AI output requires verification. ",
            "UI_SUGGESTED_QUESTIONS": '[" First? ","Second?"]',
            "AGENT_TIMEOUT_SECONDS": "45",
        }
    )

    assert settings.ui_config.product_name == "Product"
    assert settings.ui_config.language == "it"
    assert settings.ui_config.suggested_questions == ["First?", "Second?"]
    assert settings.agent_timeout_seconds == 45


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("UI_PRODUCT_NAME", ""),
        ("UI_ASSISTANT_NAME", "x" * 81),
        ("UI_DISCLAIMER", "unsafe\x00text"),
        ("UI_SUGGESTED_QUESTIONS", "not-json"),
        ("UI_SUGGESTED_QUESTIONS", '["1","2","3","4","5","6"]'),
        ("UI_SUGGESTED_QUESTIONS", '["", "ok"]'),
        ("UI_LANGUAGE", "fr"),
        ("AGENT_TIMEOUT_SECONDS", "301"),
    ],
)
def test_invalid_explicit_runtime_ui_values_fail_visibly(name, value):
    from app.backend.config import AppSettings

    with pytest.raises(ValueError):
        AppSettings.from_environment({"APP_ENV": "test", name: value})


def test_installer_language_defaults_to_it_without_freezing_builtin_copy():
    config = InstallerConfig.from_values("off", environ={})

    assert config.ui_language is None
    assert config.public_parameters()["uiLanguage"] == "it"
    environment = config.azd_environment_values()
    assert environment["UI_LANGUAGE"] == "it"
    assert not any(
        name in environment
        for name in (
            "UI_PRODUCT_NAME",
            "UI_ORGANIZATION_NAME",
            "UI_ASSISTANT_NAME",
            "UI_WELCOME_TITLE",
            "UI_WELCOME_SUBTITLE",
            "UI_DISCLAIMER",
            "UI_SUGGESTED_QUESTIONS",
        )
    )


def test_installer_validates_language_and_preserves_explicit_empty_suggestions():
    config = InstallerConfig.from_values(
        "off",
        environ={
            "UI_LANGUAGE": "en",
            "UI_SUGGESTED_QUESTIONS": "[]",
        },
    )

    assert config.ui_language == "en"
    assert config.ui_suggestions == ()
    assert config.azd_environment_values()["UI_SUGGESTED_QUESTIONS"] == "[]"
    with pytest.raises(ConfigurationError, match="UI_LANGUAGE"):
        InstallerConfig.from_values("off", environ={"UI_LANGUAGE": "invalid"})
