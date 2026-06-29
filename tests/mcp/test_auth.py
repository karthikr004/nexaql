# Copyright (c) 2026-present NexaQL Contributors
"""Tests for the auth module — UserContext construction, JWT verification."""

from __future__ import annotations

import jwt as pyjwt
import pytest

from nexaql.auth import _claims_to_user_context, _dict_to_user_context


class TestDictToUserContext:
    def test_none_returns_admin(self):
        user = _dict_to_user_context(None)
        assert user.roles == ["admin"]

    def test_empty_dict_returns_admin(self):
        user = _dict_to_user_context({})
        assert user.roles == ["admin"]

    def test_full_context(self):
        user = _dict_to_user_context({
            "user_id": "alice",
            "roles": ["analyst", "manager"],
            "region": "US-EAST",
            "department": "engineering",
            "team_id": "platform",
        })
        assert user.user_id == "alice"
        assert user.roles == ["analyst", "manager"]
        assert user.region == "US-EAST"
        assert user.department == "engineering"
        assert user.team_id == "platform"

    def test_single_role_string_becomes_list(self):
        user = _dict_to_user_context({"roles": "analyst"})
        assert user.roles == ["analyst"]

    def test_custom_attributes(self):
        user = _dict_to_user_context({
            "user_id": "bob",
            "roles": ["admin"],
            "cost_center": "CC-100",
            "vendor_id": "V-42",
        })
        assert user.attributes == {"cost_center": "CC-100", "vendor_id": "V-42"}


class TestClaimsToUserContext:
    def test_sub_maps_to_user_id(self):
        user = _claims_to_user_context({"sub": "alice", "roles": ["admin"]})
        assert user.user_id == "alice"

    def test_jwt_standard_claims_excluded(self):
        user = _claims_to_user_context({
            "sub": "alice",
            "roles": ["admin"],
            "iss": "nexaql",
            "exp": 9999999999,
            "iat": 1000000000,
            "nbf": 1000000000,
            "aud": "api",
            "jti": "abc123",
        })
        assert "iss" not in user.attributes
        assert "exp" not in user.attributes
        assert "iat" not in user.attributes

    def test_custom_claims_become_attributes(self):
        user = _claims_to_user_context({
            "sub": "bob",
            "roles": ["analyst"],
            "cost_center": "CC-200",
        })
        assert user.attributes == {"cost_center": "CC-200"}


class TestJWTVerification:
    def test_valid_token(self, jwt_secret):
        token = pyjwt.encode({"sub": "alice", "roles": ["admin"]}, jwt_secret, algorithm="HS256")
        payload = pyjwt.decode(token, jwt_secret, algorithms=["HS256"])
        assert payload["sub"] == "alice"

    def test_tampered_token_rejected(self, jwt_secret):
        token = pyjwt.encode({"sub": "alice"}, jwt_secret, algorithm="HS256")
        with pytest.raises(pyjwt.InvalidSignatureError):
            pyjwt.decode(token + "tampered", jwt_secret, algorithms=["HS256"])

    def test_wrong_secret_rejected(self, jwt_secret):
        token = pyjwt.encode({"sub": "alice"}, jwt_secret, algorithm="HS256")
        with pytest.raises(pyjwt.InvalidSignatureError):
            pyjwt.decode(token, "wrong-secret-key-that-is-32-bytes!!", algorithms=["HS256"])
