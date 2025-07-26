from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class ReadCollectionRoute(BaseRoute):
    def bind(self, api):
        @api.get("/storage/{collectionName}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get collection metadata"""
        # TODO: Implement authentication validation
        # TODO: Validate collectionName against pattern ^[a-zA-Z0-9._-]+$ and length 1-32
        # TODO: Implement collection retrieval logic
        # TODO: Return proper X-Last-Modified header

        collection_name = event["pathParameters"]["collectionName"]

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body=f'{{"collection": {{"name": "{collection_name}", "modified": 1642678800000, "count": 10, "usage": 2048}}}}',
            headers={"X-Last-Modified": "1642678800000"},
        )
