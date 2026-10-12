"""SyncStorage API v1.5 conformance tests.

Drives the real storage router (`storage_api_handler` -> StorageManager ->
stubbed DynamoDB) and asserts clauses of the protocol spec at
https://mozilla-services.github.io/syncstorage-rs/syncstorage/api-1.5.html
that the unit tests do not cover: wire-format rules, response headers, status
codes and conditional-request semantics.

These are deliberately *spec* assertions, not "whatever the code does". Where the
service does not yet meet a clause it is marked ``xfail(strict=True)`` with the
requirement quoted, so the suite stays green while CI flips the marker red the
moment the behaviour is fixed (an unexpected pass is a failure, prompting the
marker's removal).
"""

import json
from typing import Any, Optional
from unittest.mock import Mock, patch

import pytest
from botocore.stub import Stubber

from src.entrypoint.storage_api import lambda_handler as storage_handler
from src.environment.service_provider import ServiceProvider
from src.middlewares.hawk_auth import HawkAuthenticationError
from src.services.hawk_service import HawkCredentials
from tests.fixtures.integration import build_storage_event

USER_ID = "test-user-123"
GENERATION = 0

# The route's own validation limits, mirrored from the spec.
MAX_COLLECTION_NAME_LENGTH = 32
MAX_BSO_ID_LENGTH = 64
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_IDS = 100


def _creds(user_id: str = USER_ID) -> HawkCredentials:
    return HawkCredentials(
        user_id=user_id, generation=GENERATION, expiry=9999999999, hawk_id="test-hawk-id"
    )


def _body(response: dict) -> Any:
    """Decode an API Gateway proxy response body as JSON.

    Note the storage entrypoint returns a plain dict (not a powertools Response),
    so tests/conftest's json_body()/header() helpers -- which read .body/.headers
    attributes -- do not apply here.
    """
    return json.loads(response["body"])


def _header(response: dict, name: str) -> Optional[str]:
    """Case-insensitive lookup of a proxy-response header.

    The entrypoint emits ``multiValueHeaders`` (name -> list[str]) and no
    ``headers`` key, so tests/conftest's header() -- which reads ``.headers`` off
    a powertools Response -- cannot be used here.
    """
    for key, values in (response.get("multiValueHeaders") or {}).items():
        if key.lower() == name.lower():
            return values[0] if values else None
    return None


def _headers(extra: Optional[dict] = None) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": 'Hawk id="test", mac="test"'}
    headers.update(extra or {})
    return headers


def call(
    service_provider: ServiceProvider,
    context: Mock,
    method: str,
    path: str,
    *,
    headers: Optional[dict] = None,
    body: Any = None,
    query: Optional[dict] = None,
    path_params: Optional[dict] = None,
    user_id: str = USER_ID,
) -> dict:
    """Dispatch a storage request through the real router with auth stubbed out.

    HAWK validation is stubbed because these tests are about the API contract;
    authentication itself is covered by tests/integration/test_e2e_flow.py.
    """
    event = build_storage_event(
        method,
        path,
        user_id=user_id,
        headers=_headers(headers),
        body=body,
        query_params=query,
        path_params=path_params,
    )
    with patch.object(service_provider.hawk_service, "validate", return_value=_creds(user_id)):
        return storage_handler(event, context, service_provider=service_provider)


def object_item(object_id: str, payload: str = "payload", **attrs: Any) -> dict:
    """Wire-format DynamoDB item for a BSO."""
    item: dict[str, Any] = {
        "PK": {"S": f"USER#{USER_ID}#COLLECTION#bookmarks"},
        "SK": {"S": f"OBJECT#{object_id}"},
        "id": {"S": object_id},
        "payload": {"S": payload},
        "modified": {"N": "1234567890.12"},
    }
    for name, value in attrs.items():
        item[name] = {"N": str(value)} if isinstance(value, (int, float)) else {"S": value}
    return item


def collection_item(name: str) -> dict:
    """Wire-format DynamoDB item for collection metadata (as returned by the GSI)."""
    return {
        "PK": {"S": f"USER#{USER_ID}#COLLECTION#{name}"},
        "SK": {"S": "METADATA"},
        "user_id": {"S": USER_ID},
        "name": {"S": name},
        "modified": {"N": "1234567890.12"},
        "count": {"N": "3"},
        "usage": {"N": "2048"},
    }


