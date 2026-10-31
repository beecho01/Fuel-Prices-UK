"""Tests for config entry setup/unload wiring: shared API clients and the startup refresh.

hass is mocked out; FuelPricesAPI is replaced so no session or network is
involved. The helpers behind this are covered in test_coordinator_shared_client.py;
these check that setup and unload actually use them.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady

import custom_components.fuel_prices_uk as integration
from custom_components.fuel_prices_uk.const import (
    CACHE_REFRESH_MARGIN_SECONDS,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_FUELTYPES,
    CONF_LOCATION,
    CONF_RADIUS,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from tests.helpers import make_config_entry


def _fake_hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    def _create_task(coro, *args, **kwargs):
        coro.close()  # the startup refresh is not under test here
        return MagicMock()

    hass.async_create_task = MagicMock(side_effect=_create_task)
    hass.async_create_background_task = MagicMock(side_effect=_create_task)
    return hass


def _entry(
    entry_id: str,
    *,
    client_id: str = "id",
    client_secret: str = "secret",
    options: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> ConfigEntry:
    return make_config_entry(
        {
            CONF_CLIENT_ID: client_id,
            CONF_CLIENT_SECRET: client_secret,
            CONF_LOCATION: {"latitude": 51.5, "longitude": -0.12},
            CONF_RADIUS: 8.0,
            CONF_FUELTYPES: ["E10"],
            CONF_UPDATE_INTERVAL: 3600,
            **(data or {}),
        },
        options,
        entry_id=entry_id,
        title=f"Fuel Prices UK - {entry_id}",
    )


@pytest.fixture
def fake_api():
    with patch.object(integration, "FuelPricesAPI", side_effect=lambda *a, **kw: MagicMock()) as factory:
        yield factory


async def test_entries_with_the_same_credentials_share_one_client(fake_api) -> None:
    hass = _fake_hass()
    home, work, other = _entry("home"), _entry("work"), _entry("other", client_id="other-id")

    for entry in (home, work, other):
        assert await integration.async_setup_entry(hass, entry)

    coordinators = hass.data[DOMAIN]
    assert coordinators["home"].api_client is coordinators["work"].api_client
    assert coordinators["other"].api_client is not coordinators["home"].api_client
    assert fake_api.call_count == 2


async def test_unload_keeps_shared_client_until_last_entry_goes(fake_api) -> None:
    hass = _fake_hass()
    home, work = _entry("home"), _entry("work")
    await integration.async_setup_entry(hass, home)
    await integration.async_setup_entry(hass, work)
    shared = hass.data[DOMAIN]["home"].api_client

    assert await integration.async_unload_entry(hass, home)
    assert "home" not in hass.data[DOMAIN]
    assert hass.data[DOMAIN][integration.DATA_API_CLIENTS][("id", "secret")].api is shared

    assert await integration.async_unload_entry(hass, work)
    assert hass.data[DOMAIN][integration.DATA_API_CLIENTS] == {}


async def test_setup_starts_one_background_refresh_per_entry(fake_api) -> None:
    hass = _fake_hass()

    await integration.async_setup_entry(hass, _entry("home"))
    await integration.async_setup_entry(hass, _entry("work"))

    # Home Assistant waits for ordinary tasks before it finishes starting, so the
    # refresh must be a background task or it holds up startup (issue #20).
    assert hass.async_create_background_task.call_count == 2
    hass.async_create_task.assert_not_called()
    hass.config_entries.async_forward_entry_setups.assert_awaited()


async def test_cache_max_age_follows_update_interval(fake_api) -> None:
    hass = _fake_hass()

    await integration.async_setup_entry(hass, _entry("home", data={CONF_UPDATE_INTERVAL: 900}))

    coordinator = hass.data[DOMAIN]["home"]
    assert coordinator.update_interval == timedelta(seconds=900)
    assert coordinator._cache_max_age == 900 - CACHE_REFRESH_MARGIN_SECONDS


async def test_options_override_entry_data(fake_api) -> None:
    hass = _fake_hass()
    entry = _entry("home", options={CONF_UPDATE_INTERVAL: 1800, CONF_RADIUS: 3.0})

    await integration.async_setup_entry(hass, entry)

    coordinator = hass.data[DOMAIN]["home"]
    assert coordinator.update_interval == timedelta(seconds=1800)
    assert coordinator.radius == 3.0


async def test_missing_credentials_are_not_ready(fake_api) -> None:
    hass = _fake_hass()

    with pytest.raises(ConfigEntryNotReady):
        await integration.async_setup_entry(hass, _entry("home", client_secret=" "))

    assert fake_api.call_count == 0
