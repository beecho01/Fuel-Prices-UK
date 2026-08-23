"""Mocked-API tests for FuelPricesAPI's refresh/pagination/fallback logic.

Uses aioresponses to stand in for the live Fuel Finder API so these run
without network access or real credentials. This is the highest-value test
file in the suite: it locks in the fix for GitHub issue #14 (incremental
refresh always falling back to an expensive full snapshot because a 404 on
batch 1 was treated as a hard failure instead of "no updates").
"""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from custom_components.fuel_prices_uk.api_client import (
    API_BASE_URL,
    PFS_INFO_ENDPOINT,
    PFS_PRICES_ENDPOINT,
    TOKEN_ENDPOINT,
    ApiHttpError,
    FuelPricesAPI,
)

PFS_INFO_PATTERN = re.compile(re.escape(f"{API_BASE_URL}{PFS_INFO_ENDPOINT}") + r"(\?.*)?$")
PFS_PRICES_PATTERN = re.compile(re.escape(f"{API_BASE_URL}{PFS_PRICES_ENDPOINT}") + r"(\?.*)?$")
TOKEN_URL = f"{API_BASE_URL}{TOKEN_ENDPOINT}"


def _station_info_row(node_id: str, name: str = "Test Station") -> dict:
    return {
        "node_id": node_id,
        "trading_name": name,
        "brand_name": "TestCo",
        "location": {"latitude": 51.5, "longitude": -0.12, "postcode": "SW1A 1AA"},
    }


def _price_row(node_id: str, price: float, fuel_type: str = "E10") -> dict:
    return {
        "node_id": node_id,
        "fuel_prices": [
            {
                "fuel_type": fuel_type,
                "price": price,
                "price_last_updated": "2026-01-01T00:00:00Z",
            }
        ],
    }


def _mock_token(m: aioresponses) -> None:
    m.post(TOKEN_URL, status=200, payload={"access_token": "test-token", "expires_in": 3600})


