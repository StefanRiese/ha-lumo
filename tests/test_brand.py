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


async def test_home_assistant_serves_the_icon(
    hass, hass_client_no_auth, enable_custom_integrations
) -> None:
    """Home Assistant 2026.3+ serves `brand/` of a custom integration."""
    from homeassistant.loader import Integration
    from homeassistant.setup import async_setup_component

    if not hasattr(Integration, "has_branding"):
        pytest.skip("this Home Assistant does not serve brand images of custom integrations")
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client_no_auth()
    token = hass.data["brands"][0]
    response = await client.get(f"/api/brands/integration/lumo/icon.png?token={token}")
    assert response.status == 200
    assert response.content_type == "image/png"
    assert await response.read() == (BRAND / "icon.png").read_bytes()
