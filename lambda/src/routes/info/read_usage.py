from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class ReadCollectionUsageRoute(BaseRoute):
    def bind(self, api):
        @api.get("/info/collection_usage")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get storage usage for all collections"""
        # TODO: Implement authentication validation
        # TODO: Implement collection usage retrieval logic
        # TODO: Return proper CollectionUsage map structure

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body='{"usage": {"bookmarks": 2048, "history": 4096, "tabs": 1024}}',
        )
