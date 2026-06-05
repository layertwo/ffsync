from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.shared.base_route import BaseRoute
from src.shared.models import ConfigurationOutput

logger = Logger()

# Server configuration limits (per Mozilla Sync Storage API 1.5 spec)
MAX_REQUEST_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_POST_RECORDS = 100  # BSOs per batch
MAX_POST_BYTES = 2 * 1024 * 1024  # 2 MB total payload
MAX_RECORD_PAYLOAD_BYTES = 256 * 1024  # 256 KB per BSO
# Optional limits (None means unlimited)
MAX_TOTAL_RECORDS = None  # For batched uploads
MAX_TOTAL_BYTES = None  # For batched uploads (quota-based)


class ReadConfigurationRoute(BaseRoute):
    def __init__(
        self,
        max_request_bytes: int = MAX_REQUEST_BYTES,
        max_post_records: int = MAX_POST_RECORDS,
        max_post_bytes: int = MAX_POST_BYTES,
        max_record_payload_bytes: int = MAX_RECORD_PAYLOAD_BYTES,
        max_total_records: int | None = MAX_TOTAL_RECORDS,
        max_total_bytes: int | None = MAX_TOTAL_BYTES,
    ):
        self.max_request_bytes = max_request_bytes
        self.max_post_records = max_post_records
        self.max_post_bytes = max_post_bytes
        self.max_record_payload_bytes = max_record_payload_bytes
        self.max_total_records = max_total_records
        self.max_total_bytes = max_total_bytes

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/1.5/<uid>/info/configuration")
        def handle_request(uid: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """
        Get server configuration limits.

        Returns a JSON object with:
        - max_request_bytes: Maximum request body size in bytes
        - max_post_records: Maximum number of BSOs per POST request
        - max_post_bytes: Maximum combined payload size for POST requests in bytes
        - max_record_payload_bytes: Maximum individual BSO payload size in bytes
        - max_total_records: Maximum BSOs in a batched upload (optional)
        - max_total_bytes: Maximum combined payload size for batched uploads (optional)
        """
        try:
            result = ConfigurationOutput(
                max_request_bytes=self.max_request_bytes,
                max_post_records=self.max_post_records,
                max_post_bytes=self.max_post_bytes,
                max_record_payload_bytes=self.max_record_payload_bytes,
                max_total_records=self.max_total_records,
                max_total_bytes=self.max_total_bytes,
            )
            return Response(
                status_code=200,
                content_type="application/json",
                body=result.model_dump_json(exclude_none=True),
            )

        except Exception as e:  # pragma: nocover
            import json

            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
