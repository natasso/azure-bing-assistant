"""Bounded, local-only defaults for the interactive installer, never credentials."""

from __future__ import annotations

import copy
import json
import os
import re
import stat
import tempfile
from pathlib import Path

from .config import (
    ConfigurationError, validate_azure_name, validate_identifier,
    validate_resource_group, validate_ui_language, validate_websites,
)
from .installer_messages import InstallerMessageError


class WizardDraftError(InstallerMessageError, RuntimeError):
    """The installer cannot safely read, save or remove its local draft."""


_INVALID = "Invalid installer draft (.azure/installer-draft.json). Use install --reset-wizard to start again."
_IO = "Cannot access installer draft (.azure/installer-draft.json). Check local permissions and path; use install --reset-wizard only to discard it."
_CHANGED = "Installer draft changed on disk. Stop other installers and retry; use install --reset-wizard to discard it."
MAX_DRAFT_BYTES = 65536
_FIELDS = {
    "language", "tenant_id", "subscription_id", "resource_group", "create_group",
    "location", "model", "capacity", "chatbot_name", "environment_name",
    "deployment_name", "use_search", "domains", "domain_more",
}


def _validate(answers: object) -> None:
    def require(condition: bool) -> None:
        if not condition:
            raise WizardDraftError(_INVALID)

    require(type(answers) is dict and not (answers.keys() - _FIELDS))
    for name, value in answers.items():
        if name in {"create_group", "use_search", "domain_more"}:
            require(type(value) is bool)
        elif name == "capacity":
            require(type(value) is int and 1 <= value <= 2**63 - 1)
        elif name == "model":
            require(type(value) is dict and set(value) == {"name", "version", "format", "sku"})
            for key, part in value.items():
                require(type(part) is str)
                validate_azure_name(key, part)
        elif name == "domains":
            require(type(value) is list and len(value) <= 100)
            seen = set()
            for rule in value:
                # Missing policy marks validated text awaiting its yes/no answer.
                require(type(rule) is dict and set(rule) in (
                    {"domain"}, {"domain", "include_subdomains"},
                ))
                require(type(rule["domain"]) is str)
                domain = validate_websites([rule["domain"]])[0]
                require(domain == rule["domain"] and domain not in seen)
                seen.add(domain)
                if "include_subdomains" in rule:
                    require(type(rule["include_subdomains"]) is bool)
        else:
            require(type(value) is str and 1 <= len(value) <= 128)
            if name == "language":
                validate_ui_language(value)
            elif name in {"tenant_id", "subscription_id"}:
                require(re.fullmatch(r"[A-Za-z0-9-]+", value) is not None)
            elif name == "location":
                require(re.fullmatch(r"[a-z][a-z0-9]{2,31}", value) is not None)
            elif name == "resource_group":
                validate_resource_group(value)
            elif name in {"chatbot_name", "environment_name"}:
                validate_identifier(name, value)
            else:
                validate_azure_name(name, value)
    require(("tenant_id" in answers) == ("subscription_id" in answers))
    for child, parent in (
        ("resource_group", "create_group"), ("create_group", "subscription_id"),
        ("location", "subscription_id"), ("model", "location"), ("capacity", "model"),
        ("environment_name", "subscription_id"), ("deployment_name", "subscription_id"),
        ("domain_more", "domains"),
    ):
        require(child not in answers or parent in answers)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise WizardDraftError(_INVALID)
        result[key] = value
    return result


class WizardDraft:
    """One explicitly located file. Construction does not read ambient state."""

    def __init__(self, project: Path) -> None:
        self.project = project.absolute()
        self.path = self.project / ".azure" / "installer-draft.json"
        self._answers: dict = {}
        self._stamp: tuple | None = None
        self._loaded = False

    def get(self, name: str, default=None):
        return copy.deepcopy(self._answers.get(name, default))

    @property
    def has_answers(self) -> bool:
        return bool(self._answers)

    def _file_state(self) -> tuple | None:
        if self.project.resolve(strict=True) != self.project:
            raise WizardDraftError(_IO)
        for path in (self.path.parent, self.path):
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if (
                stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or (path == self.path.parent and not stat.S_ISDIR(info.st_mode))
                or (path == self.path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
            ):
                raise WizardDraftError(_IO)
            if path == self.path:
                return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        return None

    def load(self) -> None:
        try:
            stamp = self._file_state()
            answers = {}
            if stamp is not None:
                with self.path.open("rb") as stream:
                    raw = stream.read(MAX_DRAFT_BYTES + 1)
                if len(raw) > MAX_DRAFT_BYTES:
                    raise WizardDraftError(_INVALID)
                document = json.loads(raw, object_pairs_hook=_unique_object)
                if (
                    type(document) is not dict or set(document) != {"version", "answers"}
                    or type(document["version"]) is not int or document["version"] != 1
                ):
                    raise WizardDraftError(_INVALID)
                answers = document["answers"]
                _validate(answers)
                if self._file_state() != stamp:
                    raise WizardDraftError(_CHANGED)
            self._answers, self._stamp, self._loaded = answers, stamp, True
        except (ValueError, UnicodeError, RecursionError, ConfigurationError) as exc:
            raise WizardDraftError(_INVALID) from exc
        except OSError as exc:
            raise WizardDraftError(_IO) from exc

    def update(self, *, remove: tuple[str, ...] = (), **values: object) -> None:
        if not self._loaded:
            raise WizardDraftError(_IO)
        answers = copy.deepcopy(self._answers)
        for key in remove:
            answers.pop(key, None)
        answers.update(copy.deepcopy(values))
        try:
            _validate(answers)
        except ConfigurationError as exc:
            raise WizardDraftError(_INVALID) from exc
        raw = json.dumps({"version": 1, "answers": answers}, ensure_ascii=True).encode("utf-8")
        if len(raw) > MAX_DRAFT_BYTES:
            raise WizardDraftError(_INVALID)
        temporary = None
        try:
            if self._file_state() != self._stamp:
                raise WizardDraftError(_CHANGED)
            if answers == self._answers:
                return
            self.path.parent.mkdir(exist_ok=True)
            self._file_state()
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.path.parent, prefix=".installer-draft-", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if self._file_state() != self._stamp:
                raise WizardDraftError(_CHANGED)
            os.replace(temporary, self.path)
            temporary = None
            self._stamp = self._file_state()
            self._answers = answers
        except OSError as exc:
            raise WizardDraftError(_IO) from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError as exc:
                    raise WizardDraftError(_IO) from exc

    def clear(self, *, reset: bool = False) -> None:
        try:
            stamp = self._file_state()
            if not reset and (not self._loaded or stamp != self._stamp):
                raise WizardDraftError(_CHANGED)
            if stamp is not None:
                self.path.unlink()
            self._answers, self._stamp, self._loaded = {}, None, True
        except OSError as exc:
            raise WizardDraftError(_IO) from exc
