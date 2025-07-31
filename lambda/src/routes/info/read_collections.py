from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class ReadCollectionsInfoRoute(BaseRoute):
    def bind(self, api):
        @api.get("/info/collections")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get metadata for all collections"""
        # TODO: Implement authentication validation
        # TODO: Implement collection metadata retrieval logic
        # TODO: Return proper CollectionDataMap structure

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body='{"collections": {"bookmarks": {"name": "bookmarks", "modified": 1642678800000, "count": 10, "usage": 2048}, "history": {"name": "history", "modified": 1642678900000, "count": 25, "usage": 4096}}}',
        )
