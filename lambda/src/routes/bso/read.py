from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class ReadBSORoute(BaseRoute):
    def bind(self, api):
        @api.get("/storage/{collectionName}/{objectId}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get a specific storage object"""
        # TODO: Implement authentication validation
        # TODO: Validate collectionName against pattern ^[a-zA-Z0-9._-]+$ and length 1-32
        # TODO: Validate objectId against pattern ^[a-zA-Z0-9._-]+$ and length 1-64
        # TODO: Implement storage object retrieval logic
        # TODO: Return proper X-Last-Modified header

        collection_name = event["pathParameters"]["collectionName"]
        object_id = event["pathParameters"]["objectId"]

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body=f'{{"object": {{"id": "{object_id}", "payload": "{{\\"title\\": \\"Example Object\\", \\"url\\": \\"https://example.com\\"}}", "modified": 1642678800000, "sortindex": 100}}}}',
            headers={"X-Last-Modified": "1642678800000"},
        )
