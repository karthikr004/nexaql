"""Engine test fixtures — override the root conftest's autouse fixture
since engine tests don't need the MCP server or auth setup."""

from __future__ import annotations

import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def reset_to_dev_mode():
    """No-op override: engine tests don't touch the MCP server."""
    yield
