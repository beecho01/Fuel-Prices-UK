"""Tests for custom_components.fuel_prices_uk.price_parser.coerce_price."""

from __future__ import annotations

import pytest

from custom_components.fuel_prices_uk.price_parser import coerce_price


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Already in pounds (below the pence threshold) - passed through as-is.
        (1.459, 1.459),
        ("1.459", 1.459),
        (0, 0.0),
        # Pence values (>= 50) are converted down to pounds.
        (145.9, 1.459),
        ("145.9", 1.459),
        (49.9, 49.9),  # just under the pence threshold - not converted
        (50.0, 0.5),  # boundary: 50 is treated as pence
        # Large/garbled values are assumed to be in thousandths-of-a-penny
        # style feeds and divided by 1000 instead of 100.
        (1459.0, 1.459),
        # Nested containers are unwrapped to find a usable numeric value.
        ({"price": 145.9}, 1.459),
        ({"value": "132.9"}, 1.329),
        ({"amount_ppl": 141.9}, 1.419),
        ([{"price": 159.9}], 1.599),
    ],
)
def test_coerce_price_valid(value, expected) -> None:
    assert coerce_price(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not-a-number",
        {},
        [],
        {"unrelated_key": "no price here"},
        [None, "", {}],
        # Only nested *lists* are recursed into; a dict nested inside a
        # dict's values is not unwrapped further, so this is unparseable.
        {"nested": {"price": 123.4}},
    ],
)
def test_coerce_price_unparseable_returns_none(value) -> None:
    assert coerce_price(value) is None
