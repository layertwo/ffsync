"""Unit tests for the weave response headers.

The storage API's two header rules come from Mozilla's two wrappers: a
transaction wrapper ensures X-Last-Modified unless the handler set one, and the
weave middleware then reports X-Weave-Timestamp as the later of that and the
clock.
"""

from typing import Any, Optional

import pytest
from aws_lambda_powertools.event_handler import Response

from src.middlewares.weave_timestamp import apply_weave_headers
from tests.conftest import header


def _response(headers: Optional[dict[str, Any]] = None) -> Response[Any]:
    return Response(
        status_code=200, content_type="application/json", body="{}", headers=headers or None
    )


class TestLastModified:
    def test_storage_responses_get_one_from_the_clock(self) -> None:
        response = apply_weave_headers(_response(), ensure_last_modified=True)

        # Nothing to report, so the resource timestamp is "now" and the weave
        # timestamp cannot be later than it.
        assert header(response, "X-Last-Modified") == header(response, "X-Weave-Timestamp")

    def test_a_handler_set_value_is_preserved(self) -> None:
        response = apply_weave_headers(
            _response({"X-Last-Modified": "1234567890.12"}), ensure_last_modified=True
        )

        assert header(response, "X-Last-Modified") == "1234567890.12"

    def test_apis_without_a_resource_timestamp_do_not_get_one(self) -> None:
        response = apply_weave_headers(_response())

        assert "X-Last-Modified" not in response.headers


class TestWeaveTimestamp:
    def test_is_never_behind_the_resource_timestamp(self) -> None:
        response = apply_weave_headers(_response({"X-Last-Modified": "1234567890.12"}))

        assert float(header(response, "X-Weave-Timestamp")) > 1234567890.12

    def test_a_future_resource_timestamp_wins(self) -> None:
        future = "9999999999.00"

        response = apply_weave_headers(_response({"X-Last-Modified": future}))

        assert header(response, "X-Weave-Timestamp") == future

    def test_is_formatted_to_two_decimal_places(self) -> None:
        response = apply_weave_headers(_response())

        assert len(header(response, "X-Weave-Timestamp").split(".")[1]) == 2

    @pytest.mark.parametrize("value", ["not-a-number", ""])
    def test_malformed_resource_timestamp_falls_back_to_the_clock(self, value: str) -> None:
        """A handler's bad value must not turn an error response into a 502."""
        response = apply_weave_headers(_response({"X-Last-Modified": value}))

        assert float(header(response, "X-Weave-Timestamp")) > 0

    @pytest.mark.parametrize("value", [["1234567890.12"], []])
    def test_list_valued_resource_timestamp(self, value: list[str]) -> None:
        """powertools types Response.headers as str | list[str]."""
        response = apply_weave_headers(
            _response({"X-Last-Modified": value}), ensure_last_modified=True
        )

        assert header(response, "X-Last-Modified")
