"""Auth account manager for DynamoDB operations on FxA accounts"""

import logging
import time
from typing import Optional

from botocore.exceptions import ClientError

_PK = "PK"
ACCOUNT_PREFIX = "ACCOUNT"
EMAIL_PREFIX = "EMAIL"
OIDCSUB_PREFIX = "OIDCSUB"

logger = logging.getLogger(__name__)


class AuthAccountManager:
    """Manages FxA account operations with DynamoDB"""

    def __init__(self, table):
        """Initialize AuthAccountManager

        Args:
            table: DynamoDB Table resource
        """
        self.table = table

    def _account_pk(self, uid: str) -> str:
        """Generate partition key for account record"""
        return f"{ACCOUNT_PREFIX}#{uid}"

    def _email_pk(self, email: str) -> str:
        """Generate partition key for email lookup record"""
        return f"{EMAIL_PREFIX}#{email}"

    def _oidcsub_pk(self, oidc_sub: str) -> str:
        """Generate partition key for OIDC subject lookup record"""
        return f"{OIDCSUB_PREFIX}#{oidc_sub}"

    @staticmethod
    def _normalize_email(email: str) -> str:
        """Normalize email: lowercase and strip whitespace"""
        return email.strip().lower()

    def create_account(
        self,
        uid: str,
        email: str,
        verify_hash: str,
        k_a: str,
        wrap_kb: str,
        oidc_sub: str,
        key_rotation_secret: str = "",
    ) -> None:
        """Create account, email lookup, and OIDC subject lookup records.

        Stores three DynamoDB items in safe order:
        1. EMAIL#{normalized_email} -- lookup record with uid (uniqueness constraint first)
        2. OIDCSUB#{oidc_sub} -- reverse lookup from OIDC subject to uid
        3. ACCOUNT#{uid} -- full account record with all fields + verified=True, createdAt

        Email is normalized (lowercased, stripped).
        EMAIL# record uses ConditionExpression to prevent duplicates.
        If later writes fail, earlier records are cleaned up to prevent orphans.

        Args:
            uid: Account unique identifier (UUID hex)
            email: User email address
            verify_hash: 64-character hex verify hash
            k_a: 64-character hex kA key
            wrap_kb: 64-character hex wrapKB key
            oidc_sub: OIDC subject identifier
            key_rotation_secret: 64-character hex per-account key rotation secret

        Raises:
            ValueError: If email already exists
        """
        normalized_email = self._normalize_email(email)
        created_at = int(time.time() * 1000)

        # Store EMAIL# lookup record first with uniqueness constraint
        try:
            self.table.put_item(
                Item={
                    _PK: self._email_pk(normalized_email),
                    "uid": uid,
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError(f"Email already exists: {normalized_email}") from e
            raise

        # Store OIDCSUB# lookup record; clean up EMAIL# if this fails
        try:
            self.table.put_item(
                Item={
                    _PK: self._oidcsub_pk(oidc_sub),
                    "uid": uid,
                },
            )
        except Exception:
            try:
                self.table.delete_item(Key={_PK: self._email_pk(normalized_email)})
            except Exception:
                logger.exception("Failed to clean up EMAIL# record for %s", normalized_email)
            raise

        # Store ACCOUNT# record; clean up EMAIL# and OIDCSUB# if this fails
        try:
            self.table.put_item(
                Item={
                    _PK: self._account_pk(uid),
                    "email": normalized_email,
                    "uid": uid,
                    "verifyHash": verify_hash,
                    "kA": k_a,
                    "wrapKB": wrap_kb,
                    "oidcSub": oidc_sub,
                    "keyRotationSecret": key_rotation_secret,
                    "verified": True,
                    "createdAt": created_at,
                }
            )
        except Exception:
            # Clean up orphaned lookup records
            for pk in [self._email_pk(normalized_email), self._oidcsub_pk(oidc_sub)]:
                try:
                    self.table.delete_item(Key={_PK: pk})
                except Exception:
                    logger.exception("Failed to clean up %s", pk)
            raise

    def get_account_by_email(self, email: str) -> Optional[dict]:
        """Look up account by email.

        1. Get EMAIL#{normalized} record
        2. If found, get ACCOUNT#{uid} record
        3. Return account dict or None

        Args:
            email: User email address

        Returns:
            Account dict or None if not found
        """
        normalized_email = self._normalize_email(email)

        # Look up EMAIL# record
        response = self.table.get_item(Key={_PK: self._email_pk(normalized_email)})

        if "Item" not in response:
            return None

        uid = response["Item"]["uid"]

        # Look up ACCOUNT# record
        return self.get_account_by_uid(uid)

    def ensure_oidcsub_record(self, uid: str, oidc_sub: str) -> None:
        """Create OIDCSUB# lookup record if it doesn't already exist.

        Used to backfill the index for accounts created before OIDCSUB# was added.
        Uses a conditional write so it's safe to call on every login.
        """
        if not oidc_sub:
            return
        try:
            self.table.put_item(
                Item={
                    _PK: self._oidcsub_pk(oidc_sub),
                    "uid": uid,
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return  # Already exists, nothing to do
            raise

    def get_account_by_oidc_sub(self, oidc_sub: str) -> Optional[dict]:
        """Look up account by OIDC subject identifier.

        1. Get OIDCSUB#{oidc_sub} record
        2. If found, get ACCOUNT#{uid} record
        3. Return account dict or None

        Args:
            oidc_sub: OIDC subject identifier

        Returns:
            Account dict or None if not found
        """
        response = self.table.get_item(Key={_PK: self._oidcsub_pk(oidc_sub)})

        if "Item" not in response:
            return None

        uid = response["Item"]["uid"]
        return self.get_account_by_uid(uid)

    def get_account_by_uid(self, uid: str) -> Optional[dict]:
        """Look up account by uid.

        Get ACCOUNT#{uid} record, return dict or None.

        Args:
            uid: Account unique identifier

        Returns:
            Account dict or None if not found
        """
        response = self.table.get_item(Key={_PK: self._account_pk(uid)})

        if "Item" not in response:
            return None

        item = response["Item"]
        # Remove the PK field from the returned dict
        item.pop(_PK, None)
        return item
