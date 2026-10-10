"""End-to-end API tests running against the FastAPI app with a temporary SQLite database."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

PASSWORD = "password123"


@pytest.fixture()
def client(tmp_path):
    from app.main import create_app

    app = create_app(db_path=str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, username: str, password: str = PASSWORD) -> dict:
    response = client.post("/api/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def next_event(websocket, expected_type: str, predicate=None, limit: int = 10) -> dict:
    """Receive WebSocket events until one matches the expected type/predicate."""
    for _ in range(limit):
        event = websocket.receive_json()
        if event.get("type") == expected_type and (predicate is None or predicate(event)):
            return event
    raise AssertionError(f"expected a '{expected_type}' websocket event")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_register_login_and_session_lifecycle(client):
    created = register(client, "alice")
    assert created["user"]["username"] == "alice"
    assert created["token"]

    # Wrong password is rejected without revealing why.
    response = client.post("/api/auth/login", json={"username": "alice", "password": "not-my-password"})
    assert response.status_code == 401

    # Login is case-insensitive.
    response = client.post("/api/auth/login", json={"username": "ALICE", "password": PASSWORD})
    assert response.status_code == 200
    token = response.json()["token"]

    # The session works and /me identifies the user.
    response = client.get("/api/users/me", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["username"] == "alice"

    # Unknown usernames fail too.
    response = client.post("/api/auth/login", json={"username": "ghost", "password": PASSWORD})
    assert response.status_code == 401

    # Usernames are unique regardless of case.
    response = client.post("/api/auth/register", json={"username": "Alice", "password": PASSWORD})
    assert response.status_code == 409

    # Logout invalidates the token.
    response = client.post("/api/auth/logout", headers=auth(token))
    assert response.status_code == 204
    response = client.get("/api/users/me", headers=auth(token))
    assert response.status_code == 401

    # Missing or bogus tokens are rejected.
    assert client.get("/api/users").status_code == 401
    assert client.get("/api/users", headers=auth("made-up-token")).status_code == 401


def test_registration_validation(client):
    cases = [
        {"username": "ab", "password": PASSWORD},  # username too short
        {"username": "x" * 33, "password": PASSWORD},  # username too long
        {"username": "bad name!", "password": PASSWORD},  # illegal characters
        {"username": "validname", "password": "short"},  # password too short
    ]
    for case in cases:
        response = client.post("/api/auth/register", json=case)
        assert response.status_code == 422, case


# ---------------------------------------------------------------------------
# Users, conversations, messages, permissions
# ---------------------------------------------------------------------------


def test_conversations_messages_and_permissions(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    carol = register(client, "carol")

    # The directory lists everyone but me, sorted alphabetically.
    response = client.get("/api/users", headers=auth(alice["token"]))
    assert [u["username"] for u in response.json()] == ["bob", "carol"]

    # Starting a chat is idempotent.
    response = client.post(
        "/api/conversations", json={"user_id": bob["user"]["id"]}, headers=auth(alice["token"])
    )
    assert response.status_code == 201
    conversation = response.json()
    assert conversation["partner"]["username"] == "bob"
    again = client.post(
        "/api/conversations", json={"user_id": bob["user"]["id"]}, headers=auth(alice["token"])
    )
    assert again.json()["id"] == conversation["id"]
    conversation_id = conversation["id"]

    # Both participants see the conversation in their sidebar.
    response = client.get("/api/conversations", headers=auth(bob["token"]))
    assert [c["id"] for c in response.json()] == [conversation_id]

    # Sending stores a trimmed message and returns it.
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "  hello bob  "},
        headers=auth(alice["token"]),
    )
    assert response.status_code == 201
    first = response.json()
    assert first["content"] == "hello bob"
    assert first["sender_id"] == alice["user"]["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "hi alice"},
        headers=auth(bob["token"]),
    )
    second = response.json()

    # History is chronological and includes timestamps.
    response = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=auth(alice["token"])
    )
    messages = response.json()
    assert [m["id"] for m in messages] == [first["id"], second["id"]]
    assert messages[0]["created_at"] <= messages[1]["created_at"]

    # Incremental fetch (used by the polling fallback).
    response = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"after_id": first["id"]},
        headers=auth(alice["token"]),
    )
    assert [m["id"] for m in response.json()] == [second["id"]]

    # Backwards pagination (used by "load earlier").
    response = client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"before_id": second["id"]},
        headers=auth(alice["token"]),
    )
    assert [m["id"] for m in response.json()] == [first["id"]]

    # The sidebar preview shows the newest message.
    response = client.get("/api/conversations", headers=auth(alice["token"]))
    assert response.json()[0]["last_message"]["id"] == second["id"]

    # Outsiders can neither read nor post in the conversation.
    response = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=auth(carol["token"])
    )
    assert response.status_code == 403
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "let me in"},
        headers=auth(carol["token"]),
    )
    assert response.status_code == 403
    response = client.get("/api/conversations", headers=auth(carol["token"]))
    assert response.json() == []

    # Invalid payloads and targets are rejected.
    assert (
        client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "   "},
            headers=auth(alice["token"]),
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "x" * 4001},
            headers=auth(alice["token"]),
        ).status_code
        == 422
    )
    assert client.get("/api/conversations/999999/messages", headers=auth(alice["token"])).status_code == 404
    assert (
        client.post("/api/conversations", json={"user_id": alice["user"]["id"]}, headers=auth(alice["token"])).status_code
        == 400
    )
    assert client.post("/api/conversations", json={"user_id": 999999}, headers=auth(alice["token"])).status_code == 404


def test_messages_persist_across_restart(tmp_path):
    from app.main import create_app

    db_path = str(tmp_path / "messenger.db")
    app = create_app(db_path=db_path)
    with TestClient(app) as first_client:
        alice = register(first_client, "alice")
        bob = register(first_client, "bob")
        conversation = first_client.post(
            "/api/conversations", json={"user_id": bob["user"]["id"]}, headers=auth(alice["token"])
        ).json()
        first_client.post(
            f"/api/conversations/{conversation['id']}/messages",
            json={"content": "still there?"},
            headers=auth(alice["token"]),
        )

    # Simulate a restart by rebuilding the app on the same database file.
    restarted = create_app(db_path=db_path)
    with TestClient(restarted) as second_client:
        response = second_client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
        assert response.status_code == 200
        token = response.json()["token"]
        messages = second_client.get(
            f"/api/conversations/{conversation['id']}/messages", headers=auth(token)
        ).json()
        assert len(messages) == 1
        assert messages[0]["content"] == "still there?"


def test_schema_migrations(tmp_path):
    """Databases from earlier app versions are upgraded at startup."""
    import sqlite3

    from app.db import connect, init_db

    db_path = str(tmp_path / "old.db")
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL
        );
        -- v1.1 schema: the participants table carried a `hidden` flag that
        -- v1.2 removed in favour of full conversation deletion.
        CREATE TABLE conversation_participants (
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            hidden INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (conversation_id, user_id)
        );
        INSERT INTO conversations (created_at) VALUES ('2026-01-01T00:00:00+00:00');
        INSERT INTO conversation_participants VALUES (1, 1, 0);
        """
    )
    legacy.commit()
    legacy.close()

    init_db(db_path)  # runs at every server startup

    conn = connect(db_path)
    try:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(conversation_participants)")]
        # hidden dropped, read cursor added, data preserved
        assert columns == ["conversation_id", "user_id", "last_read_message_id"]
        row = conn.execute("SELECT * FROM conversation_participants WHERE conversation_id = 1").fetchone()
        assert tuple(row) == (1, 1, 0)
    finally:
        conn.close()


