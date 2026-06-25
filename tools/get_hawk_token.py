#!/usr/bin/env python3
"""
Script to get HAWK credentials from Firefox Sync Token Server.

Flow:
1. Discovers OIDC endpoints from .well-known/openid-configuration
2. Opens browser for OAuth login (Authorization Code flow with PKCE)
3. Exchanges authorization code for OIDC access token
4. Exchanges OIDC token for HAWK credentials via Token Server

Usage:
    python tools/get_hawk_token.py --issuer https://auth.example.com/application/o/myapp/ \
        --client-id my-client-id --token-server-url https://sync.example.com
"""

import base64
import hashlib
import http.server
import json
import secrets
import urllib.parse
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone

import click
import requests


@dataclass
class OIDCConfig:
    """OIDC provider configuration from discovery endpoint."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str


@dataclass
class TokenResponse:
    """OIDC token response"""

    access_token: str
    token_type: str
    expires_in: int
    id_token: str | None = None
    refresh_token: str | None = None


@dataclass
class HawkCredentials:
    """HAWK credentials from Token Server"""

    id: str
    key: str
    api_endpoint: str
    uid: str
    duration: int
    hashalg: str


def discover_oidc_config(issuer: str) -> OIDCConfig:
    """Fetch OIDC configuration from .well-known endpoint."""
    well_known_url = f"{issuer}/.well-known/openid-configuration"

    response = requests.get(well_known_url, timeout=10)
    response.raise_for_status()

    data = response.json()
    return OIDCConfig(
        issuer=data["issuer"],
        authorization_endpoint=data["authorization_endpoint"],
        token_endpoint=data["token_endpoint"],
    )


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scopes: str,
    state: str,
    code_challenge: str,
) -> str:
    """Build authorization URL."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorization_endpoint}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(
    token_endpoint: str,
    client_id: str,
    client_secret: str | None,
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> TokenResponse:
    """Exchange authorization code for tokens."""
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    if client_secret:
        data["client_secret"] = client_secret

    response = requests.post(token_endpoint, data=data, timeout=30)
    response.raise_for_status()

    token_data = response.json()
    return TokenResponse(
        access_token=token_data["access_token"],
        token_type=token_data["token_type"],
        expires_in=token_data["expires_in"],
        id_token=token_data.get("id_token"),
        refresh_token=token_data.get("refresh_token"),
    )


