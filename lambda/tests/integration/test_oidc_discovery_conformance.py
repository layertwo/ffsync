"""OpenID Connect Discovery 1.0 conformance for /.well-known/openid-configuration.

The OP metadata document MUST contain ``issuer``, ``authorization_endpoint``,
``token_endpoint``, ``jwks_uri``, ``response_types_supported``,
``subject_types_supported`` and ``id_token_signing_alg_values_supported``, and
every URL it advertises must be one the server actually serves. Firefox's
accounts client reads ``jwks_uri`` from here, so a URL that 404s silently breaks
token verification for every relying party.
"""

import json
from unittest.mock import MagicMock

from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.environment.service_provider import ServiceProvider
from src.routes.auth.oidc_discovery import OIDCDiscoveryRoute

ISSUER = "https://auth.prod.ffsync.example.com"

# OpenID Connect Discovery 1.0, section 3 -- REQUIRED metadata.
REQUIRED_METADATA = {
    "issuer",
    "authorization_endpoint",
    "token_endpoint",
    "jwks_uri",
    "response_types_supported",
    "subject_types_supported",
    "id_token_signing_alg_values_supported",
}

DISCOVERY_PATH = "/.well-known/openid-configuration"


def _metadata() -> dict:
    jwt_service = MagicMock()
    jwt_service.issuer = ISSUER
    response = OIDCDiscoveryRoute(jwt_service=jwt_service).handle(APIGatewayProxyEvent({}))
    assert response.status_code == 200
    assert response.body is not None
    return json.loads(response.body)


def _registered(provider: ServiceProvider) -> set[tuple[str, str]]:
    """(method, path) pairs the auth router actually serves.

    Powertools splits routes into `_static_routes` (literal paths, which is all of
    the auth API's) and `_dynamic_routes` (paths with parameters, e.g. the storage
    API's). Both have to be read or the guard silently passes against a subset.
    """
    app = provider.auth_api_router.app
    return {(route.method, route.path) for route in [*app._static_routes, *app._dynamic_routes]}


class TestOIDCDiscovery:
    def test_all_required_metadata_is_present(self) -> None:
        metadata = _metadata()

        missing = REQUIRED_METADATA - set(metadata)
        assert not missing, f"missing REQUIRED OIDC metadata: {missing}"

    def test_issuer_identifies_this_authorization_server(self) -> None:
        assert _metadata()["issuer"] == ISSUER

    def test_jwks_uri_points_at_a_route_that_is_served(
        self, mock_service_provider: ServiceProvider
    ) -> None:
        jwks_uri = _metadata()["jwks_uri"]

        assert jwks_uri == f"{ISSUER}/v1/jwks"
        assert ("GET", "/v1/jwks") in _registered(mock_service_provider)

    def test_advertised_endpoints_are_served(self, mock_service_provider: ServiceProvider) -> None:
        metadata = _metadata()
        registered = _registered(mock_service_provider)

        assert ("POST", "/v1/oauth/authorization") in registered
        assert metadata["authorization_endpoint"].endswith("/v1/oauth/authorization")
        assert ("POST", "/v1/oauth/token") in registered
        assert metadata["token_endpoint"].endswith("/v1/oauth/token")

    def test_discovery_is_served_at_the_path_clients_request(
        self, mock_service_provider: ServiceProvider
    ) -> None:
        """Firefox requests /.well-known/openid-configuration under the issuer."""
        assert ("GET", DISCOVERY_PATH) in _registered(mock_service_provider)

    def test_signing_algorithm_matches_what_the_jwks_publishes(self) -> None:
        """The advertised alg must be one the issued JWTs actually use (RS256)."""
        assert _metadata()["id_token_signing_alg_values_supported"] == ["RS256"]