def test_delete_conversation(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    carol = register(client, "carol")

    conversation_id = client.post(
        "/api/conversations", json={"user_id": bob["user"]["id"]}, headers=auth(alice["token"])
    ).json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "hello"},
        headers=auth(alice["token"]),
    )

    # Alice deletes the conversation; it is gone for both participants.
    response = client.delete(f"/api/conversations/{conversation_id}", headers=auth(alice["token"]))
    assert response.status_code == 204
    assert client.get("/api/conversations", headers=auth(alice["token"])).json() == []
    assert client.get("/api/conversations", headers=auth(bob["token"])).json() == []

    # The conversation and its messages no longer exist.
    assert (
        client.get(f"/api/conversations/{conversation_id}/messages", headers=auth(alice["token"])).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "zombie message"},
            headers=auth(alice["token"]),
        ).status_code
        == 404
    )

    # Deleting the conversation also removed its messages from the database.
    fresh_conversation_id = client.post(
        "/api/conversations", json={"user_id": bob["user"]["id"]}, headers=auth(alice["token"])
    ).json()["id"]
    assert fresh_conversation_id != conversation_id  # a brand-new conversation

    # Outsiders cannot delete conversations they are not part of.
    assert (
        client.delete(
            f"/api/conversations/{fresh_conversation_id}", headers=auth(carol["token"])
        ).status_code
        == 403
    )
    assert client.delete("/api/conversations/999999", headers=auth(alice["token"])).status_code == 404

    fresh = client.get(
        f"/api/conversations/{fresh_conversation_id}/messages", headers=auth(bob["token"])
    ).json()
    assert fresh == []  # empty history: the old messages are gone for good


