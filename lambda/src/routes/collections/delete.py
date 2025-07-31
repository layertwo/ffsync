from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class DeleteCollectionRoute(BaseRoute):
    def bind(self, api):
        @api.delete("/storage/{collectionName}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Delete an entire collection"""
        # TODO: Implement authentication validation
        # TODO: Validate collectionName against pattern ^[a-zA-Z0-9._-]+$ and length 1-32
        # TODO: Implement collection deletion logic
        # TODO: Return proper timestamp in response

        collection_name = event["pathParameters"]["collectionName"]

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body='{"modified": 1642678800000}',
        )
