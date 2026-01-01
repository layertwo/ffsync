#!/usr/bin/env python3
"""
FFSync API Client

A comprehensive client for interacting with the FFSync (Firefox Sync) storage API
using HAWK authentication.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import click
import requests
from requests_hawk import HawkAuth


class FFSyncError(Exception):
    """Base exception for FFSync API errors"""

    pass


class AuthenticationError(FFSyncError):
    """Authentication-related errors"""

    pass


class CollectionNotFoundError(FFSyncError):
    """Collection not found errors"""

    pass


class QuotaExceededError(FFSyncError):
    """Storage quota exceeded errors"""

    pass


class ConflictError(FFSyncError):
    """Conflict errors (e.g., version mismatch)"""

    pass


class FFSyncClient:
    """Client for FFSync storage API with HAWK authentication"""

    def __init__(
        self,
        hawk_id: str,
        hawk_key: str,
        api_endpoint: str,
        algorithm: str = "sha256",
    ):
        """
        Initialize FFSync client

        Args:
            hawk_id: HAWK credential ID
            hawk_key: HAWK credential key
            api_endpoint: API endpoint URL
            algorithm: HAWK hash algorithm (default: sha256)
        """
        from urllib.parse import urlparse
        
        self.base_url = api_endpoint.rstrip("/")
        self.logger = logging.getLogger(__name__)
        
        # Parse the API endpoint to extract host for HAWK signing
        parsed = urlparse(self.base_url)
        self.hawk_host = parsed.hostname or ""
        self.hawk_port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Create HAWK authentication
        # Set always_hash_content=False to avoid hashing empty GET request bodies
        self.auth = HawkAuth(
            id=hawk_id,
            key=hawk_key,
            algorithm=algorithm,
            always_hash_content=False,
        )

        self.logger.info(f"Initialized FFSync client for endpoint: {self.base_url}")

    def _make_request(self, method: str, path: str, **kwargs) -> requests.Response:
        """
        Make authenticated request to FFSync API

        Args:
            method: HTTP method
            path: API path (without base URL)
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            FFSyncError: For API-specific errors
        """
        url = f"{self.base_url}{path}"
        self.logger.info(f"Making {method} request to {url}")

        # Add authentication
        kwargs["auth"] = self.auth

        # Set default headers
        headers = kwargs.get("headers", {})
        headers.setdefault("Content-Type", "application/json")
        kwargs["headers"] = headers

        self.logger.debug(f"{method} {url}")
        self.logger.debug(f"Headers before request: {headers}")

        try:
            response = requests.request(method, url, **kwargs)
            self.logger.debug(f"Request headers sent: {response.request.headers}")
            self.logger.debug(f"Response status: {response.status_code}")

            # Handle common HTTP errors
            if response.status_code == 401:
                raise AuthenticationError("Authentication failed")
            elif response.status_code == 404 and "collection" in path.lower():
                raise CollectionNotFoundError("Collection not found")
            elif response.status_code == 409:
                raise ConflictError("Conflict - resource may have been modified")
            elif response.status_code == 413:
                raise QuotaExceededError("Request too large or quota exceeded")
            elif response.status_code >= 400:
                try:
                    error_data = response.json()
                    FFSyncError(
                        f"API error: {response.status_code}: {error_data}"
                    )
                except json.JSONDecodeError:
                    raise FFSyncError(f"HTTP {response.status_code}: {response.text}")

            return response

        except requests.RequestException as e:
            raise FFSyncError(f"Request failed: {e}")

    def _get_json(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make GET request and return JSON response"""
        response = self._make_request("GET", path, **kwargs)
        return response.json()

    def _post_json(
        self, path: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """Make POST request and return JSON response"""
        if data:
            kwargs["json"] = data
        response = self._make_request("POST", path, **kwargs)
        return response.json() if response.content else {}

    def _put_json(
        self, path: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """Make PUT request and return JSON response"""
        if data:
            kwargs["json"] = data
        response = self._make_request("PUT", path, **kwargs)
        return response.json() if response.content else {}

    def _delete_json(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make DELETE request and return JSON response"""
        response = self._make_request("DELETE", path, **kwargs)
        return response.json() if response.content else {}

    # Info Operations
    def get_collections_info(self) -> Dict[str, Any]:
        """Get metadata for all collections"""
        return self._get_json("/info/collections")

    def get_collection_counts(self) -> Dict[str, Any]:
        """Get object counts for all collections"""
        return self._get_json("/info/collection_counts")

    def get_collection_usage(self) -> Dict[str, Any]:
        """Get storage usage for all collections"""
        return self._get_json("/info/collection_usage")

    def get_quota_info(self) -> Dict[str, Any]:
        """Get storage quota information"""
        return self._get_json("/info/quota")

    # Collection Operations
    def list_collections(self) -> Dict[str, Any]:
        """List all collections with their metadata"""
        return self._get_json("/storage")

    def create_collection(
        self, collection_name: str, objects: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Create a new collection

        Args:
            collection_name: Name of the collection to create
            objects: Optional list of BSO objects to add
        """
        data = {"objects": objects or []}
        return self._post_json(f"/storage/{collection_name}", data)

    def get_collection(self, collection_name: str) -> Dict[str, Any]:
        """Get collection metadata"""
        return self._get_json(f"/storage/{collection_name}")

    def update_collection(
        self,
        collection_name: str,
        objects: List[Dict[str, Any]],
        if_unmodified_since: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update collection with batch objects

        Args:
            collection_name: Name of the collection
            objects: List of BSO objects to update
            if_unmodified_since: Optional timestamp for conditional update
        """
        headers = {}
        if if_unmodified_since:
            headers["X-If-Unmodified-Since"] = str(if_unmodified_since)

        data = {"objects": objects}
        return self._put_json(f"/storage/{collection_name}", data, headers=headers)

    def delete_collection(self, collection_name: str) -> Dict[str, Any]:
        """Delete an entire collection"""
        return self._delete_json(f"/storage/{collection_name}")

    # Basic Storage Object (BSO) Operations
    def get_bso(self, collection_name: str, object_id: str) -> Dict[str, Any]:
        """Get a specific storage object"""
        return self._get_json(f"/storage/{collection_name}/{object_id}")

    def update_bso(
        self,
        collection_name: str,
        object_id: str,
        payload: str,
        sortindex: Optional[int] = None,
        ttl: Optional[int] = None,
        if_unmodified_since: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update a storage object

        Args:
            collection_name: Name of the collection
            object_id: ID of the object
            payload: JSON payload for the object
            sortindex: Optional sort index
            ttl: Optional time-to-live in seconds
            if_unmodified_since: Optional timestamp for conditional update
        """
        headers = {}
        if if_unmodified_since:
            headers["X-If-Unmodified-Since"] = str(if_unmodified_since)

        data = {"id": object_id, "payload": payload}
        if sortindex is not None:
            data["sortindex"] = sortindex
        if ttl is not None:
            data["ttl"] = ttl

        return self._put_json(
            f"/storage/{collection_name}/{object_id}", data, headers=headers
        )

    def delete_bso(self, collection_name: str, object_id: str) -> Dict[str, Any]:
        """Delete a specific storage object"""
        return self._delete_json(f"/storage/{collection_name}/{object_id}")

    # Storage Operations
    def delete_all_storage(self) -> Dict[str, Any]:
        """Delete all storage data for the authenticated user"""
        return self._delete_json("/storage")


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def load_hawk_credentials(credentials_file: str) -> Dict[str, str]:
    """Load HAWK credentials from JSON file"""
    try:
        with open(credentials_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise AuthenticationError(f"Credentials file not found: {credentials_file}")
    except json.JSONDecodeError as e:
        raise AuthenticationError(f"Invalid JSON in credentials file: {e}")


def get_client(ctx):
    """Get FFSync client from context"""
    return ctx.obj["client"]


# Click CLI implementation
@click.group()
@click.option(
    "--hawk-id",
    envvar="HAWK_ID",
    help="HAWK credential ID (or set HAWK_ID env var)",
)
@click.option(
    "--hawk-key",
    envvar="HAWK_KEY",
    help="HAWK credential key (or set HAWK_KEY env var)",
)
@click.option(
    "--api-endpoint",
    envvar="HAWK_API_ENDPOINT",
    help="API endpoint URL (or set HAWK_API_ENDPOINT env var)",
)
@click.option(
    "--credentials-file",
    type=click.Path(exists=True),
    help="JSON file with HAWK credentials (from get_hawk_token.py)",
)
@click.option(
    "--algorithm",
    default="sha256",
    help="HAWK hash algorithm (default: sha256)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(
    ctx, hawk_id, hawk_key, api_endpoint, credentials_file, algorithm, verbose
):
    """FFSync API Client - Interact with Firefox Sync storage API using HAWK authentication

    Credentials can be provided via:
    1. Command-line options (--hawk-id, --hawk-key, --api-endpoint)
    2. Environment variables (HAWK_ID, HAWK_KEY, HAWK_API_ENDPOINT)
    3. JSON file from get_hawk_token.py (--credentials-file)

    Example using credentials file:
        python ffsync_client.py --credentials-file hawk_creds.json info collections

    Example using environment variables:
        export HAWK_ID="your-hawk-id"
        export HAWK_KEY="your-hawk-key"
        export HAWK_API_ENDPOINT="https://sync.example.com/storage"
        python ffsync_client.py info collections
    """
    # Setup logging
    setup_logging(verbose)

    # Initialize context
    ctx.ensure_object(dict)

    try:
        # Load credentials from file if provided
        if credentials_file:
            creds = load_hawk_credentials(credentials_file)
            hawk_id = creds.get("id")
            hawk_key = creds.get("key")
            api_endpoint = "https://storage.beta.ffsync.layertwo.dev" #creds.get("api_endpoint")
            algorithm = creds.get("hashalg", algorithm)

        # Validate required credentials
        if not all([hawk_id, hawk_key, api_endpoint]):
            raise AuthenticationError(
                "Missing required credentials. Provide --hawk-id, --hawk-key, and "
                "--api-endpoint, or use --credentials-file, or set environment variables."
            )

        # Initialize client
        client = FFSyncClient(hawk_id, hawk_key, api_endpoint, algorithm)
        ctx.obj["client"] = client

    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(click.style(f"Unexpected error: {e}", fg="red"), err=True)
        ctx.exit(1)


# Info commands
@cli.group()
def info():
    """Get storage information and metadata"""
    pass


@info.command("collections")
@click.pass_context
def info_collections(ctx):
    """Get metadata for all collections"""
    try:
        client = get_client(ctx)
        result = client.get_collections_info()
        click.echo(json.dumps(result, indent=2))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


@info.command("counts")
@click.pass_context
def info_counts(ctx):
    """Get object counts for all collections"""
    try:
        client = get_client(ctx)
        result = client.get_collection_counts()
        click.echo(json.dumps(result, indent=2))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


@info.command("usage")
@click.pass_context
def info_usage(ctx):
    """Get storage usage for all collections"""
    try:
        client = get_client(ctx)
        result = client.get_collection_usage()
        click.echo(json.dumps(result, indent=2))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


@info.command("quota")
@click.pass_context
def info_quota(ctx):
    """Get storage quota information"""
    try:
        client = get_client(ctx)
        result = client.get_quota_info()
        click.echo(json.dumps(result, indent=2))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


# Collection commands
@cli.group()
def collection():
    """Collection operations"""
    pass


@collection.command("list")
@click.pass_context
def collection_list(ctx):
    """List all collections with their metadata"""
    try:
        client = get_client(ctx)
        result = client.list_collections()
        click.echo(json.dumps(result, indent=2))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


@collection.command("create")
@click.argument("name")
@click.pass_context
def collection_create(ctx, name):
    """Create a new collection"""
    try:
        client = get_client(ctx)
        result = client.create_collection(name)
        click.echo(json.dumps(result, indent=2))
        click.echo(
            click.style(f"✓ Collection '{name}' created successfully", fg="green")
        )
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


@collection.command("get")
@click.argument("name")
@click.pass_context
def collection_get(ctx, name):
    """Get collection metadata"""
    try:
        client = get_client(ctx)
        result = client.get_collection(name)
        click.echo(json.dumps(result, indent=2))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


@collection.command("delete")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def collection_delete(ctx, name, yes):
    """Delete an entire collection"""
    if not yes:
        if not click.confirm(f"Are you sure you want to delete collection '{name}'?"):
            click.echo("Cancelled.")
            return

    try:
        client = get_client(ctx)
        result = client.delete_collection(name)
        click.echo(json.dumps(result, indent=2))
        click.echo(
            click.style(f"✓ Collection '{name}' deleted successfully", fg="green")
        )
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


# BSO commands
@cli.group()
def bso():
    """Basic Storage Object operations"""
    pass


@bso.command("get")
@click.argument("collection")
@click.argument("object_id")
@click.pass_context
def bso_get(ctx, collection, object_id):
    """Get a specific storage object"""
    try:
        client = get_client(ctx)
        result = client.get_bso(collection, object_id)
        click.echo(json.dumps(result, indent=2))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


@bso.command("update")
@click.argument("collection")
@click.argument("object_id")
@click.argument("payload")
@click.option("--sortindex", type=int, help="Sort index for ordering")
@click.option("--ttl", type=int, help="Time-to-live in seconds")
@click.option("--if-unmodified-since", type=int, help="Conditional update timestamp")
@click.pass_context
def bso_update(
    ctx, collection, object_id, payload, sortindex, ttl, if_unmodified_since
):
    """Update a storage object"""
    try:
        client = get_client(ctx)
        result = client.update_bso(
            collection, object_id, payload, sortindex, ttl, if_unmodified_since
        )
        click.echo(json.dumps(result, indent=2))
        click.echo(click.style(f"✓ BSO '{object_id}' updated successfully", fg="green"))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


@bso.command("delete")
@click.argument("collection")
@click.argument("object_id")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def bso_delete(ctx, collection, object_id, yes):
    """Delete a specific storage object"""
    if not yes:
        if not click.confirm(
            f"Are you sure you want to delete BSO '{object_id}' from collection '{collection}'?"
        ):
            click.echo("Cancelled.")
            return

    try:
        client = get_client(ctx)
        result = client.delete_bso(collection, object_id)
        click.echo(json.dumps(result, indent=2))
        click.echo(click.style(f"✓ BSO '{object_id}' deleted successfully", fg="green"))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


# Storage commands
@cli.group()
def storage():
    """Storage operations"""
    pass


@storage.command("delete-all")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def storage_delete_all(ctx, yes):
    """Delete all storage data for the authenticated user"""
    if not yes:
        click.echo(
            click.style(
                "WARNING: This will delete ALL storage data for the authenticated user!",
                fg="red",
                bold=True,
            )
        )
        if not click.confirm("Are you absolutely sure you want to continue?"):
            click.echo("Cancelled.")
            return

    try:
        client = get_client(ctx)
        result = client.delete_all_storage()
        click.echo(json.dumps(result, indent=2))
        click.echo(click.style("✓ All storage data deleted successfully", fg="green"))
    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)


if __name__ == "__main__":
    cli()
