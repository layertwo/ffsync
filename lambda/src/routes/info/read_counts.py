from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class ReadCollectionCountsRoute(BaseRoute):
    def bind(self, api):
        @api.get("/info/collection_counts")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get object counts for all collections"""
        # TODO: Implement authentication validation
        # TODO: Implement collection counts retrieval logic
        # TODO: Return proper CollectionCounts map structure

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body='{"counts": {"bookmarks": 10, "history": 25, "tabs": 5}}',
        )
