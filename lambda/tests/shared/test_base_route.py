"""Tests for BaseRoute abstract class"""

import pytest

from src.shared.base_route import BaseRoute


class TestBaseRoute:
    """Tests for BaseRoute abstract class"""

    def test_cannot_instantiate_directly(self) -> None:
        """Test that BaseRoute cannot be instantiated directly"""
        with pytest.raises(TypeError) as exc_info:
            BaseRoute()  # type: ignore[abstract]

        assert "abstract" in str(exc_info.value).lower()
