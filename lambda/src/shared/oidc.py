"""OIDC-related data models"""

from dataclasses import dataclass
from typing import Optional

from dataclasses_json import DataClassJsonMixin


@dataclass
class OIDCTokenClaims(DataClassJsonMixin):
    """
    OIDC token claims extracted from validated token

    Attributes:
        sub: Subject (user identifier)
        iss: Issuer URL
        aud: Audience (client ID)
        exp: Expiry timestamp
        iat: Issued at timestamp
        email: User email (optional)
    """

    sub: str
    iss: str
    aud: str
    exp: int
    iat: int
    email: Optional[str] = None


@dataclass
class OIDCProviderConfig(DataClassJsonMixin):
    """
    OIDC provider configuration from .well-known/openid-configuration

    Attributes:
        issuer: Provider issuer URL
        jwks_uri: JSON Web Key Set endpoint URL
        authorization_endpoint: OAuth authorization endpoint
        token_endpoint: OAuth token endpoint
        userinfo_endpoint: User info endpoint
    """

    issuer: str
    jwks_uri: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str


@dataclass
class ErrorDetail(DataClassJsonMixin):
    """
    Error detail for Firefox Sync protocol error responses

    Attributes:
        location: Where the error occurred (header, body, query)
        name: Field name that caused the error
        description: Human-readable error description
    """

    location: str
    name: str
    description: str
