"""Tests for how the coordinator picks its search location from a device_tracker (issue #10)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import custom_components.fuel_prices_uk as integration

TRACKER = "device_tracker.car"


def _tracker_state(state: str, latitude: float | None = None, longitude: float | None = None) -> SimpleNamespace:
    attributes = {}
    if latitude is not None:
        attributes["latitude"] = latitude
    if longitude is not None:
        attributes["longitude"] = longitude
    return SimpleNamespace(state=state, attributes=attributes)


def _coordinator(states: dict[str, SimpleNamespace]) -> integration.FuelPricesDataUpdateCoordinator:
    coordinator = integration.FuelPricesDataUpdateCoordinator.__new__(integration.FuelPricesDataUpdateCoordinator)
    coordinator.hass = MagicMock()
    coordinator.hass.states.get.side_effect = states.get
    coordinator.location = {}
    coordinator.device_tracker_entity_id = TRACKER
    coordinator._last_tracker_location = None
    return coordinator


def test_tracker_away_from_home_is_used() -> None:
    """A GPS tracker outside every zone reports "not_home" but still has coordinates."""
    coordinator = _coordinator({TRACKER: _tracker_state("not_home", 52.2, -1.5)})

    assert coordinator._resolve_search_coordinates() == (52.2, -1.5)


def test_tracker_in_a_zone_is_used() -> None:
    coordinator = _coordinator({TRACKER: _tracker_state("work", 51.9, -0.4)})

    assert coordinator._resolve_search_coordinates() == (51.9, -0.4)


def test_person_entity_is_used() -> None:
    coordinator = _coordinator({"person.driver": _tracker_state("not_home", 52.2, -1.5)})
    coordinator.device_tracker_entity_id = "person.driver"

    assert coordinator._resolve_search_coordinates() == (52.2, -1.5)


def test_zone_entity_is_used() -> None:
    """A zone's state is the number of people in it, not home/not_home."""
    coordinator = _coordinator({"zone.work": _tracker_state("0", 51.9, -0.4)})
    coordinator.device_tracker_entity_id = "zone.work"

    assert coordinator._resolve_search_coordinates() == (51.9, -0.4)


def test_unavailable_tracker_falls_back_to_last_known_location() -> None:
    states = {TRACKER: _tracker_state("not_home", 52.2, -1.5)}
    coordinator = _coordinator(states)
    coordinator._resolve_search_coordinates()

    states[TRACKER] = _tracker_state("unavailable")

    assert coordinator._resolve_search_coordinates() == (52.2, -1.5)


def test_tracker_without_coordinates_falls_back_to_last_known_location() -> None:
    states = {TRACKER: _tracker_state("home", 51.5, -0.12)}
    coordinator = _coordinator(states)
    coordinator._resolve_search_coordinates()

    # e.g. a router-based tracker: has a state but no GPS attributes
    states[TRACKER] = _tracker_state("not_home")

    assert coordinator._resolve_search_coordinates() == (51.5, -0.12)


def test_no_location_ever_seen_returns_none() -> None:
    coordinator = _coordinator({})

    assert coordinator._resolve_search_coordinates() == (None, None)
