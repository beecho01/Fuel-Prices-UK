"""Tests for the pure payload-shaping helpers in api_client.py.

These cover the response-parsing logic that sits between the raw Fuel
Finder API JSON and the station/price records the coordinator consumes -
the area most exposed to upstream payload-shape drift.
"""

from __future__ import annotations

import pytest

from custom_components.fuel_prices_uk.api_client import (
    PFS_INFO_ENDPOINT,
    _build_batch_signature,
    _distance_km,
    _extract_fuel_entries_from_row,
    _extract_price,
    _extract_records_from_payload,
    _extract_station_identifier,
    _extract_total_batches_hint,
    _latest_iso,
    _normalise_source_fuel_type_key,
    _parse_datetime,
)


def test_distance_km_same_point_is_zero() -> None:
    assert _distance_km(51.5074, -0.1278, 51.5074, -0.1278) == 0.0


def test_distance_km_known_separation() -> None:
    # London -> roughly Newbury direction; just needs to be a sane positive distance.
    km = _distance_km(51.5074, -0.1278, 51.4545, -0.9781)
    assert km == pytest.approx(59.176, abs=0.5)


@pytest.mark.parametrize(
    ("prices", "fuel_type", "expected"),
    [
        ({"E10": {"price": 145.9}}, "E10", 1.459),  # pence -> pounds conversion
        ({"E10": {"price": 1.459}}, "E10", 1.459),  # already in pounds
        ({"E10": 145.9}, "E10", 1.459),  # flat value, not wrapped in a dict
        ({}, "E10", None),
        ({"E10": {"price": None}}, "E10", None),
    ],
)
def test_extract_price(prices, fuel_type, expected) -> None:
    result = _extract_price(prices, fuel_type)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("E10", "E10"),
        ("e10", "E10"),
        ("B7_Standard", "B7_STANDARD"),
        ("B7-STANDARD", "B7_STANDARD"),
        ("B7_PREMIUM", "B7_PREMIUM"),
        ("DIESEL", "B7"),  # aliased
        ("PREMIUM_DIESEL", "B7_PREMIUM"),  # aliased
        ("UNLEADED", "E10"),  # aliased
        ("PREMIUM_UNLEADED", "E5"),  # aliased
        ("HVO", None),  # not in FUEL_TYPE_MAP - unsupported fuel type
        ("B10", None),  # not in FUEL_TYPE_MAP - unsupported fuel type
        ("unknown", None),
    ],
)
def test_normalise_source_fuel_type_key(raw, expected) -> None:
    assert _normalise_source_fuel_type_key(raw) == expected


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"node_id": "abc"}, "abc"),
        ({"site_id": "xyz"}, "xyz"),
        ({"id": 123}, "123"),
        ({}, ""),
    ],
)
def test_extract_station_identifier(row, expected) -> None:
    assert _extract_station_identifier(row) == expected


def test_build_batch_signature_reflects_batch_contents() -> None:
    assert _build_batch_signature([{"node_id": "a"}, {"node_id": "b"}]) == (2, "a", "b")


def test_build_batch_signature_empty_batch() -> None:
    assert _build_batch_signature([]) == (0, "[]", "[]")


def test_extract_records_from_payload_direct_list() -> None:
    payload = [{"node_id": "1", "trading_name": "x"}]
    assert _extract_records_from_payload(payload, PFS_INFO_ENDPOINT) == payload


def test_extract_records_from_payload_wrapped_in_data_key() -> None:
    payload = {"data": [{"node_id": "1", "location": {}, "trading_name": "x", "brand_name": "y"}]}
    assert _extract_records_from_payload(payload, PFS_INFO_ENDPOINT) == payload["data"]


def test_extract_records_from_payload_no_list_present() -> None:
    assert _extract_records_from_payload({"foo": "bar"}, PFS_INFO_ENDPOINT) is None


def test_extract_records_from_payload_empty_top_level_list_is_none() -> None:
    # An empty list has no dict rows to collect, so this is treated the same
    # as "no records found" rather than "zero records" - callers rely on
    # this to distinguish an unexpected shape (None) from a genuinely empty
    # batch (see _fetch_batched_resource's batch_number == 1 handling).
    assert _extract_records_from_payload([], PFS_INFO_ENDPOINT) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-02-17T16:00:00.000Z", "2026-02-17T16:00:00+00:00"),
        ("2026-02-17T16:00:00Z", "2026-02-17T16:00:00+00:00"),
        ("17/02/2026 16:00:00", "2026-02-17T16:00:00+00:00"),
        (None, None),
        ("garbage", None),
    ],
)
def test_parse_datetime(value, expected) -> None:
    assert _parse_datetime(value) == expected


def test_latest_iso_prefers_more_recent_candidate() -> None:
    assert _latest_iso(None, "2026-02-17T16:00:00+00:00") == "2026-02-17T16:00:00+00:00"
    assert _latest_iso("2026-02-17T16:00:00+00:00", "2026-02-18T16:00:00+00:00") == "2026-02-18T16:00:00+00:00"
    assert _latest_iso("2026-02-18T16:00:00+00:00", "2026-02-17T16:00:00+00:00") == "2026-02-18T16:00:00+00:00"


def test_extract_fuel_entries_from_row_reads_fuel_prices_array() -> None:
    row = {
        "fuel_prices": [
            {"fuel_type": "E10", "price": 132.9},
            {"fuel_type": "B7_STANDARD", "price": 141.9},
        ]
    }
    entries = _extract_fuel_entries_from_row(row)
    assert {"fuel_type": "E10", "price": 132.9} in entries
    assert {"fuel_type": "B7_STANDARD", "price": 141.9} in entries


def test_extract_total_batches_hint_top_level_key() -> None:
    assert _extract_total_batches_hint({"total_batches": 3}) == 3


def test_extract_total_batches_hint_nested_pagination_key() -> None:
    assert _extract_total_batches_hint({"pagination": {"total_pages": 5}}) == 5


def test_extract_total_batches_hint_missing() -> None:
    assert _extract_total_batches_hint({}) is None
