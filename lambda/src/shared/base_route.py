from abc import ABC, abstractmethod


class BaseRoute(ABC):
    """Base class for all route handlers"""

    @abstractmethod
    def bind(self, api):
        """Bind this route to the API with appropriate decorators"""
        pass

    @abstractmethod
    def handle(self, event, context):
        pass
