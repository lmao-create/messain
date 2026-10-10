"""Conversations and messages: listing, creation, history, and sending."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import get_current_user, utcnow
from .db import get_connection
from .presence import manager
from .schemas import (
    ConversationOut,
    CreateConversationRequest,
    MessageOut,
    SendMessageRequest,
    UserOut,
)

router = APIRouter()

_MESSAGE_COLUMNS = "id, conversation_id, sender_id, content, created_at"


def _participant_ids(conn: sqlite3.Connection, conversation_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT user_id FROM conversation_participants WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchall()
    return [row["user_id"] for row in rows]


def _require_conversation(conn: sqlite3.Connection, conversation_id: int, user_id: int) -> None:
    """404 when the conversation is missing, 403 when the user is not in it."""
    conversation = conn.execute(
        "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    participant = conn.execute(
        "SELECT 1 FROM conversation_participants WHERE conversation_id = ? AND user_id = ?",
        (conversation_id, user_id),
    ).fetchone()
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant of this conversation",
        )


def _conversation_out(conn: sqlite3.Connection, conversation_id: int, for_user_id: int) -> ConversationOut:
    """Build the sidebar payload for a conversation, from one participant's view."""
    conversation = conn.execute(
        "SELECT id, created_at FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    partner = conn.execute(
        """
        SELECT u.id, u.username, u.created_at
        FROM conversation_participants p
        JOIN users u ON u.id = p.user_id
        WHERE p.conversation_id = ? AND p.user_id != ?
        """,
        (conversation_id, for_user_id),
    ).fetchone()
    last = conn.execute(
        f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    ).fetchone()
    return ConversationOut(
        id=conversation["id"],
        created_at=conversation["created_at"],
        partner=UserOut(
            id=partner["id"],
            username=partner["username"],
            created_at=partner["created_at"],
            is_online=manager.is_online(partner["id"]),
        ),
        last_message=MessageOut(**dict(last)) if last else None,
    )


