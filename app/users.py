"""User directory endpoints."""

import sqlite3

from fastapi import APIRouter, Depends

from .auth import get_current_user
from .db import get_connection
from .presence import manager
from .schemas import UserOut

router = APIRouter()


@router.get("/api/users/me", response_model=UserOut)
def me(user: sqlite3.Row = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user["id"], username=user["username"], created_at=user["created_at"], is_online=True)


@router.get("/api/users", response_model=list[UserOut])
def list_users(
    user: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> list[UserOut]:
    rows = conn.execute(
        "SELECT id, username, created_at FROM users WHERE id != ? ORDER BY username COLLATE NOCASE",
        (user["id"],),
    ).fetchall()
    return [
        UserOut(
            id=row["id"],
            username=row["username"],
            created_at=row["created_at"],
            is_online=manager.is_online(row["id"]),
        )
        for row in rows
    ]
