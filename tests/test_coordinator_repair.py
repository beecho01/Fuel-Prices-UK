"""Tests for the stale-data Repair logic in FuelPricesDataUpdateCoordinator.

This exercises _record_failure_and_maybe_raise_repair/_clear_stale_data_issue
directly on a bare instance (bypassing DataUpdateCoordinator.__init__, which
needs a real Home Assistant runtime) with hass and issue_registry mocked out.
That keeps this test at the same "pure-logic" depth as the rest of the suite
while still covering the real counting/threshold/reset behaviour - see
GitHub issue #14, where both reporters asked for exactly this kind of
visibility when the coordinator has been failing silently.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import custom_components.fuel_prices_uk as integration
from custom_components.fuel_prices_uk.const import CONSECUTIVE_FAILURE_THRESHOLD, DOMAIN


def _bare_coordinator() -> integration.FuelPricesDataUpdateCoordinator:
    """Build a coordinator instance without running DataUpdateCoordinator.__init__."""
    coordinator = integration.FuelPricesDataUpdateCoordinator.__new__(integration.FuelPricesDataUpdateCoordinator)
    coordinator.hass = MagicMock()
    coordinator._consecutive_failures = 0
    coordinator._first_failure_at = None
    coordinator._stale_data_issue_id = "stale_data_test_entry"
    return coordinator


def test_repair_is_not_raised_before_threshold() -> None:
    coordinator = _bare_coordinator()
    with patch("custom_components.fuel_prices_uk.ir") as mock_ir:
        for _ in range(CONSECUTIVE_FAILURE_THRESHOLD - 1):
            coordinator._record_failure_and_maybe_raise_repair()

        mock_ir.async_create_issue.assert_not_called()
    assert coordinator._consecutive_failures == CONSECUTIVE_FAILURE_THRESHOLD - 1


def test_repair_is_raised_once_threshold_reached() -> None:
    coordinator = _bare_coordinator()
    with patch("custom_components.fuel_prices_uk.ir") as mock_ir:
        for _ in range(CONSECUTIVE_FAILURE_THRESHOLD):
            coordinator._record_failure_and_maybe_raise_repair()

        mock_ir.async_create_issue.assert_called_once()
        _, kwargs = mock_ir.async_create_issue.call_args
        assert kwargs["translation_key"] == "stale_data"
        assert kwargs["is_fixable"] is False
        assert kwargs["translation_placeholders"]["failure_count"] == str(CONSECUTIVE_FAILURE_THRESHOLD)

        call_args = mock_ir.async_create_issue.call_args
        assert call_args[0][1] == DOMAIN
        assert call_args[0][2] == "stale_data_test_entry"


def test_repair_placeholders_stay_current_across_further_failures() -> None:
    coordinator = _bare_coordinator()
    with patch("custom_components.fuel_prices_uk.ir") as mock_ir:
        for _ in range(CONSECUTIVE_FAILURE_THRESHOLD + 2):
            coordinator._record_failure_and_maybe_raise_repair()

        # Re-created (not duplicated) on every failure past the threshold so
        # the displayed failure_count/since stay accurate for a long outage.
        assert mock_ir.async_create_issue.call_count == 3
        latest_kwargs = mock_ir.async_create_issue.call_args.kwargs
        assert latest_kwargs["translation_placeholders"]["failure_count"] == str(CONSECUTIVE_FAILURE_THRESHOLD + 2)


def test_successful_refresh_clears_repair_and_resets_counter() -> None:
    coordinator = _bare_coordinator()
    with patch("custom_components.fuel_prices_uk.ir") as mock_ir:
        for _ in range(CONSECUTIVE_FAILURE_THRESHOLD):
            coordinator._record_failure_and_maybe_raise_repair()

        coordinator._clear_stale_data_issue()

        mock_ir.async_delete_issue.assert_called_once_with(coordinator.hass, DOMAIN, "stale_data_test_entry")
    assert coordinator._consecutive_failures == 0
    assert coordinator._first_failure_at is None


def test_success_before_threshold_does_not_touch_issue_registry() -> None:
    """A single blip followed by a success shouldn't call delete_issue for an issue that was never created."""
    coordinator = _bare_coordinator()
    with patch("custom_components.fuel_prices_uk.ir") as mock_ir:
        coordinator._record_failure_and_maybe_raise_repair()
        coordinator._clear_stale_data_issue()

        mock_ir.async_create_issue.assert_not_called()
        mock_ir.async_delete_issue.assert_not_called()
    assert coordinator._consecutive_failures == 0