@router.get("/api/conversations", response_model=list[ConversationOut])
def list_conversations(
    user: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> list[ConversationOut]:
    rows = conn.execute(
        """
        SELECT c.id, c.created_at,
               u.id AS partner_id, u.username AS partner_username, u.created_at AS partner_created_at,
               m.id AS last_id, m.conversation_id AS last_conversation_id,
               m.sender_id AS last_sender_id, m.content AS last_content, m.created_at AS last_created_at
        FROM conversations c
        JOIN conversation_participants me ON me.conversation_id = c.id AND me.user_id = ?
        JOIN conversation_participants other ON other.conversation_id = c.id AND other.user_id != ?
        JOIN users u ON u.id = other.user_id
        LEFT JOIN messages m ON m.id = (
            SELECT mm.id FROM messages mm WHERE mm.conversation_id = c.id ORDER BY mm.id DESC LIMIT 1
        )
        ORDER BY COALESCE(m.created_at, c.created_at) DESC
        """,
        (user["id"], user["id"]),
    ).fetchall()
    result: list[ConversationOut] = []
    for row in rows:
        last_message = None
        if row["last_id"] is not None:
            last_message = MessageOut(
                id=row["last_id"],
                conversation_id=row["last_conversation_id"],
                sender_id=row["last_sender_id"],
                content=row["last_content"],
                created_at=row["last_created_at"],
            )
        result.append(
            ConversationOut(
                id=row["id"],
                created_at=row["created_at"],
                partner=UserOut(
                    id=row["partner_id"],
                    username=row["partner_username"],
                    created_at=row["partner_created_at"],
                    is_online=manager.is_online(row["partner_id"]),
                ),
                last_message=last_message,
            )
        )
    return result


@router.post("/api/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: CreateConversationRequest,
    user: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> ConversationOut:
    other_id = payload.user_id
    if other_id == user["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot start a conversation with yourself",
        )
    other_user = conn.execute(
        "SELECT id, username, created_at FROM users WHERE id = ?", (other_id,)
    ).fetchone()
    if other_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = conn.execute(
        """
        SELECT c.id
        FROM conversations c
        JOIN conversation_participants a ON a.conversation_id = c.id AND a.user_id = ?
        JOIN conversation_participants b ON b.conversation_id = c.id AND b.user_id = ?
        """,
        (user["id"], other_id),
    ).fetchone()
    if existing is not None:
        return _conversation_out(conn, existing["id"], user["id"])

    cursor = conn.execute("INSERT INTO conversations (created_at) VALUES (?)", (utcnow(),))
    conversation_id = int(cursor.lastrowid)
    conn.executemany(
        "INSERT INTO conversation_participants (conversation_id, user_id) VALUES (?, ?)",
        [(conversation_id, user["id"]), (conversation_id, other_id)],
    )
    conn.commit()

    # Push the new conversation to the other participant so their sidebar updates.
    await manager.send_to_users(
        [other_id],
        {
            "type": "conversation",
            "conversation": _conversation_out(conn, conversation_id, other_id).model_dump(),
        },
    )
    return _conversation_out(conn, conversation_id, user["id"])


@router.get("/api/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: int,
    before_id: int | None = Query(default=None, ge=1),
    after_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    user: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> list[MessageOut]:
    _require_conversation(conn, conversation_id, user["id"])

    # Read cursors of both participants; a message is "read" when the
    # participant who did NOT send it has a cursor at or past its id.
    cursors = {
        row["user_id"]: row["last_read_message_id"]
        for row in conn.execute(
            "SELECT user_id, last_read_message_id FROM conversation_participants WHERE conversation_id = ?",
            (conversation_id,),
        )
    }

    def _to_message_out(row: sqlite3.Row) -> MessageOut:
        read_up_to = 0
        for participant_id, cursor in cursors.items():
            if participant_id != row["sender_id"]:
                read_up_to = cursor
                break
        return MessageOut(**dict(row), is_read=read_up_to >= row["id"])

    if after_id is not None:
        # Incremental fetch, used by the polling fallback.
        rows = conn.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE conversation_id = ? AND id > ? "
            "ORDER BY id ASC LIMIT ?",
            (conversation_id, after_id, limit),
        ).fetchall()
    elif before_id is not None:
        # Backwards pagination, used by "load earlier".
        rows = conn.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE conversation_id = ? AND id < ? "
            "ORDER BY id DESC LIMIT ?",
            (conversation_id, before_id, limit),
        ).fetchall()
        rows = list(reversed(rows))
    else:
        rows = conn.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        rows = list(reversed(rows))
    return [_to_message_out(row) for row in rows]


@router.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: int,
    payload: SendMessageRequest,
    user: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> MessageOut:
    _require_conversation(conn, conversation_id, user["id"])
    cursor = conn.execute(
        "INSERT INTO messages (conversation_id, sender_id, content, created_at) VALUES (?, ?, ?, ?)",
        (conversation_id, user["id"], payload.content, utcnow()),
    )
    conn.commit()
    row = conn.execute(
        f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    message = MessageOut(**dict(row))
    # Deliver live to every participant (including the sender's other tabs).
    participants = _participant_ids(conn, conversation_id)
    await manager.send_to_users(
        participants,
        {"type": "message", "conversation_id": conversation_id, "message": message.model_dump()},
    )
    return message


@router.post("/api/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_conversation_read(
    conversation_id: int,
    user: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> None:
    """Record that the caller has read up to the newest message in the conversation."""
    _require_conversation(conn, conversation_id, user["id"])
    latest = conn.execute(
        "SELECT MAX(id) AS latest_id FROM messages WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()["latest_id"]
    if latest is None:
        return  # nothing to read yet
    current = conn.execute(
        "SELECT last_read_message_id FROM conversation_participants WHERE conversation_id = ? AND user_id = ?",
        (conversation_id, user["id"]),
    ).fetchone()["last_read_message_id"]
    if latest <= current:
        return  # nothing new since the last read

    conn.execute(
        "UPDATE conversation_participants SET last_read_message_id = ? WHERE conversation_id = ? AND user_id = ?",
        (latest, conversation_id, user["id"]),
    )
    conn.commit()

    participants = _participant_ids(conn, conversation_id)
    await manager.send_to_users(
        participants,
        {
            "type": "read",
            "conversation_id": conversation_id,
            "reader_id": user["id"],
            "last_read_message_id": latest,
        },
    )


@router.delete("/api/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    user: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> None:
    """Permanently delete the conversation and all of its messages.

    Deletion affects every participant; starting a chat with the same person
    again creates a brand-new, empty conversation.
    """
    _require_conversation(conn, conversation_id, user["id"])
    participants = _participant_ids(conn, conversation_id)
    # Foreign-key cascades remove the participants and messages with it.
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
    # Tell every participant's open tabs that the conversation is gone.
    await manager.send_to_users(
        participants, {"type": "conversation_removed", "conversation_id": conversation_id}
    )
