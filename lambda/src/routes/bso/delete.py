from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class DeleteBSORoute(BaseRoute):
    def bind(self, api):
        @api.delete("/storage/{collectionName}/{objectId}")
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Delete a specific storage object"""
        # TODO: Implement authentication validation
        # TODO: Validate collectionName against pattern ^[a-zA-Z0-9._-]+$ and length 1-32
        # TODO: Validate objectId against pattern ^[a-zA-Z0-9._-]+$ and length 1-64
        # TODO: Implement storage object deletion logic
        # TODO: Return proper timestamp in response

        collection_name = event["pathParameters"]["collectionName"]
        object_id = event["pathParameters"]["objectId"]

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body='{"modified": 1642678800000}',
        )
