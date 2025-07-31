from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class CreateCollectionRoute(BaseRoute):
    def bind(self, api):
        @api.post("/storage/{collectionName}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Create a new collection"""
        # TODO: Implement authentication validation
        # TODO: Validate collectionName against pattern ^[a-zA-Z0-9._-]+$ and length 1-32
        # TODO: Implement collection creation logic
        # TODO: Handle batch object creation if objects provided
        # TODO: Return proper collection data and batch result

        collection_name = event["pathParameters"]["collectionName"]

        return Response(
            status_code=StatusCode.CREATED,
            content_type="application/json",
            body=f'{{"collection": {{"name": "{collection_name}", "modified": 1642678800000, "count": 0, "usage": 0}}, "batchResult": {{"success": [], "failed": {{}}, "modified": 1642678800000}}}}',
        )
