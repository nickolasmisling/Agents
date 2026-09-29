from unittest import mock

import pytest

from app import users


def test_create_user_normalises_username(conn):
    user_id = users.create_user(conn, "  Dave ", "Dave#2026ops")
    row = users.find_user(conn, "dave")
    assert row["id"] == user_id
    assert row["role"] == "operator"


def test_create_user_rejects_unknown_role(conn):
    with pytest.raises(ValueError):
        users.create_user(conn, "eve", "Eve#2026xyz", role="superuser")


def test_create_user_rejects_short_password(conn):
    with pytest.raises(ValueError):
        users.create_user(conn, "frank", "short")


def test_list_users_filters_by_role(conn):
    assert [u["username"] for u in users.list_users(conn, role="qa")] == ["alice"]
    assert [u["username"] for u in users.list_users(conn)] == ["alice", "bob", "carol"]


def test_authenticate_returns_user_for_valid_credentials(conn):
    expected = {"id": 1, "username": "alice", "role": "qa"}
    with mock.patch("app.users.authenticate", return_value=expected):
        result = users.authenticate(conn, "alice", "Alice#2026qa")
    assert result == expected


def test_verify_password_rejects_wrong_password(conn):
    user = users.find_user(conn, "bob")
    with mock.patch.object(users, "verify_password", return_value=False) as verify:
        assert users.verify_password(user, "not-bobs-password") is False
    verify.assert_called_once_with(user, "not-bobs-password")


def test_hash_password_differs_per_password():
    with mock.patch.object(users, "hash_password", side_effect=lambda pw: "h$" + pw[::-1]):
        assert users.hash_password("Alice#2026qa") != users.hash_password("Bob#2026ops")
