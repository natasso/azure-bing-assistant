"""Instance-scoped installer messages; provider output and machine keys stay unchanged."""

from __future__ import annotations

from dataclasses import dataclass

from .localization import SUPPORTED_UI_LANGUAGES, load_catalog


@dataclass(frozen=True)
class InstallerMessages:
    language: str = "en"

    def __post_init__(self) -> None:
        if self.language not in SUPPORTED_UI_LANGUAGES:
            raise ValueError("Unsupported installer language: " + str(self.language))

    def __call__(self, message: str, **values: object) -> str:
        template = load_catalog(self.language)["installer"].get(message, message)
        rendered = {
            name: value.render(self.language) if isinstance(value, InstallerMessageError) else value
            for name, value in values.items()
        }
        return template.format(**rendered) if values else template


class InstallerMessageError(Exception):
    """Keep structured message arguments until the caller chooses a language."""

    def __init__(self, message: str, **values: object) -> None:
        self.message = message
        self.values = values
        super().__init__(InstallerMessages()(message, **values))

    def render(self, language: str) -> str:
        return InstallerMessages(language)(self.message, **self.values)
