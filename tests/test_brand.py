"""The brand images Home Assistant shows for the integration (from 2026.3)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

BRAND = Path(__file__).parents[1] / "custom_components" / "lumo" / "brand"


@pytest.mark.parametrize(("name", "size"), [("icon.png", 256), ("icon@2x.png", 512)])
def test_brand_icon_is_a_square_png(name: str, size: int) -> None:
    data = (BRAND / name).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (size, size)
