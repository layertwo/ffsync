import json
from datetime import datetime, timezone

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CODE_SERVER_LIMIT_EXCEEDED,
    ConflictException,
    PreconditionFailedException,
    ServerLimitExceededException,
    ValidationException,
)
from src.shared.models import (
    BasicStorageObject,
    BatchResultOutput,
    ValidationError,
    validate_collection_name,
)

logger = Logger()


class CreateCollectionRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/1.5/<uid>/storage/<collectionName>")
        def handle_request(uid: str, collectionName: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Create a new collection or batch create/update objects"""
        try:
            # Extract user_id from authorizer context
            user_id = event.get("requestContext", {}).get("hawk_uid")
            if not user_id:
                return Response(
                    status_code=401,
                    content_type="application/json",
                    body=json.dumps({"error": "Unauthorized"}),
                )

            path_params = event.path_parameters or {}
            headers = event.headers or {}
            body = event.body
            collection_name = path_params["collectionName"]

            # Validate collection name before any storage call
            try:
                validate_collection_name(collection_name)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Validate X-Weave-Records header if present (Requirement 3.7)
            x_weave_records = headers.get("x-weave-records")
            if x_weave_records:
                try:
                    expected_records = int(x_weave_records)
                    if expected_records > 100:  # MAX_POST_RECORDS
                        raise ServerLimitExceededException(
                            f"X-Weave-Records header indicates {expected_records} records, maximum is 100"
                        )
                except ValueError:
                    raise ValidationException("X-Weave-Records header must be an integer")

            # Validate X-Weave-Bytes header if present (Requirement 3.8)
            x_weave_bytes = headers.get("x-weave-bytes")
            if x_weave_bytes:
                try:
                    expected_bytes = int(x_weave_bytes)
                    if expected_bytes > 2 * 1024 * 1024:  # MAX_POST_BYTES (2 MB)
                        raise ServerLimitExceededException(
                            f"X-Weave-Bytes header indicates {expected_bytes} bytes, maximum is {2 * 1024 * 1024}"
                        )
                except ValueError:
                    raise ValidationException("X-Weave-Bytes header must be an integer")

            # Check conditional headers
            if_unmodified_since = headers.get("x-if-unmodified-since")
            if if_unmodified_since and not self._check_precondition(
                user_id, collection_name, if_unmodified_since
            ):
                return Response(
                    status_code=412,
                    content_type="application/json",
                    body=json.dumps({"error": "Precondition failed"}),
                )

            # Parse objects from request body - support application/json only
            # API Gateway will reject unsupported Content-Types
            objects = []
            if body:
                try:
                    body_data = json.loads(body)

                    # Handle direct array of objects (Mozilla API format)
                    if isinstance(body_data, list):
                        objects_data = body_data
                    # Handle wrapped objects
                    elif "objects" in body_data:
                        objects_data = body_data["objects"]
                    else:  # pragma: nocover
                        objects_data = []

                    objects = [
                        BasicStorageObject(
                            id=obj["id"],
                            payload=obj["payload"],
                            sortindex=obj.get("sortindex"),
                            ttl=obj.get("ttl"),
                            modified=datetime.fromtimestamp(
                                0, tz=timezone.utc
                            ),  # Will be set by storage manager
                        )
                        for obj in objects_data
                    ]
                except (json.JSONDecodeError, KeyError) as e:
                    raise ValidationException(f"Invalid request body: {e}")

            # Validate actual record count matches X-Weave-Records if provided
            if x_weave_records:
                actual_records = len(objects)
                if actual_records != expected_records:
                    raise ValidationException(
                        f"X-Weave-Records header indicates {expected_records} records, but body contains {actual_records}"
                    )

            # Create/update collection using storage manager
            collection_data, batch_result = self.storage_manager.create_or_update_collection(
                user_id, collection_name, objects if objects else None
            )

            # Return Mozilla-compliant response format (Requirement 3.2)
            modified_ts = collection_data.modified.timestamp()
            result = BatchResultOutput(
                modified=modified_ts,
                success=batch_result.success,
                failed=batch_result.failed,
            )

            return Response(
                status_code=201,  # 201 Created for new collection
                content_type="application/json",
                body=result.model_dump_json(),
                headers={"X-Last-Modified": str(round(modified_ts, 2))},
            )

        except ServerLimitExceededException:
            # Return 400 with Mozilla response code 17 (Requirement 3.4, 3.5)
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps(CODE_SERVER_LIMIT_EXCEEDED),
            )
        except ValidationException as e:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except ConflictException as e:
            return Response(
                status_code=409,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except PreconditionFailedException as e:  # pragma: nocover
            return Response(
                status_code=412,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )

    def _check_precondition(self, user_id, collection_name, if_unmodified_since):
        """Check if collection was modified since given timestamp"""
        try:
            timestamp = float(if_unmodified_since)
            collection = self.storage_manager.get_collection(user_id, collection_name)
            return collection.modified <= datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except ValueError, Exception:  # pragma: nocover
            return True  # If we can't check, allow the operation