def test_websocket_conversation_deleted_event(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    conversation_id = client.post(
        "/api/conversations", json={"user_id": bob["user"]["id"]}, headers=auth(alice["token"])
    ).json()["id"]

    # Both participants are told when the conversation is deleted.
    with client.websocket_connect(f"/api/ws?token={alice['token']}") as alice_ws:
        with client.websocket_connect(f"/api/ws?token={bob['token']}") as bob_ws:
            alice_ws.receive_json()  # bob comes online
            response = client.delete(f"/api/conversations/{conversation_id}", headers=auth(alice["token"]))
            assert response.status_code == 204
            event = next_event(alice_ws, "conversation_removed")
            assert event["conversation_id"] == conversation_id
            event = next_event(bob_ws, "conversation_removed")
            assert event["conversation_id"] == conversation_id



def test_read_receipts(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    carol = register(client, "carol")
    conversation_id = client.post(
        "/api/conversations", json={"user_id": bob["user"]["id"]}, headers=auth(alice["token"])
    ).json()["id"]

    first = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "hello?"},
        headers=auth(alice["token"]),
    ).json()
    second = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "you there?"},
        headers=auth(alice["token"]),
    ).json()

    # Nobody has read anything yet.
    history = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=auth(alice["token"])
    ).json()
    assert [m["is_read"] for m in history] == [False, False]

    # Bob opens the conversation and marks it read.
    response = client.post(f"/api/conversations/{conversation_id}/read", headers=auth(bob["token"]))
    assert response.status_code == 204
    history = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=auth(alice["token"])
    ).json()
    assert [m["is_read"] for m in history] == [True, True]

    # Bob replies; his own message starts unread.
    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "hi alice"},
        headers=auth(bob["token"]),
    )
    history = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=auth(bob["token"])
    ).json()
    assert [m["is_read"] for m in history] == [True, True, False]

    # Re-marking with nothing new is a no-op that still returns 204.
    response = client.post(f"/api/conversations/{conversation_id}/read", headers=auth(bob["token"]))
    assert response.status_code == 204

    # Alice reads the reply.
    response = client.post(f"/api/conversations/{conversation_id}/read", headers=auth(alice["token"]))
    assert response.status_code == 204
    history = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=auth(bob["token"])
    ).json()
    assert [m["is_read"] for m in history] == [True, True, True]

    # Outsiders cannot mark a conversation read, and missing ones 404.
    assert (
        client.post(
            f"/api/conversations/{conversation_id}/read", headers=auth(carol["token"])
        ).status_code
        == 403
    )
    assert client.post("/api/conversations/999999/read", headers=auth(alice["token"])).status_code == 404

    # An empty conversation can be "read" harmlessly.
    empty_id = client.post(
        "/api/conversations", json={"user_id": carol["user"]["id"]}, headers=auth(alice["token"])
    ).json()["id"]
    assert client.post(f"/api/conversations/{empty_id}/read", headers=auth(alice["token"])).status_code == 204


