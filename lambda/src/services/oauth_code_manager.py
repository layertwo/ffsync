"""OAuth Code Manager for authorization codes and refresh tokens in DynamoDB."""

import base64
import hashlib
import hmac
import os
import time
from typing import Any, Optional

from botocore.exceptions import ClientError

_PK = "PK"
OAUTHCODE_PREFIX = "OAUTHCODE"
REFRESH_PREFIX = "REFRESH"


class OAuthCodeManager:
    """Manages OAuth authorization codes and refresh tokens."""

    def __init__(
        self,
        table: Any,
        code_ttl_seconds: int = 600,
        refresh_ttl_seconds: int = 86400,
    ):
        self._table = table
        self._code_ttl = code_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds

    def create_authorization_code(
        self,
        uid: str,
        client_id: str,
        scope: str,
        code_challenge: str,
        code_challenge_method: str,
        keys_jwe: str = "",
    ) -> str:
        """Create an authorization code and store in DynamoDB.

        Returns:
            The authorization code string.
        """
        code = os.urandom(32).hex()
        now = int(time.time())

        self._table.put_item(
            Item={
                _PK: f"{OAUTHCODE_PREFIX}#{code}",
                "uid": uid,
                "clientId": client_id,
                "scope": scope,
                "codeChallenge": code_challenge,
                "codeChallengeMethod": code_challenge_method,
                "keysJwe": keys_jwe,
                "expiry": now + self._code_ttl,
            }
        )
        return code

    def consume_authorization_code(self, code: str) -> Optional[dict]:
        """Consume an authorization code (single-use) atomically.

        Uses delete_item with ReturnValues to avoid TOCTOU race condition.

        Returns:
            Dict with uid, clientId, scope, codeChallenge, codeChallengeMethod
            or None if not found or expired.
        """
        try:
            response = self._table.delete_item(
                Key={_PK: f"{OAUTHCODE_PREFIX}#{code}"},
                ReturnValues="ALL_OLD",
                ConditionExpression="attribute_exists(PK)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

        item = response.get("Attributes")
        if not item:
            return None

        # Check expiry server-side
        if item.get("expiry", 0) < int(time.time()):
            return None

        return {
            "uid": item["uid"],
            "clientId": item["clientId"],
            "scope": item["scope"],
            "codeChallenge": item["codeChallenge"],
            "codeChallengeMethod": item["codeChallengeMethod"],
            "keysJwe": item.get("keysJwe", ""),
        }

    def create_refresh_token(self, uid: str, client_id: str, scope: str) -> str:
        """Create a refresh token and store in DynamoDB.

        Returns:
            The refresh token string.
        """
        token = os.urandom(32).hex()
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        now = int(time.time())

        self._table.put_item(
            Item={
                _PK: f"{REFRESH_PREFIX}#{token_hash}",
                "uid": uid,
                "clientId": client_id,
                "scope": scope,
                "expiry": now + self._refresh_ttl,
            }
        )
        return token

    def consume_refresh_token(self, token_hash: str) -> Optional[dict]:
        """Consume a refresh token (single-use) atomically.

        Uses delete_item with ReturnValues to avoid TOCTOU race condition.

        Args:
            token_hash: SHA256 hex hash of the refresh token.

        Returns:
            Dict with uid, clientId, scope or None if not found or expired.
        """
        try:
            response = self._table.delete_item(
                Key={_PK: f"{REFRESH_PREFIX}#{token_hash}"},
                ReturnValues="ALL_OLD",
                ConditionExpression="attribute_exists(PK)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

        item = response.get("Attributes")
        if not item:
            return None

        # Check expiry server-side
        if item.get("expiry", 0) < int(time.time()):
            return None

        return {
            "uid": item["uid"],
            "clientId": item["clientId"],
            "scope": item["scope"],
        }

    def delete_refresh_token(self, token_hash: str) -> None:
        """Delete a refresh token by its hash."""
        self._table.delete_item(Key={_PK: f"{REFRESH_PREFIX}#{token_hash}"})

    @staticmethod
    def verify_code_challenge(verifier: str, challenge: str, method: str) -> bool:
        """Verify a PKCE code challenge.

        Args:
            verifier: The code_verifier from the token request.
            challenge: The code_challenge from the authorization request.
            method: The code_challenge_method (S256 or plain).

        Returns:
            True if the verifier matches the challenge.
        """
        if method == "S256":
            digest = hashlib.sha256(verifier.encode("ascii")).digest()
            computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            return hmac.compare_digest(computed, challenge)
        elif method == "plain":
            return hmac.compare_digest(verifier, challenge)
        return False
