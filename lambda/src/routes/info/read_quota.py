from aws_lambda_proxy import Response, StatusCode
from src.shared.base_route import BaseRoute


class ReadQuotaInfoRoute(BaseRoute):
    def bind(self, api):
        @api.get("/info/quota")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get storage quota information"""
        # TODO: Implement authentication validation
        # TODO: Implement quota information retrieval logic
        # TODO: Return proper quota structure with quota, usage, remaining

        return Response(
            status_code=StatusCode.OK,
            content_type="application/json",
            body='{"quota": 104857600, "usage": 7168, "remaining": 104850432}',
        )