def test_websocket_read_event(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    conversation_id = client.post(
        "/api/conversations", json={"user_id": bob["user"]["id"]}, headers=auth(alice["token"])
    ).json()["id"]

    with client.websocket_connect(f"/api/ws?token={alice['token']}") as alice_ws:
        with client.websocket_connect(f"/api/ws?token={bob['token']}") as bob_ws:
            alice_ws.receive_json()  # bob comes online

            first = client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"content": "seen this?"},
                headers=auth(alice["token"]),
            ).json()
            second = client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"content": "and this?"},
                headers=auth(alice["token"]),
            ).json()

            # Bob reads the conversation; Alice is told instantly.
            response = client.post(
                f"/api/conversations/{conversation_id}/read", headers=auth(bob["token"])
            )
            assert response.status_code == 204
            event = next_event(alice_ws, "read")
            assert event["conversation_id"] == conversation_id
            assert event["reader_id"] == bob["user"]["id"]
            assert event["last_read_message_id"] == second["id"]

            # Re-reading with nothing new must not emit another event; Alice's
            # next event is Bob replying, proving the no-op stayed silent.
            client.post(f"/api/conversations/{conversation_id}/read", headers=auth(bob["token"]))
            reply = client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"content": "yep, read both"},
                headers=auth(bob["token"]),
            ).json()
            event = next_event(alice_ws, "message")
            assert event["message"]["id"] == reply["id"]


# ---------------------------------------------------------------------------
# WebSockets
# ---------------------------------------------------------------------------


def test_websocket_delivery_and_presence(client):
    alice = register(client, "alice")
    bob = register(client, "bob")

    with client.websocket_connect(f"/api/ws?token={alice['token']}") as alice_ws:
        with client.websocket_connect(f"/api/ws?token={bob['token']}"):
            # Alice sees Bob coming online.
            event = alice_ws.receive_json()
            assert event == {"type": "presence", "user_id": bob["user"]["id"], "online": True}

            # A conversation started by Bob appears instantly in Alice's sidebar.
            conversation = client.post(
                "/api/conversations",
                json={"user_id": alice["user"]["id"]},
                headers=auth(bob["token"]),
            ).json()
            event = next_event(alice_ws, "conversation")
            assert event["conversation"]["id"] == conversation["id"]
            assert event["conversation"]["partner"]["username"] == "bob"

            # Messages sent by Bob arrive live for Alice.
            sent = client.post(
                f"/api/conversations/{conversation['id']}/messages",
                json={"content": "real time!"},
                headers=auth(bob["token"]),
            ).json()
            event = next_event(alice_ws, "message")
            assert event["conversation_id"] == conversation["id"]
            assert event["message"]["id"] == sent["id"]
            assert event["message"]["content"] == "real time!"

        # When Bob disconnects, Alice is told he went offline.
        event = next_event(alice_ws, "presence", predicate=lambda e: e["online"] is False)
        assert event["user_id"] == bob["user"]["id"]


def test_websocket_rejects_bad_tokens(client):
    register(client, "alice")
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/api/ws?token=not-a-real-token") as websocket:
            websocket.receive_json()
    assert excinfo.value.code == 4401
