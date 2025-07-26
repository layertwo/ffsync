from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class ListCollectionsRoute(BaseRoute):
    def bind(self, api):
        @api.get("/storage")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """List all collections with their metadata"""
        # TODO: Implement authentication validation
        # TODO: Implement collection listing logic
        # TODO: Return proper CollectionDataList structure

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body='{"collections": [{"name": "bookmarks", "modified": 1642678800000, "count": 10, "usage": 2048}, {"name": "history", "modified": 1642678900000, "count": 25, "usage": 4096}]}',
        )
