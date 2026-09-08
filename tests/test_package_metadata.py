from pathlib import Path
import tomllib


def test_production_metadata_declares_bounded_async_http_transport():
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert "aiohttp>=3.14.3,<4" in project["project"]["dependencies"]
    assert project["project"]["requires-python"] == ">=3.11"
    assert {
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    }.issubset(project["project"]["classifiers"])


def test_package_metadata_declares_mit_and_includes_license_notices():
    root = Path(__file__).parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["license"] == "MIT"
    assert project["project"]["license-files"] == ["LICENSE", "NOTICE"]
    for name in project["project"]["license-files"]:
        assert (root / name).is_file()
    assert 'Copyright (c) 2026 Donato "natasso" Pasqualicchio' in (
        root / "LICENSE"
    ).read_text(encoding="utf-8")
