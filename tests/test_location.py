"""Tests for the pure-logic helpers in custom_components.fuel_prices_uk.location.

is_coordinates and rank_local_type do not perform network I/O, unlike
get_lat_lon/is_postcode/is_location/fetch_postcode_data which call the
postcodes.io API and are exercised via the manual scripts/check_*.py
scripts instead.
"""

from __future__ import annotations

import pytest

from custom_components.fuel_prices_uk.location import is_coordinates, rank_local_type


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("51.5074,-0.1278", (51.5074, -0.1278)),
        ("51.5074, -0.1278", (51.5074, -0.1278)),  # whitespace after comma tolerated
        ("not,coords", (None, None)),  # non-numeric
        ("200,-0.1278", (None, None)),  # latitude out of range
        ("51.5074", (None, None)),  # missing longitude
        ("", (None, None)),
        ("SW1A 1AA", (None, None)),  # postcode, not raw coordinates
    ],
)
def test_is_coordinates(query, expected) -> None:
    assert is_coordinates(query) == expected


@pytest.mark.parametrize(
    ("local_type", "expected_rank"),
    [
        ("City", 1),
        ("Town", 2),
        ("Village", 3),
        ("Suburban Area", 4),
        ("Hamlet", 5),
        ("Other Settlement", 6),
        ("Unknown Type", 999),
        (None, 999),
    ],
)
def test_rank_local_type(local_type, expected_rank) -> None:
    assert rank_local_type(local_type) == expected_rank


def test_rank_local_type_orders_cities_before_villages() -> None:
    assert rank_local_type("City") < rank_local_type("Village") < rank_local_type("Hamlet")
