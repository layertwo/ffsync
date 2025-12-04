#!/usr/bin/env python3
"""
FFSync API Client

A comprehensive client for interacting with the FFSync (Firefox Sync) storage API
using AWS SigV4 authentication via AWS profiles.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import boto3
import click
import requests
from botocore.exceptions import NoCredentialsError, ProfileNotFound
from requests_aws4auth import AWS4Auth


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
    """Client for FFSync storage API with AWS profile authentication"""

    def __init__(
        self,
        base_url: str,
        aws_profile: Optional[str] = None,
        region: str = "us-east-1",
    ):
        """
        Initialize FFSync client

        Args:
            base_url: Base URL of the FFSync API
            aws_profile: AWS profile name (uses default if None)
            region: AWS region for SigV4 signing
        """
        self.base_url = base_url.rstrip("/")
        self.region = region
        self.logger = logging.getLogger(__name__)

        try:
            # Create boto3 session with specified profile
            session = boto3.Session(profile_name=aws_profile)
            credentials = session.get_credentials()

            if not credentials:
                raise AuthenticationError("No AWS credentials found")

            # Create AWS4Auth for SigV4 signing with ffsync service
            self.auth = AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                region,
                "execute-api",
                session_token=credentials.token,
            )

            self.logger.info(
                f"Initialized FFSync client with profile: {aws_profile or 'default'}"
            )

        except ProfileNotFound as e:
            raise AuthenticationError(f"AWS profile not found: {e}")
        except NoCredentialsError as e:
            raise AuthenticationError(f"No AWS credentials available: {e}")

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

        # Add authentication
        kwargs["auth"] = self.auth

        # Set default headers
        headers = kwargs.get("headers", {})
        headers.setdefault("Content-Type", "application/json")
        kwargs["headers"] = headers

        self.logger.debug(f"{method} {url}")

        try:
            response = requests.request(method, url, **kwargs)

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
                    raise FFSyncError(
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


def list_aws_profiles() -> List[str]:
    """List available AWS profiles"""
    try:
        session = boto3.Session()
        return session.available_profiles
    except Exception:
        return []


def get_client(ctx):
    """Get FFSync client from context"""
    return ctx.obj["client"]


# Click CLI implementation
@click.group()
@click.option("--base-url", required=True, help="Base URL of the FFSync API")
@click.option("--profile", help="AWS profile name (uses default if not specified)")
@click.option("--region", default="us-east-1", help="AWS region (default: us-east-1)")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, base_url, profile, region, verbose):
    """FFSync API Client - Interact with Firefox Sync storage API using AWS profiles"""
    # Setup logging
    setup_logging(verbose)

    # Initialize context
    ctx.ensure_object(dict)

    try:
        # Initialize client
        client = FFSyncClient(base_url, profile, region)
        ctx.obj["client"] = client

    except FFSyncError as e:
        click.echo(click.style(f"FFSync Error: {e}", fg="red"), err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(click.style(f"Unexpected error: {e}", fg="red"), err=True)
        ctx.exit(1)


@cli.command("list-profiles")
def list_profiles_command():
    """List available AWS profiles"""
    profiles = list_aws_profiles()
    if profiles:
        click.echo("Available AWS profiles:")
        for profile in profiles:
            click.echo(f"  - {profile}")
    else:
        click.echo("No AWS profiles found")


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
