"""Unit tests for OAuth Code Manager"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.services.oauth_code_manager import OAuthCodeManager


@pytest.fixture
def mock_table():
    return MagicMock()


@pytest.fixture
def manager(mock_table):
    return OAuthCodeManager(table=mock_table, code_ttl_seconds=600, refresh_ttl_seconds=86400)


class TestCreateAuthorizationCode:
    def test_returns_code_string(self, manager):
        code = manager.create_authorization_code(
            uid="uid1",
            client_id="client1",
            scope="openid",
            code_challenge="challenge123",
            code_challenge_method="S256",
        )
        assert isinstance(code, str)
        assert len(code) > 0

    def test_stores_code_in_dynamo(self, manager, mock_table):
        manager.create_authorization_code(
            uid="uid1",
            client_id="client1",
            scope="openid",
            code_challenge="challenge123",
            code_challenge_method="S256",
        )
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args.kwargs["Item"]
        assert item["PK"].startswith("OAUTHCODE#")
        assert item["uid"] == "uid1"
        assert item["clientId"] == "client1"
        assert item["scope"] == "openid"
        assert item["codeChallenge"] == "challenge123"
        assert item["codeChallengeMethod"] == "S256"
        assert "expiry" in item

    def test_different_calls_produce_different_codes(self, manager):
        code1 = manager.create_authorization_code(
            uid="uid1",
            client_id="client1",
            scope="openid",
            code_challenge="c1",
            code_challenge_method="S256",
        )
        code2 = manager.create_authorization_code(
            uid="uid1",
            client_id="client1",
            scope="openid",
            code_challenge="c2",
            code_challenge_method="S256",
        )
        assert code1 != code2


class TestConsumeAuthorizationCode:
    @patch("src.services.oauth_code_manager.time")
    def test_returns_code_data_atomically(self, mock_time, manager, mock_table):
        mock_time.time.return_value = 1000000.0
        mock_table.delete_item.return_value = {
            "Attributes": {
                "PK": "OAUTHCODE#abc123",
                "uid": "uid1",
                "clientId": "client1",
                "scope": "openid",
                "codeChallenge": "challenge",
                "codeChallengeMethod": "S256",
                "expiry": 1000600,
            }
        }
        result = manager.consume_authorization_code("abc123")
        assert result is not None
        assert result["uid"] == "uid1"
        assert result["clientId"] == "client1"
        assert result["scope"] == "openid"
        assert result["codeChallenge"] == "challenge"
        mock_table.delete_item.assert_called_once()
        # Verify it's called with ReturnValues and ConditionExpression
        call_kwargs = mock_table.delete_item.call_args.kwargs
        assert call_kwargs["ReturnValues"] == "ALL_OLD"
        assert call_kwargs["ConditionExpression"] == "attribute_exists(PK)"

    def test_returns_none_for_unknown_code(self, manager, mock_table):
        mock_table.delete_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
            "DeleteItem",
        )
        result = manager.consume_authorization_code("nonexistent")
        assert result is None

    @patch("src.services.oauth_code_manager.time")
    def test_returns_none_for_expired_code(self, mock_time, manager, mock_table):
        mock_time.time.return_value = 1000000.0
        mock_table.delete_item.return_value = {
            "Attributes": {
                "PK": "OAUTHCODE#abc123",
                "uid": "uid1",
                "clientId": "client1",
                "scope": "openid",
                "codeChallenge": "challenge",
                "codeChallengeMethod": "S256",
                "expiry": 999999,
            }
        }
        result = manager.consume_authorization_code("abc123")
        assert result is None


class TestCreateRefreshToken:
    def test_returns_token_string(self, manager):
        token = manager.create_refresh_token(uid="uid1", client_id="client1", scope="openid")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_stores_refresh_in_dynamo(self, manager, mock_table):
        manager.create_refresh_token(uid="uid1", client_id="client1", scope="openid")
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args.kwargs["Item"]
        assert item["PK"].startswith("REFRESH#")
        assert item["uid"] == "uid1"
        assert item["clientId"] == "client1"
        assert item["scope"] == "openid"
        assert "expiry" in item


class TestConsumeRefreshToken:
    @patch("src.services.oauth_code_manager.time")
    def test_returns_data_atomically(self, mock_time, manager, mock_table):
        mock_time.time.return_value = 1000000.0
        token_hash = hashlib.sha256(b"token123").hexdigest()
        mock_table.delete_item.return_value = {
            "Attributes": {
                "PK": f"REFRESH#{token_hash}",
                "uid": "uid1",
                "clientId": "client1",
                "scope": "openid",
                "expiry": 1086400,
            }
        }
        result = manager.consume_refresh_token(token_hash)
        assert result is not None
        assert result["uid"] == "uid1"
        mock_table.delete_item.assert_called_once()
        call_kwargs = mock_table.delete_item.call_args.kwargs
        assert call_kwargs["ReturnValues"] == "ALL_OLD"
        assert call_kwargs["ConditionExpression"] == "attribute_exists(PK)"

    def test_returns_none_for_unknown_token(self, manager, mock_table):
        mock_table.delete_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
            "DeleteItem",
        )
        result = manager.consume_refresh_token("nonexistent")
        assert result is None

    @patch("src.services.oauth_code_manager.time")
    def test_returns_none_for_expired_token(self, mock_time, manager, mock_table):
        mock_time.time.return_value = 1000000.0
        token_hash = hashlib.sha256(b"token123").hexdigest()
        mock_table.delete_item.return_value = {
            "Attributes": {
                "PK": f"REFRESH#{token_hash}",
                "uid": "uid1",
                "clientId": "client1",
                "scope": "openid",
                "expiry": 999999,
            }
        }
        result = manager.consume_refresh_token(token_hash)
        assert result is None


class TestConsumeAuthorizationCodeEdgeCases:
    @patch("src.services.oauth_code_manager.time")
    def test_reraises_non_conditional_error(self, mock_time, manager, mock_table):
        mock_time.time.return_value = 1000000.0
        mock_table.delete_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": ""}},
            "DeleteItem",
        )
        with pytest.raises(ClientError) as exc_info:
            manager.consume_authorization_code("abc")
        assert exc_info.value.response["Error"]["Code"] == "InternalServerError"

    @patch("src.services.oauth_code_manager.time")
    def test_returns_none_for_empty_attributes(self, mock_time, manager, mock_table):
        mock_time.time.return_value = 1000000.0
        mock_table.delete_item.return_value = {}
        result = manager.consume_authorization_code("abc")
        assert result is None


class TestConsumeRefreshTokenEdgeCases:
    @patch("src.services.oauth_code_manager.time")
    def test_reraises_non_conditional_error(self, mock_time, manager, mock_table):
        mock_time.time.return_value = 1000000.0
        mock_table.delete_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": ""}},
            "DeleteItem",
        )
        with pytest.raises(ClientError) as exc_info:
            manager.consume_refresh_token("hash")
        assert exc_info.value.response["Error"]["Code"] == "InternalServerError"

    @patch("src.services.oauth_code_manager.time")
    def test_returns_none_for_empty_attributes(self, mock_time, manager, mock_table):
        mock_time.time.return_value = 1000000.0
        mock_table.delete_item.return_value = {}
        result = manager.consume_refresh_token("hash")
        assert result is None


class TestVerifyCodeChallenge:
    def test_valid_s256_challenge(self, manager):
        # verifier -> SHA256 -> base64url = challenge
        import base64

        verifier = "test-verifier-string"
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert manager.verify_code_challenge(verifier, challenge, "S256") is True

    def test_invalid_s256_challenge(self, manager):
        assert manager.verify_code_challenge("wrong", "invalid_challenge", "S256") is False

    def test_plain_challenge(self, manager):
        verifier = "plain-challenge-value"
        assert manager.verify_code_challenge(verifier, verifier, "plain") is True

    def test_plain_challenge_mismatch(self, manager):
        assert manager.verify_code_challenge("a", "b", "plain") is False

    def test_unsupported_method_returns_false(self, manager):
        assert manager.verify_code_challenge("v", "c", "unsupported") is False


class TestDeleteRefreshToken:
    def test_deletes_by_hash(self, manager, mock_table):
        manager.delete_refresh_token("somehash")
        mock_table.delete_item.assert_called_once()
