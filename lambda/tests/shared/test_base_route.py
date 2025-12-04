"""Tests for BaseRoute abstract class"""

import pytest

from src.shared.base_route import BaseRoute


class TestBaseRoute:
    """Tests for BaseRoute abstract class"""

    def test_cannot_instantiate_directly(self):
        """Test that BaseRoute cannot be instantiated directly"""
        with pytest.raises(TypeError) as exc_info:
            BaseRoute()

        assert "abstract" in str(exc_info.value).lower()

    def test_must_implement_bind(self):
        """Test that subclasses must implement bind method"""

        class IncompleteRoute(BaseRoute):
            def handle(self, event):
                pass

        with pytest.raises(TypeError) as exc_info:
            IncompleteRoute()

        assert "abstract" in str(exc_info.value).lower()

    def test_must_implement_handle(self):
        """Test that subclasses must implement handle method"""

        class IncompleteRoute(BaseRoute):
            def bind(self, api):
                pass

        with pytest.raises(TypeError) as exc_info:
            IncompleteRoute()

        assert "abstract" in str(exc_info.value).lower()

    def test_can_instantiate_complete_subclass(self):
        """Test that subclass with both methods can be instantiated"""

        class CompleteRoute(BaseRoute):
            def bind(self, api):
                return "bound"

            def handle(self, event):
                return "handled"

        route = CompleteRoute()

        assert route.bind("api") == "bound"
        assert route.handle("event") == "handled"

    def test_subclass_can_have_additional_methods(self):
        """Test that subclass can have additional methods"""

        class ExtendedRoute(BaseRoute):
            def bind(self, api):
                pass

            def handle(self, event):
                return self.process(event)

            def process(self, event):
                return f"processed: {event}"

        route = ExtendedRoute()

        assert route.handle("test") == "processed: test"

    def test_subclass_can_have_constructor(self):
        """Test that subclass can have its own constructor"""

        class RouteWithConstructor(BaseRoute):
            def __init__(self, storage_manager):
                self.storage_manager = storage_manager

            def bind(self, api):
                pass

            def handle(self, event):
                return self.storage_manager

        mock_storage = "mock_storage"
        route = RouteWithConstructor(mock_storage)

        assert route.handle(None) == mock_storage

    def test_multiple_subclasses_independent(self):
        """Test that multiple subclasses are independent"""

        class Route1(BaseRoute):
            def bind(self, api):
                return "route1_bind"

            def handle(self, event):
                return "route1_handle"

        class Route2(BaseRoute):
            def bind(self, api):
                return "route2_bind"

            def handle(self, event):
                return "route2_handle"

        route1 = Route1()
        route2 = Route2()

        assert route1.bind(None) == "route1_bind"
        assert route2.bind(None) == "route2_bind"
        assert route1.handle(None) == "route1_handle"
        assert route2.handle(None) == "route2_handle"
