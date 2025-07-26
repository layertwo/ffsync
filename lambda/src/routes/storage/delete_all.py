from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class DeleteAllStorageRoute(BaseRoute):
    def bind(self, api):
        @api.delete("/storage")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Delete all storage data for the authenticated user"""
        # TODO: Implement authentication validation
        # TODO: Implement storage deletion logic
        # TODO: Return proper timestamp in response

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body='{"modified": 1642678800000}',
        )
