"""Shared pytest fixtures/setup for the Fuel Prices UK test suite."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform.startswith("win") and isinstance(
    asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy
):
    # aiodns (pulled in by aiohttp) requires SelectorEventLoop on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def _reset_api_client_module_globals():
    """Reset api_client.py's module-level shared state before every test.

    FuelPricesAPI intentionally shares a token cache, a request-rate lock,
    and a 429 cooldown across all instances (so multiple config entries
    don't thrash each other's OAuth tokens - see issue #8). That module-level
    state must not leak between tests. The lock objects are also recreated
    rather than just cleared, since pytest-asyncio gives each test function
    its own event loop by default and asyncio.Lock instances used by a
    previous test's (now-closed) loop cannot be safely reused here.
    """
    import custom_components.fuel_prices_uk.api_client as api_client_module

    api_client_module._global_429_cooldown_until = 0.0
    api_client_module._global_last_request_at = None
    api_client_module._global_token_cache = {}
    api_client_module._global_request_lock = asyncio.Lock()
    api_client_module._global_token_lock = asyncio.Lock()
    yield


@pytest.fixture
async def aiohttp_client_session():
    import aiohttp

    async with aiohttp.ClientSession() as session:
        yield session