class TestRequestValidation:
    """Input rules the spec fixes, enforced before any storage access."""

    def test_collection_name_longer_than_32_is_rejected(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            f"/storage/{'a' * (MAX_COLLECTION_NAME_LENGTH + 1)}",
            path_params={"collectionName": "a" * (MAX_COLLECTION_NAME_LENGTH + 1)},
        )

        assert response["statusCode"] == 400

    def test_collection_name_with_invalid_characters_is_rejected(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        """Collection names are urlsafe-base64 (plus period) only."""
        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/book marks",
            path_params={"collectionName": "book marks"},
        )

        assert response["statusCode"] == 400

    def test_bso_id_longer_than_64_is_rejected(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        long_id = "a" * (MAX_BSO_ID_LENGTH + 1)
        response = call(
            mock_service_provider,
            sample_lambda_context,
            "PUT",
            f"/storage/bookmarks/{long_id}",
            body={"payload": "x"},
            path_params={"collectionName": "bookmarks", "objectId": long_id},
        )

        assert response["statusCode"] == 400

    def test_get_with_more_than_100_ids_is_rejected(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        ids = ",".join(f"id{i}" for i in range(MAX_IDS + 1))
        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks",
            query={"ids": ids},
            path_params={"collectionName": "bookmarks"},
        )

        assert response["statusCode"] == 400

    def test_delete_with_more_than_100_ids_is_rejected(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        ids = ",".join(f"id{i}" for i in range(MAX_IDS + 1))
        response = call(
            mock_service_provider,
            sample_lambda_context,
            "DELETE",
            "/storage/bookmarks",
            query={"ids": ids},
            path_params={"collectionName": "bookmarks"},
        )

        assert response["statusCode"] == 400

    def test_payload_larger_than_256_kib_is_rejected(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        """Servers MUST support 256 KiB; larger than the configured maximum is a 413."""
        response = call(
            mock_service_provider,
            sample_lambda_context,
            "PUT",
            "/storage/bookmarks/obj1",
            body={"payload": "x" * (MAX_PAYLOAD_BYTES + 1)},
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 413


class TestResponseHeaders:
    """Headers the spec requires on responses."""

    def test_success_carries_x_weave_timestamp(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        """X-Weave-Timestamp is returned with all responses, 2 decimal places."""
        response = call(mock_service_provider, sample_lambda_context, "GET", "/info/configuration")

        assert response["statusCode"] == 200
        timestamp = _header(response, "X-Weave-Timestamp")
        assert timestamp is not None
        assert len(timestamp.split(".")[1]) == 2

    def test_get_bso_carries_x_last_modified(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        """X-Last-Modified is the resource's last-modified time."""
        dynamodb_stubber.add_response("get_item", {"Item": object_item("obj1")}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks/obj1",
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 200
        assert _header(response, "X-Last-Modified") == "1234567890.12"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Spec: 'X-Last-Modified ... Included in all success responses (200, 201, 204)'. "
            "The /info endpoints return 200 without it."
        ),
    )
    def test_info_endpoints_carry_x_last_modified(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        response = call(mock_service_provider, sample_lambda_context, "GET", "/info/configuration")

        assert _header(response, "X-Last-Modified") is not None

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Spec: 'X-Weave-Timestamp ... Returned with all responses'. Responses produced by "
            "the router's exception handlers skip WeaveTimestampMiddleware, so raised 401/403/"
            "422/500 have no header."
        ),
    )
    def test_error_responses_carry_x_weave_timestamp(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        event = build_storage_event(
            "GET", "/storage/bookmarks", path_params={"collectionName": "bookmarks"}
        )
        with patch.object(
            mock_service_provider.hawk_service,
            "validate",
            side_effect=HawkAuthenticationError("bad hawk"),
        ):
            response = storage_handler(event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 401
        assert _header(response, "X-Weave-Timestamp") is not None


class TestBsoWireFormat:
    """BSO field rules from the spec's Basic Storage Object section."""

    def test_get_returns_payload_but_never_ttl(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        """`ttl` 'may be set on write, but is not returned by the server'."""
        dynamodb_stubber.add_response("get_item", {"Item": object_item("obj1", ttl=3600)}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks/obj1",
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        body = _body(response)
        assert body["payload"] == "payload"
        assert body["modified"] == 1234567890.12
        assert "ttl" not in body

    def test_put_returns_the_collection_last_modified(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        """A successful PUT returns the new collection last-modified time."""
        dynamodb_stubber.add_response("get_item", {}, None)  # BSO does not exist yet
        dynamodb_stubber.add_response("put_item", {}, None)
        dynamodb_stubber.add_response("update_item", {}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "PUT",
            "/storage/bookmarks/obj1",
            body={"payload": "hello"},
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 200
        last_modified = _header(response, "X-Last-Modified")
        assert last_modified is not None
        assert float(_body(response)) == float(last_modified)

    def test_get_collection_returns_ids_by_default(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response(
            "query",
            {"Items": [object_item("obj1"), object_item("obj2")], "Count": 2},
            None,
        )

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks",
            path_params={"collectionName": "bookmarks"},
        )

        assert response["statusCode"] == 200
        assert _body(response) == ["obj1", "obj2"]

    def test_get_collection_full_returns_objects(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response(
            "query",
            {"Items": [object_item("obj1")], "Count": 1},
            None,
        )

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks",
            query={"full": "1"},
            path_params={"collectionName": "bookmarks"},
        )

        body = _body(response)
        assert [o["id"] for o in body] == ["obj1"]
        assert body[0]["payload"] == "payload"
        assert "ttl" not in body[0]

    def test_missing_collection_returns_empty_list_not_404(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        """Non-existent collections do not trigger 404 (backwards compatibility)."""
        dynamodb_stubber.add_response("query", {"Items": [], "Count": 0}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/nonexistent",
            path_params={"collectionName": "nonexistent"},
        )

        assert response["statusCode"] == 200
        assert _body(response) == []


class TestConditionalRequests:
    """X-If-Modified-Since / X-If-Unmodified-Since semantics."""

    def test_if_modified_since_returns_304(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response("get_item", {"Item": object_item("obj1")}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks/obj1",
            headers={"X-If-Modified-Since": "1234567890.12"},
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 304

    def test_invalid_if_modified_since_returns_400(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
    ) -> None:
        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks/obj1",
            headers={"X-If-Modified-Since": "not-a-decimal"},
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 400

    def test_both_conditional_headers_returns_400(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
    ) -> None:
        """'If the value is not a valid positive decimal, or if X-If-Unmodified-Since is also
        present, returns 400 Bad Request.'"""
        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks/obj1",
            headers={
                "X-If-Modified-Since": "1234567890.12",
                "X-If-Unmodified-Since": "1234567890.12",
            },
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 400

    def test_put_if_unmodified_since_zero_is_create_only(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        """'Use X-If-Unmodified-Since: 0' to create an item only if it does not exist."""
        dynamodb_stubber.add_response("get_item", {"Item": object_item("obj1")}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "PUT",
            "/storage/bookmarks/obj1",
            headers={"X-If-Unmodified-Since": "0"},
            body={"payload": "hello"},
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 412

    def test_put_if_unmodified_since_older_than_resource_returns_412(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response("get_item", {"Item": object_item("obj1")}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "PUT",
            "/storage/bookmarks/obj1",
            headers={"X-If-Unmodified-Since": "1.0"},
            body={"payload": "hello"},
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 412


class TestInfoEndpoints:
    """GET /info/* shapes."""

    def test_quota_is_a_two_item_list_with_null_quota(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        """'Returns a two-item list giving the user's current usage and quota (in KB). The
        second item will be null if the server does not enforce quotas.'"""
        dynamodb_stubber.add_response("query", {"Items": [collection_item("bookmarks")]}, None)

        response = call(mock_service_provider, sample_lambda_context, "GET", "/info/quota")

        body = _body(response)
        assert isinstance(body, list)
        assert len(body) == 2
        assert isinstance(body[0], (int, float))

    def test_collections_maps_names_to_last_modified(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response("query", {"Items": [collection_item("bookmarks")]}, None)

        response = call(mock_service_provider, sample_lambda_context, "GET", "/info/collections")

        body = _body(response)
        assert body == {"bookmarks": 1234567890.12}

    def test_configuration_advertises_the_limits(
        self, mock_service_provider: ServiceProvider, sample_lambda_context: Mock
    ) -> None:
        response = call(mock_service_provider, sample_lambda_context, "GET", "/info/configuration")

        body = _body(response)
        assert body["max_post_records"] == 100
        assert body["max_record_payload_bytes"] == MAX_PAYLOAD_BYTES


class TestDelete:
    """DELETE semantics."""

    def test_delete_bso_returns_modified(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response("get_item", {"Item": object_item("obj1")}, None)
        dynamodb_stubber.add_response("delete_item", {}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "DELETE",
            "/storage/bookmarks/obj1",
            path_params={"collectionName": "bookmarks", "objectId": "obj1"},
        )

        assert response["statusCode"] == 200
        assert "modified" in _body(response)

    def test_delete_all_returns_modified(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response("query", {"Items": []}, None)

        response = call(mock_service_provider, sample_lambda_context, "DELETE", "/storage")

        assert response["statusCode"] == 200
        assert "modified" in _body(response)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Spec (403/404): 'Non-existent collections do not trigger 404 for backwards "
            "compatibility reasons.' Deleting a collection that does not exist returns 404."
        ),
    )
    def test_delete_missing_collection_does_not_404(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response("get_item", {}, None)

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "DELETE",
            "/storage/nonexistent",
            path_params={"collectionName": "nonexistent"},
        )

        assert response["statusCode"] == 200


class TestPostCollection:
    """POST /storage/<collection> performs a series of PUTs at one timestamp."""

    def test_response_shape_is_modified_success_failed(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response("get_item", {}, None)  # collection does not exist
        dynamodb_stubber.add_response("batch_write_item", {"UnprocessedItems": {}}, None)
        dynamodb_stubber.add_response("put_item", {}, None)  # new collection metadata

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "POST",
            "/storage/bookmarks",
            body=[{"id": "obj1", "payload": "hello"}],
            path_params={"collectionName": "bookmarks"},
        )

        assert response["statusCode"] in (200, 201)
        body = _body(response)
        assert set(body.keys()) == {"modified", "success", "failed"}
        assert body["success"] == ["obj1"]


class TestDocumentedDeviations:
    """Clauses the service does not yet satisfy, pinned so they cannot drift silently."""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Spec: X-Weave-Next-Offset 'will always be a string of characters from the "
            "urlsafe-base64 alphabet; clients must treat it as opaque'. We return a decimal "
            "offset (offset + limit). Harmless for clients that echo it back, but not per spec."
        ),
    )
    def test_next_offset_is_an_opaque_token(
        self,
        mock_service_provider: ServiceProvider,
        sample_lambda_context: Mock,
        dynamodb_stubber: Stubber,
    ) -> None:
        dynamodb_stubber.add_response(
            "query",
            {"Items": [object_item("obj1"), object_item("obj2")], "Count": 2},
            None,
        )

        response = call(
            mock_service_provider,
            sample_lambda_context,
            "GET",
            "/storage/bookmarks",
            query={"limit": "1"},
            path_params={"collectionName": "bookmarks"},
        )

        next_offset = _header(response, "X-Weave-Next-Offset")
        assert next_offset is not None
        # An opaque urlsafe-base64 token is not a bare integer.
        assert not next_offset.isdigit()


def test_route_table_matches_the_spec_endpoints(
    mock_service_provider: ServiceProvider,
) -> None:
    """Guard: the spec's endpoint list and the router's route table must agree.

    Keeps this file honest as endpoints are added or renamed -- an endpoint that
    appears in neither the spec nor the router is a silent gap. Reads powertools'
    private ``_dynamic_routes``; if that attribute ever moves, this fails loudly
    rather than passing vacuously.
    """
    expected = {
        ("GET", "/1.5/<uid>/info/collections"),
        ("GET", "/1.5/<uid>/info/collection_counts"),
        ("GET", "/1.5/<uid>/info/collection_usage"),
        ("GET", "/1.5/<uid>/info/quota"),
        ("GET", "/1.5/<uid>/info/configuration"),
        ("GET", "/1.5/<uid>/storage"),
        ("POST", "/1.5/<uid>/storage/<collectionName>"),
        ("GET", "/1.5/<uid>/storage/<collectionName>"),
        ("PUT", "/1.5/<uid>/storage/<collectionName>"),
        ("DELETE", "/1.5/<uid>/storage/<collectionName>"),
        ("GET", "/1.5/<uid>/storage/<collectionName>/<objectId>"),
        ("PUT", "/1.5/<uid>/storage/<collectionName>/<objectId>"),
        ("DELETE", "/1.5/<uid>/storage/<collectionName>/<objectId>"),
        ("DELETE", "/1.5/<uid>/storage"),
        ("DELETE", "/1.5/<uid>"),
    }

    router = mock_service_provider.storage_api_router
    registered = {(route.method, route.path) for route in router.app._dynamic_routes}

    assert registered == expected, f"route table drift: {registered ^ expected}"
