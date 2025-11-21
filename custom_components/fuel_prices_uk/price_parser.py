"""Utility helpers for normalising retailer price payloads."""
from __future__ import annotations

from typing import Any, Iterable, Optional

PRICE_KEYS_PRIMARY: tuple[str, ...] = (
    "price",
    "value",
    "amount",
    "amount_ppl",
    "amountPpl",
    "amountPencePerLitre",
    "amount_pence_per_litre",
    "cash_price",
    "cashPrice",
    "pence_per_litre",
    "ppl",
)


def _iter_candidates(entry: Any) -> Iterable[Any]:
    if isinstance(entry, dict):
        for key in PRICE_KEYS_PRIMARY:
            if key in entry:
                yield entry[key]
        for maybe_value in entry.values():
            yield maybe_value
    elif isinstance(entry, (list, tuple, set)):
        for item in entry:
            yield from _iter_candidates(item)
    else:
        yield entry


def coerce_price(value: Any) -> Optional[float]:
    """Return a GBP float regardless of whether the feed uses pence, strings, or nested dicts."""

    for candidate in _iter_candidates(value):
        if candidate in (None, ""):
            continue
        try:
            price = float(candidate)
        except (TypeError, ValueError):
            continue
        if price >= 50:
            divisor = 1000 if price >= 1000 else 100
            price = price / divisor
        return round(price, 3)
    return None
