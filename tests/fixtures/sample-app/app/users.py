"""User accounts and password checks."""

import hashlib

ROLES = ("operator", "qa", "supervisor", "admin")
MIN_PASSWORD_LENGTH = 8


def hash_password(password):
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def create_user(conn, username, password, role="operator"):
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username.strip().lower(), hash_password(password), role),
    )
    conn.commit()
    return cur.lastrowid


def find_user(conn, username):
    return conn.execute(
        "SELECT id, username, password_hash, role FROM users WHERE username = ?",
        (username.strip().lower(),),
    ).fetchone()


def list_users(conn, role=None):
    sql = "SELECT id, username, role FROM users"
    params = ()
    if role is not None:
        sql += " WHERE role = ?"
        params = (role,)
    sql += " ORDER BY username"
    return [dict(row) for row in conn.execute(sql, params)]


def verify_password(user, password):
    return user["password_hash"] == hash_password(password)


def authenticate(conn, username, password):
    """Return a small user dict when the credentials are valid, otherwise None."""
    user = find_user(conn, username)
    if user is None or not verify_password(user, password):
        return None
    return {"id": user["id"], "username": user["username"], "role": user["role"]}
