"""Tests for the options flow's location-method switches.

The flow handler is driven directly, with hass mocked out, the same way the
coordinator tests run on bare instances.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.data_entry_flow import FlowResultType

from custom_components.fuel_prices_uk.config_flow import OptionsFlowHandler
from custom_components.fuel_prices_uk.const import (
    CONF_ADDRESS,
    CONF_CHEAPEST_COUNT,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_TRACKER,
    CONF_FUELTYPES,
    CONF_LOCATION,
    CONF_LOCATION_METHOD,
    CONF_MAX_DATA_AGE_DAYS,
    CONF_NEAREST_COUNT,
    CONF_RADIUS,
    CONF_UPDATE_INTERVAL,
    MILES_TO_KM,
)
from custom_components.fuel_prices_uk.sensor import _derive_location_strings
from tests.helpers import make_config_entry, with_options

TRACKER = "device_tracker.car"


def _address_entry() -> ConfigEntry:
    """An entry originally set up from an address, so entry.data holds that address."""
    return make_config_entry(
        {
            CONF_CLIENT_ID: "id",
            CONF_CLIENT_SECRET: "secret",
            CONF_LOCATION_METHOD: "address",
            CONF_ADDRESS: "SW1A 1AA",
            CONF_LOCATION: {"latitude": 51.501, "longitude": -0.142},
            CONF_RADIUS: 8.0,
            CONF_FUELTYPES: ["E10"],
            CONF_UPDATE_INTERVAL: 3600,
        },
        title="Fuel Prices UK - SW1A 1AA",
    )


def _flow(entry: ConfigEntry) -> OptionsFlowHandler:
    # OptionsFlowWithConfigEntry reports its own deprecation through HA's frame
    # helper, which needs a running hass; custom integrations are exempt anyway.
    with patch("homeassistant.config_entries.report_usage"):
        flow = OptionsFlowHandler(entry)
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = entry
    flow.hass.states.get.return_value = SimpleNamespace(
        state="not_home", attributes={"latitude": 52.2, "longitude": -1.5}
    )
    flow.handler = entry.entry_id
    flow.flow_id = "test_flow"
    flow.context = {}
    return flow


def _saved_options(result: ConfigFlowResult) -> dict[str, Any]:
    """Return the options a finished flow saves, failing if it didn't finish."""
    assert result.get("type") is FlowResultType.CREATE_ENTRY
    return dict(result.get("data") or {})


def _form_errors(result: ConfigFlowResult) -> dict[str, str]:
    """Return the errors on a re-shown form, failing if the flow didn't show one."""
    assert result.get("type") is FlowResultType.FORM
    return dict(result.get("errors") or {})


def _common_input() -> dict[str, Any]:
    return {
        CONF_UPDATE_INTERVAL: 1800,
        CONF_RADIUS: 3.0,
        CONF_FUELTYPES: ["E10", "B7"],
        CONF_CHEAPEST_COUNT: 2,
        CONF_NEAREST_COUNT: 1,
    }


async def test_switching_to_map_blanks_the_old_address() -> None:
    entry = _address_entry()
    user_input = {**_common_input(), CONF_LOCATION: {"latitude": 52.2, "longitude": -1.5}}

    options = _saved_options(await _flow(entry).async_step_location_map(user_input))

    # Options are merged over entry.data, so the key must be present and blank
    # rather than missing, or the old address would still name the sensors.
    assert options[CONF_ADDRESS] == ""
    assert options[CONF_LOCATION_METHOD] == "map"
    assert options[CONF_LOCATION] == {"latitude": 52.2, "longitude": -1.5}
    assert options[CONF_RADIUS] == round(3.0 * MILES_TO_KM, 1)
    assert options[CONF_UPDATE_INTERVAL] == 1800

    label, _slug = _derive_location_strings(with_options(entry, options))
    assert "SW1A 1AA" not in label
    assert label.startswith("52.2000,-1.5000 · ")


async def test_switching_to_device_tracker_blanks_the_old_address() -> None:
    entry = _address_entry()
    user_input = {**_common_input(), CONF_DEVICE_TRACKER: TRACKER}

    options = _saved_options(await _flow(entry).async_step_location_device_tracker(user_input))

    assert options[CONF_ADDRESS] == ""
    assert options[CONF_LOCATION_METHOD] == "device_tracker"
    assert options[CONF_DEVICE_TRACKER] == TRACKER

    label, _slug = _derive_location_strings(with_options(entry, options))
    # With no address or fixed coordinates the label falls back to the entry
    # title. The options flow doesn't retitle the entry, so an entry first set
    # up from an address keeps that address in its title.
    assert label.startswith(f"{entry.title} · ")


async def test_location_entity_can_be_a_tracker_person_or_zone() -> None:
    result = await _flow(_address_entry()).async_step_location_device_tracker(None)

    schema = result["data_schema"].schema
    (entity_selector,) = (value for key, value in schema.items() if key == CONF_DEVICE_TRACKER)
    assert entity_selector.config["domain"] == ["device_tracker", "person", "zone"]


async def test_zone_is_accepted_as_the_location_entity() -> None:
    flow = _flow(_address_entry())
    flow.hass.states.get.return_value = SimpleNamespace(state="0", attributes={"latitude": 51.9, "longitude": -0.4})
    user_input = {**_common_input(), CONF_DEVICE_TRACKER: "zone.work"}

    options = _saved_options(await flow.async_step_location_device_tracker(user_input))

    assert options[CONF_LOCATION_METHOD] == "device_tracker"
    assert options[CONF_DEVICE_TRACKER] == "zone.work"


async def test_map_step_rejects_missing_coordinates() -> None:
    user_input = {**_common_input(), CONF_LOCATION: {"latitude": None, "longitude": None}}

    result = await _flow(_address_entry()).async_step_location_map(user_input)

    assert _form_errors(result) == {CONF_LOCATION: "invalid_location"}


async def test_map_step_requires_at_least_one_sensor_type() -> None:
    user_input = {
        **_common_input(),
        CONF_CHEAPEST_COUNT: 0,
        CONF_NEAREST_COUNT: 0,
        CONF_LOCATION: {"latitude": 52.2, "longitude": -1.5},
    }

    result = await _flow(_address_entry()).async_step_location_map(user_input)

    assert _form_errors(result) == {"base": "neither_option_enabled"}


@pytest.mark.parametrize("step", ["location_map", "location_address", "location_device_tracker"])
async def test_max_data_age_is_required_and_prefilled(step: str) -> None:
    entry = with_options(_address_entry(), {CONF_MAX_DATA_AGE_DAYS: 7})

    result = await getattr(_flow(entry), f"async_step_{step}")(None)

    # An Optional field gets a checkbox in the HA frontend; unticking it drops
    # the key and voluptuous refills the default (the saved value), so the
    # change is silently lost. Required renders no checkbox.
    schema = result["data_schema"].schema
    (key,) = (k for k in schema if k == CONF_MAX_DATA_AGE_DAYS)
    assert isinstance(key, vol.Required)
    assert key.default() == 7


async def test_max_data_age_can_be_set_back_to_zero() -> None:
    entry = with_options(_address_entry(), {CONF_MAX_DATA_AGE_DAYS: 7})
    user_input = {
        **_common_input(),
        CONF_LOCATION: {"latitude": 52.2, "longitude": -1.5},
        CONF_MAX_DATA_AGE_DAYS: 0,
    }

    options = _saved_options(await _flow(entry).async_step_location_map(user_input))

    assert options[CONF_MAX_DATA_AGE_DAYS] == 0
