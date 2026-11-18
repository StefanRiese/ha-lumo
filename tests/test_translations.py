"""en.json and de.json must stay in step: same keys, same placeholders, no empty texts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

TRANSLATIONS = Path(__file__).parent.parent / "custom_components" / "lumo" / "translations"
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = value
    return flat


def _load(language: str) -> dict[str, str]:
    return _flatten(json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")))


def test_same_keys() -> None:
    english, german = _load("en"), _load("de")
    assert sorted(set(english) - set(german)) == [], "missing in de.json"
    assert sorted(set(german) - set(english)) == [], "missing in en.json"


@pytest.mark.parametrize("language", ["en", "de"])
def test_no_empty_texts(language: str) -> None:
    assert [key for key, text in _load(language).items() if not text.strip()] == []


def test_same_placeholders() -> None:
    english, german = _load("en"), _load("de")
    differing = {
        key: (sorted(PLACEHOLDER.findall(english[key])), sorted(PLACEHOLDER.findall(german[key])))
        for key in english.keys() & german.keys()
        if sorted(PLACEHOLDER.findall(english[key])) != sorted(PLACEHOLDER.findall(german[key]))
    }
    assert differing == {}


def test_every_entity_translation_key_exists() -> None:
    """Entities use translation keys; a missing one would show a raw key name."""
    from custom_components.lumo.binary_sensor import CANCELLATIONS
    from custom_components.lumo.sensor import SENSORS

    names = _load("en")
    keys = [d.translation_key for d in (*SENSORS, *CANCELLATIONS)]
    keys += [
        "schulportal_connection",
        "caseda_connection",
        "untis_connection",
        "ntfy_connection",
        "updates_connection",
        "update_available",
        "calendar",
        "refresh",
        "homework",
    ]
    prefixes = ("sensor", "binary_sensor", "calendar", "button", "todo")
    missing = [key for key in keys if not any(f"entity.{p}.{key}.name" in names for p in prefixes)]
    assert missing == []
