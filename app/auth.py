"""Registration, login, logout and the current-user dependency."""

import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import security
from .config import token_expire_days
from .db import get_connection
from .presence import manager
from .schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut

router = APIRouter()

_bearer = HTTPBearer(auto_error=False)


def utcnow() -> str:
    """Current UTC time as a sortable ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def user_for_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    """Return the user owning this token, or None if it is unknown or expired."""
    if not token:
        return None
    return conn.execute(
        """
        SELECT u.id, u.username, u.created_at, t.token
        FROM auth_tokens t
        JOIN users u ON u.id = t.user_id
        WHERE t.token = ? AND t.expires_at > ?
        """,
        (token, utcnow()),
    ).fetchone()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn: sqlite3.Connection = Depends(get_connection),
) -> sqlite3.Row:
    """Resolve the authenticated user, raising 401 for missing or invalid tokens."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = user_for_token(conn, credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return user


def _issue_token(conn: sqlite3.Connection, user_id: int) -> str:
    token = security.new_token()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=token_expire_days())
    conn.execute(
        "INSERT INTO auth_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    return token


def _auth_response(conn: sqlite3.Connection, user: sqlite3.Row) -> AuthResponse:
    token = _issue_token(conn, user["id"])
    return AuthResponse(
        token=token,
        user=UserOut(id=user["id"], username=user["username"], created_at=user["created_at"]),
    )


@router.post("/api/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    conn: sqlite3.Connection = Depends(get_connection),
) -> AuthResponse:
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (payload.username, security.hash_password(payload.password), utcnow()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username is already taken",
        )
    user = conn.execute(
        "SELECT id, username, created_at FROM users WHERE username = ?", (payload.username,)
    ).fetchone()
    response = _auth_response(conn, user)
    # Let connected clients know a new user is available to chat with.
    await manager.broadcast_all({"type": "user", "user": response.user.model_dump()})
    return response


@router.post("/api/auth/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    conn: sqlite3.Connection = Depends(get_connection),
) -> AuthResponse:
    user = conn.execute(
        "SELECT id, username, created_at, password_hash FROM users WHERE username = ? COLLATE NOCASE",
        (payload.username.strip(),),
    ).fetchone()
    if user is None:
        security.dummy_verify(payload.password)  # equalise timing for unknown usernames
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not security.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return _auth_response(conn, user)


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> None:
    conn.execute("DELETE FROM auth_tokens WHERE token = ?", (user["token"],))
    conn.commit()
