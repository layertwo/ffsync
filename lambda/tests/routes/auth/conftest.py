"""Shared route-test doubles for the FxA auth routes.

Deliberately bare MagicMocks: a test that needs configured behaviour should configure it
locally, so that adding setup here can never silently change what another test receives.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_account_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_token_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def device_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_oauth_code_manager() -> MagicMock:
    return MagicMock()