def exchange_for_hawk_credentials(token_server_url: str, access_token: str) -> HawkCredentials:
    """Exchange OIDC token for HAWK credentials."""
    url = f"{token_server_url}/1.0/sync/1.5"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    return HawkCredentials(
        id=data["id"],
        key=data["key"],
        api_endpoint=data["api_endpoint"],
        uid=data["uid"],
        duration=data["duration"],
        hashalg=data["hashalg"],
    )


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    auth_code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self):
        """Handle OAuth callback GET request."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return

        params = urllib.parse.parse_qs(parsed.query)

        if "error" in params:
            CallbackHandler.error = params["error"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication failed</h1><p>You can close this window.</p>")
            return

        CallbackHandler.auth_code = params.get("code", [None])[0]
        CallbackHandler.state = params.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this window.</p>")

    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass


def wait_for_callback(expected_state: str, port: int) -> str:
    """Start local server and wait for OAuth callback."""
    server = http.server.HTTPServer(("localhost", port), CallbackHandler)
    server.timeout = 120

    CallbackHandler.auth_code = None
    CallbackHandler.state = None
    CallbackHandler.error = None

    while CallbackHandler.auth_code is None and CallbackHandler.error is None:
        server.handle_request()

    server.server_close()

    if CallbackHandler.error:
        raise Exception(f"OAuth error: {CallbackHandler.error}")

    if CallbackHandler.state != expected_state:
        raise Exception("State mismatch - possible CSRF attack")

    return CallbackHandler.auth_code


@click.command()
@click.option(
    "--issuer",
    required=True,
    help="OIDC issuer URL (has .well-known/openid-configuration)",
)
@click.option("--client-id", required=True, help="OAuth client ID")
@click.option(
    "--client-secret",
    default=None,
    help="OAuth client secret (for confidential clients)",
)
@click.option("--token-server-url", required=True, help="Firefox Sync Token Server URL")
@click.option("--scopes", default="openid profile email", help="Space-separated OAuth scopes")
@click.option("--port", default=8765, help="Local callback server port")
@click.option("--redirect-uri", default=None, help="Override redirect URI")
@click.option("--json-only", is_flag=True, help="Output only JSON")
@click.option("--debug", is_flag=True, help="Print debug info")
def main(
    issuer: str,
    client_id: str,
    client_secret: str | None,
    token_server_url: str,
    scopes: str,
    port: int,
    redirect_uri: str | None,
    json_only: bool,
    debug: bool,
):
    """Get HAWK credentials from Firefox Sync Token Server via OIDC."""
    issuer = issuer.rstrip("/")
    token_server_url = token_server_url.rstrip("/")

    if redirect_uri is None:
        redirect_uri = f"http://localhost:{port}/callback"

    # Discover OIDC endpoints
    if not json_only:
        click.echo("Discovering OIDC configuration...")

    try:
        oidc_config = discover_oidc_config(issuer)
    except requests.HTTPError as e:
        raise click.ClickException(f"Failed to discover OIDC config: {e}")

    if not json_only:
        click.echo("Firefox Sync Token Exchange")
        click.echo("=" * 40)
        click.echo(f"Issuer: {oidc_config.issuer}")
        click.echo(f"Auth endpoint: {oidc_config.authorization_endpoint}")
        click.echo(f"Token endpoint: {oidc_config.token_endpoint}")
        click.echo(f"Token Server: {token_server_url}")
        click.echo()

    # Generate PKCE and state
    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = generate_pkce_pair()

    # Build auth URL
    auth_url = build_auth_url(
        oidc_config.authorization_endpoint,
        client_id,
        redirect_uri,
        scopes,
        state,
        code_challenge,
    )

    if debug:
        click.echo(f"Redirect URI: {redirect_uri}")
        click.echo(f"Auth URL: {auth_url}")
        click.echo()

    if not json_only:
        click.echo("Opening browser for authentication...")
    webbrowser.open(auth_url)

    # Wait for callback
    try:
        auth_code = wait_for_callback(state, port)
    except Exception as e:
        raise click.ClickException(str(e))

    if not json_only:
        click.echo("\nReceived authorization code, exchanging for tokens...")

    # Exchange code for OIDC token
    try:
        tokens = exchange_code_for_token(
            oidc_config.token_endpoint,
            client_id,
            client_secret,
            redirect_uri,
            auth_code,
            code_verifier,
        )
        if not json_only:
            click.echo(f"Got OIDC access token (expires in {tokens.expires_in}s)")
    except requests.HTTPError as e:
        msg = f"Failed to get OIDC token: {e}"
        if e.response is not None:
            msg += f"\nResponse: {e.response.text}"
        raise click.ClickException(msg)

    # Exchange for HAWK credentials
    if not json_only:
        click.echo("\nExchanging OIDC token for HAWK credentials...")
    try:
        hawk = exchange_for_hawk_credentials(token_server_url, tokens.access_token)
    except requests.HTTPError as e:
        msg = f"Failed to get HAWK credentials: {e}"
        if e.response is not None:
            msg += f"\nResponse: {e.response.text}"
        raise click.ClickException(msg)

    # Decode HAWK ID to extract expiry timestamp
    try:
        # Add padding back if needed
        hawk_id_padded = hawk.id
        padding = 4 - (len(hawk_id_padded) % 4)
        if padding != 4:
            hawk_id_padded += "=" * padding

        decoded = base64.urlsafe_b64decode(hawk_id_padded).decode("utf-8")
        parts = decoded.split(":")
        if len(parts) == 3:
            expiry_timestamp = int(parts[2])
            expiry_dt = datetime.fromtimestamp(expiry_timestamp, tz=timezone.utc)
            expiry_iso = expiry_dt.isoformat()
        else:
            expiry_iso = None
    except Exception:
        expiry_iso = None

    hawk_dict = {
        "id": hawk.id,
        "key": hawk.key,
        "api_endpoint": hawk.api_endpoint,
        "uid": hawk.uid,
        "duration": hawk.duration,
        "hashalg": hawk.hashalg,
    }

    if expiry_iso:
        hawk_dict["expires_at"] = expiry_iso

    if json_only:
        click.echo(json.dumps(hawk_dict, indent=2))
    else:
        click.echo("\n" + "=" * 40)
        click.echo("HAWK Credentials")
        click.echo("=" * 40)
        click.echo(f"ID:           {hawk.id}")
        click.echo(f"Key:          {hawk.key}")
        click.echo(f"API Endpoint: {hawk.api_endpoint}")
        click.echo(f"UID:          {hawk.uid}")
        click.echo(f"Duration:     {hawk.duration}s")
        click.echo(f"Hash Alg:     {hawk.hashalg}")
        if expiry_iso:
            click.echo(f"Expires At:   {expiry_iso}")
        click.echo("\nJSON:")
        click.echo(json.dumps(hawk_dict, indent=2))


if __name__ == "__main__":
    main()