@pytest.fixture
def fast_client(monkeypatch):
    """Patch the inter-request pacing so tests run without real sleeps."""
    import custom_components.fuel_prices_uk.api_client as ac

    monkeypatch.setattr(ac, "MIN_REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(ac, "DEFAULT_429_BACKOFF_SECONDS", 0.01)

    async def _noop_pause() -> None:
        return None

    monkeypatch.setattr(ac.FuelPricesAPI, "_inter_fetch_pause", staticmethod(_noop_pause))
    return ac


async def _full_snapshot_refresh(api: FuelPricesAPI, m: aioresponses, *, station_price: float = 145.9) -> None:
    """Register a minimal successful full-snapshot pair and refresh."""
    _mock_token(m)
    m.get(
        PFS_INFO_PATTERN,
        status=200,
        payload={"total_batches": 1, "data": [_station_info_row("s1")]},
    )
    m.get(
        PFS_PRICES_PATTERN,
        status=200,
        payload={"total_batches": 1, "data": [_price_row("s1", station_price)]},
    )
    await api.get_all_stations(force_refresh=True)


class TestFullSnapshotAndPagination:
    async def test_full_snapshot_success(self, fast_client, aiohttp_client_session) -> None:
        api = FuelPricesAPI(session=aiohttp_client_session, client_id="c1", client_secret="s1")
        with aioresponses() as m:
            await _full_snapshot_refresh(api, m)

        stations = await api.get_all_stations()
        assert len(stations) == 1
        station = stations[0]
        assert station["site_id"] == "s1"
        assert station["latitude"] == 51.5
        assert station["prices"]["E10"]["price"] == pytest.approx(1.459)

    async def test_pagination_stops_via_total_batches_hint(self, fast_client, aiohttp_client_session) -> None:
        api = FuelPricesAPI(session=aiohttp_client_session, client_id="c2", client_secret="s2")
        with aioresponses() as m:
            _mock_token(m)
            m.get(
                PFS_INFO_PATTERN,
                status=200,
                payload={
                    "total_batches": 1,
                    "data": [_station_info_row("s1"), _station_info_row("s2")],
                },
            )
            # Two price batches (distinct stations per batch, so the
            # repeated-payload-signature guard doesn't fire), total_batches=2
            # tells the client to stop after batch 2.
            m.get(
                PFS_PRICES_PATTERN,
                status=200,
                payload={"total_batches": 2, "data": [_price_row("s1", 145.9)]},
            )
            m.get(
                PFS_PRICES_PATTERN,
                status=200,
                payload={"total_batches": 2, "data": [_price_row("s2", 132.9, fuel_type="B7")]},
            )
            await api.get_all_stations(force_refresh=True)

        stations = {s["site_id"]: s for s in await api.get_all_stations()}
        assert stations["s1"]["prices"]["E10"]["price"] == pytest.approx(1.459)
        assert stations["s2"]["prices"]["B7"]["price"] == pytest.approx(1.329)

    async def test_404_on_batch_greater_than_one_ends_pagination(self, fast_client, aiohttp_client_session) -> None:
        """Existing behaviour: a 404 on batch 2+ (no total_batches hint) means end-of-pages."""
        api = FuelPricesAPI(session=aiohttp_client_session, client_id="c3", client_secret="s3")
        with aioresponses() as m:
            _mock_token(m)
            m.get(
                PFS_INFO_PATTERN,
                status=200,
                payload={"data": [_station_info_row("s1")]},  # no total_batches hint
            )
            m.get(PFS_INFO_PATTERN, status=404, payload={"message": "not found"})  # batch 2
            m.get(
                PFS_PRICES_PATTERN,
                status=200,
                payload={"data": [_price_row("s1", 145.9)]},
            )
            m.get(PFS_PRICES_PATTERN, status=404, payload={"message": "not found"})  # batch 2

            stations = await api.get_all_stations(force_refresh=True)

        assert len(stations) == 1
        assert stations[0]["prices"]["E10"]["price"] == pytest.approx(1.459)


class TestIncrementalRefresh:
    """Regression coverage for GitHub issue #14.

    Confirmed against the live Fuel Finder API: an incremental request's
    404-on-batch-1 ("Requested batch 1 is not available") happens
    regardless of the effective-start-timestamp format and simply means
    "nothing changed in this window" - it must not abort the whole refresh.
    """

    async def test_incremental_404_on_batch_one_is_treated_as_no_updates(
        self, fast_client, aiohttp_client_session
    ) -> None:
        api = FuelPricesAPI(session=aiohttp_client_session, client_id="c4", client_secret="s4")
        with aioresponses() as m:
            await _full_snapshot_refresh(api, m, station_price=145.9)

        assert api._last_refresh is not None
        assert "s1" in api._station_index

        with aioresponses() as m:
            _mock_token(m)
            # Incremental station-info: 404 on batch 1 -> must be treated as empty.
            m.get(PFS_INFO_PATTERN, status=404, payload={"message": "Requested batch 1 is not available"})
            # Incremental prices: succeeds with a genuinely updated price.
            m.get(
                PFS_PRICES_PATTERN,
                status=200,
                payload={"total_batches": 1, "data": [_price_row("s1", 139.9)]},
            )

            await api._refresh()

            # The full-snapshot fallback endpoints (no effective-start-timestamp)
            # must NOT have been hit - the incremental path must have succeeded
            # on its own instead of aborting to a full snapshot.
            fallback_calls = [
                url for (method, url) in m.requests if method == "GET" and "effective-start-timestamp" not in str(url)
            ]
            assert fallback_calls == [], f"Unexpected full-snapshot fallback calls: {fallback_calls}"

        stations = await api.get_all_stations()
        assert stations[0]["prices"]["E10"]["price"] == pytest.approx(1.399)

    async def test_404_on_batch_one_without_effective_start_still_raises(
        self, fast_client, aiohttp_client_session
    ) -> None:
        """A 404 on batch 1 for a *full* snapshot request (no effective_start) is still a hard failure."""
        api = FuelPricesAPI(session=aiohttp_client_session, client_id="c5", client_secret="s5")
        with aioresponses() as m:
            _mock_token(m)
            m.get(PFS_INFO_PATTERN, status=404, payload={"message": "not found"})

            with pytest.raises(ApiHttpError):
                await api._fetch_station_info()

    async def test_incremental_fallback_to_full_snapshot_on_genuine_failure(
        self, fast_client, aiohttp_client_session
    ) -> None:
        api = FuelPricesAPI(session=aiohttp_client_session, client_id="c6", client_secret="s6")
        with aioresponses() as m:
            await _full_snapshot_refresh(api, m, station_price=145.9)

        with aioresponses() as m:
            _mock_token(m)
            # Incremental info succeeds with nothing new...
            m.get(PFS_INFO_PATTERN, status=404, payload={"message": "Requested batch 1 is not available"})
            # ...but incremental prices hits a genuine server error, not a 404.
            m.get(PFS_PRICES_PATTERN, status=500, payload={"message": "Internal Server Error"})

            # Fallback: full snapshot for both endpoints.
            m.get(
                PFS_INFO_PATTERN,
                status=200,
                payload={"total_batches": 1, "data": [_station_info_row("s1")]},
            )
            m.get(
                PFS_PRICES_PATTERN,
                status=200,
                payload={"total_batches": 1, "data": [_price_row("s1", 150.0)]},
            )

            await api._refresh()

        stations = await api.get_all_stations()
        assert stations[0]["prices"]["E10"]["price"] == pytest.approx(1.5)


class TestRateLimitAndAuth:
    async def test_429_is_retried_and_then_succeeds(self, fast_client, aiohttp_client_session) -> None:
        api = FuelPricesAPI(session=aiohttp_client_session, client_id="c7", client_secret="s7")
        with aioresponses() as m:
            _mock_token(m)
            m.get(PFS_INFO_PATTERN, status=429, headers={"Retry-After": "0"})
            m.get(
                PFS_INFO_PATTERN,
                status=200,
                payload={"total_batches": 1, "data": [_station_info_row("s1")]},
            )

            stations = await api._fetch_station_info()

        assert len(stations) == 1

    async def test_token_is_cached_across_instances_with_same_credentials(
        self, fast_client, aiohttp_client_session
    ) -> None:
        """Two config entries with the same credentials must share one token (issue #8)."""
        api_a = FuelPricesAPI(session=aiohttp_client_session, client_id="shared", client_secret="secret")
        api_b = FuelPricesAPI(session=aiohttp_client_session, client_id="shared", client_secret="secret")

        with aioresponses() as m:
            _mock_token(m)  # only ONE token response registered

            token_a = await api_a._get_access_token()
            token_b = await api_b._get_access_token()

            assert token_a == token_b == "test-token"
            token_calls = [url for (method, url) in m.requests if method == "POST"]
            assert len(token_calls) == 1
