# Messain

**A simple, modern, real-time messaging app — FastAPI + SQLite + WebSockets on the backend, React + TypeScript + Tailwind on the frontend, dark theme by default.**

Messain is a complete, working chat application built from scratch: register an account, see
who's online, start 1:1 conversations, and exchange messages that arrive live — with read
receipts, permanent deletion, and history that survives restarts. It runs entirely on your
machine with one or two commands.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB) ![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688) ![React](https://img.shields.io/badge/React_19-frontend-61DAFB) ![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6) ![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57) ![License](https://img.shields.io/badge/License-Messain_Custom-4f46e5)

## Table of contents

- [Features](#features)
- [The interface](#the-interface)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Database schema](#database-schema)
- [Real-time protocol](#real-time-protocol)
- [How messages, receipts and deletion work](#how-messages-receipts-and-deletion-work)
- [API reference](#api-reference)
- [Security](#security)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Design decisions & limits](#design-decisions--limits)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Features

| Feature | Details |
| --- | --- |
| **Accounts** | Register / log in with username + password. Usernames are unique (case-insensitive), 3–32 chars, letters/digits/`._-`. Passwords 8–128 chars, hashed with PBKDF2-HMAC-SHA256 (600k iterations, 16-byte random salt) — plaintext is never stored or logged. |
| **Sessions** | Opaque random tokens (43 chars, `secrets.token_urlsafe`), stored server-side with an expiry (30 days by default). Logout invalidates the token immediately. |
| **User directory** | Everyone registered appears under **People** with a live online/offline dot. New users appear in open clients instantly. |
| **Conversations** | Click any person to start a 1:1 chat (find-or-create: clicking again returns the same conversation). The other side's sidebar updates the moment a chat is created. |
| **Real-time messaging** | Messages are pushed over a WebSocket — no refreshing. If the socket drops, the client shows an offline banner, polls every 3 s, and reconnects with exponential backoff (1 s → 10 s cap). |
| **Message history** | Everything is stored in SQLite. Reopening a conversation reloads it; "Load earlier messages" pages back through history (50 per page) without losing your scroll position. |
| **Read receipts** | Your sent messages show a ✓ that flips to **✓✓ Read** (blue) the instant the other person opens the conversation. Works live and after reloads. |
| **Delete conversations** | The trash icon permanently deletes the chat **and every message in it, for both participants**. Starting a chat with the same person again creates a fresh, empty conversation. |
| **Presence** | Online = has an active WebSocket (multiple tabs count once). Going offline is broadcast to the people who need it. |
| **Timestamps** | Every bubble shows its time; days are grouped under separators (Today / Yesterday / weekday). |
| **Dark, responsive UI** | Discord/WhatsApp-inspired layout. Two panes on desktop, single-pane with a back button on mobile. Skeleton loaders, empty states, and dismissible error banners everywhere. |

## The interface

- **Sidebar**
  - *Messages* — your conversations, most recent activity first, with partner avatar, online dot, last-message preview, and relative time.
  - *People* — registered users you don't have a chat with yet (click to start one).
  - *Bottom bar* — your avatar and username, plus **Log out**.
  - *Top bar* — app logo and a **Live** indicator (green when the WebSocket is connected).
- **Chat pane**
  - Header with partner avatar, name, and Online/Offline status (back button on mobile).
  - Message bubbles — yours in indigo on the right, others in slate on the left — with times, day separators, and read receipts on your own messages.
  - Composer — auto-growing textarea; **Enter** sends, **Shift+Enter** is a newline.
- **Auth screen** — tabbed Sign in / Register card with inline validation and server error messages.
- **Banners** — a red dismissible error banner and an amber "connection lost — polling" banner under the header.

## Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | Python 3.11+ / FastAPI | Typed routes, built-in validation via Pydantic, native WebSocket support |
| Server | uvicorn (`uvicorn[standard]`) | ASGI, automatic WebSocket keep-alive pings |
| Database | SQLite via stdlib `sqlite3`, WAL mode | Zero setup, single file, safe concurrent reads; no ORM needed at this scale |
| Realtime | FastAPI WebSockets + polling fallback | Live delivery, graceful degradation when the socket is down |
| Auth | Random bearer tokens in the DB | No JWT signing keys to manage; instant revocation on logout |
| Frontend | React 19, Vite 7, TypeScript (strict) | Fast dev server, type safety end to end |
| Styling | Tailwind CSS v4 | Utility classes keep styling local and consistent |
| Tests | pytest + FastAPI TestClient (+ httpx) | Full-stack API tests over a temporary database |

## Architecture

```text
Browser — React SPA (TypeScript, Tailwind)
   │
   │  REST: fetch /api/...          WebSocket: /api/ws?token=...
   ▼
┌──────────────────────────────────────────────────────────┐
│ FastAPI (uvicorn, port 8000)                             │
│                                                          │
│  auth.py        users.py        conversations.py         │
│  register/login directory       chats/messages/receipts  │
│         │                              │                 │
│         ▼                              ▼                 │
│  ┌─────────────┐              ┌──────────────────┐       │
│  │ SQLite (WAL) │◄─────────────│ presence.py      │       │
│  │ data/       │  read/write  │ in-memory socket │       │
│  │ messenger.db│              │ registry + push  │       │
│  └─────────────┘              └──────────────────┘       │
│         ▲                                                │
│         │ serves frontend/dist (production mode)         │
└─────────┼────────────────────────────────────────────────┘
          │
   Vite dev server (port 5173) proxies /api — including the
   WebSocket upgrade — to port 8000 during development.
```

**One request, one connection.** Every HTTP request opens a short-lived SQLite connection
(WAL allows concurrent readers; a 30 s busy timeout handles write contention). Each
WebSocket is registered in an in-memory map of `user_id → set of sockets`, which supports
multiple tabs per user and drives both presence and event delivery.

**Sending a message.** The client POSTs to `/messages`; the server validates, writes to
SQLite, then pushes a `message` event to every participant's sockets (including the
sender's other tabs). Clients merge by message id, so REST + WS delivery never duplicates.

**Resilience.** If the WebSocket dies, the client enters polling mode (3 s interval),
fetching conversation lists and any messages newer than the last one it has. When the
socket reconnects, the client refetches the open conversation to catch anything the poll
window missed.

## Getting started

### Prerequisites

- [Python](https://www.python.org/downloads/) 3.11 or newer
- [Node.js](https://nodejs.org/) 20 or newer

### Install (first time)

```powershell
python -m venv .venv
& .venv\Scripts\pip install -r requirements.txt
cd frontend
npm install
cd ..
```

Bash: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then `cd frontend && npm install`.

### Run — development (two terminals)

**Terminal 1 — backend** (hot reload on Python changes):

```powershell
& .venv\Scripts\python -m uvicorn app.main:app --reload
```

**Terminal 2 — frontend** (hot reload on TS/TSX/CSS changes):

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173**. The Vite server proxies `/api` (REST and WebSocket) to
port 8000, so both parts behave as one origin.

### Run — production style (one server)

Build the frontend once; uvicorn then serves API + UI from a single process:

```powershell
cd frontend
npm run build
cd ..
& .venv\Scripts\python -m uvicorn app.main:app
```

Open **http://127.0.0.1:8000**. Rebuild (`npm run build`) after changing frontend code.

### Try it in 60 seconds

1. Register `alice` (`password123` will do).
2. Open an incognito window (same-browser tabs share one login) and register `bob`.
3. In Alice's window click **bob** under *People*, send a message.
4. It appears instantly in Bob's window; watch your bubble's ✓ flip to **✓✓ Read** when Bob opens the chat.
5. Hover a conversation and click the **trash icon** — the chat and its messages vanish for both of you.
6. Stop both servers (`Ctrl+C`), start them again, log back in — everything is still there.

## Configuration

Messain reads environment variables, optionally from a `.env` file in the project root
(copy [`.env.example`](.env.example)). No secrets are required — tokens are random values
generated at runtime.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MESSAIN_DATABASE` | `data/messenger.db` | SQLite database file path (parent folders are created) |
| `MESSAIN_TOKEN_EXPIRE_DAYS` | `30` | Days before a login token expires |

**Reset all data:** stop the server and delete the `data` folder (the `.db`, plus its `-wal`/`-shm` siblings).

## Database schema

Five tables, all with foreign keys enabled (`PRAGMA foreign_keys = ON`) and WAL journaling.

```text
users                              one row per account
├── id                INTEGER PK AUTOINCREMENT
├── username          TEXT NOT NULL UNIQUE COLLATE NOCASE   ← case-insensitive uniqueness
├── password_hash     TEXT NOT NULL                        ← pbkdf2_sha256$iter$salt$digest
└── created_at        TEXT NOT NULL                        ← UTC ISO-8601

auth_tokens                        one row per active session
├── token             TEXT PK                          ← random 43-char urlsafe string
├── user_id           INTEGER → users.id CASCADE
├── created_at        TEXT NOT NULL
└── expires_at        TEXT NOT NULL                        ← compared lexicographically (fixed format)

conversations                      one row per 1:1 chat
├── id                INTEGER PK AUTOINCREMENT
└── created_at        TEXT NOT NULL

conversation_participants          membership + read state
├── conversation_id        INTEGER → conversations.id CASCADE   ┐ composite PK
├── user_id               INTEGER → users.id CASCADE           ┘
└── last_read_message_id   INTEGER NOT NULL DEFAULT 0            ← read-receipt cursor

messages                           one row per message
├── id               INTEGER PK AUTOINCREMENT
├── conversation_id  INTEGER → conversations.id CASCADE   ← deleting a chat cascades
├── sender_id        INTEGER → users.id CASCADE
├── content          TEXT NOT NULL CHECK (length(trim(content)) > 0)
└── created_at       TEXT NOT NULL
```

Indexes: `auth_tokens(user_id)`, `conversation_participants(user_id)`,
`messages(conversation_id, id)` — the last one serves both history pagination and the
"latest message" sidebar lookup.

Old databases are upgraded automatically at startup (`app/db.py → _apply_migrations`),
e.g. dropping the v1.1 `hidden` column and adding the v1.3 read cursor.

## Real-time protocol

**Connect:** `GET /api/ws?token=<token>` (browsers can't set headers on WebSockets, so the
token rides in the query string). Unknown/expired tokens: the socket is accepted, then
closed with code **`4401`** — the client treats that as fatal and returns to the login
screen instead of retrying.

**Server → client events:**

| Event | Payload | When |
| --- | --- | --- |
| `message` | `{conversation_id, message}` | A participant sent a message (delivered to all participants, all tabs) |
| `presence` | `{user_id, online}` | Someone connected or disconnected (their last socket closing = offline) |
| `conversation` | `{conversation}` | Someone started a chat with you |
| `conversation_removed` | `{conversation_id}` | The chat was permanently deleted |
| `read` | `{conversation_id, reader_id, last_read_message_id}` | The other person read up to a message |
| `user` | `{user}` | A new account was registered |

```jsonc
// examples
{ "type": "message",  "conversation_id": 5, "message": { "id": 42, "conversation_id": 5, "sender_id": 2, "content": "hi", "created_at": "2026-10-11T09:30:00.123456+00:00", "is_read": false } }
{ "type": "presence", "user_id": 3, "online": true }
{ "type": "read", "conversation_id": 5, "reader_id": 3, "last_read_message_id": 42 }
```

**Client behavior:** messages are merged by id (dedupe across REST + WS); `read` events
only flip the sender's own bubbles; a `4401` close logs you out; any other close triggers
reconnect with exponential backoff (1 s → 10 s) plus 3-second polling while offline.

## How messages, receipts and deletion work

**Message lifecycle.** `POST /messages` trims the content, validates length (1–4000),
inserts one row, commits, then broadcasts. History is served ascending by id, so ordering
is always chronological; pagination uses `before_id` (older) / `after_id` (newer, used by
polling).

**Read receipts.** Each participant row stores `last_read_message_id` — a cursor. Opening a
conversation (or receiving a message while it's open) makes the client `POST /read`, which
advances the cursor to the newest message id and pushes a `read` event. A message's
`is_read` is computed as *the participant who didn't send it has a cursor ≥ its id* — so
both people see "Read" on their own sent bubbles, consistently, from any view. Re-reading
with nothing new is a no-op (no event spam).

**Deletion.** `DELETE /api/conversations/{id}` removes the conversation row; cascades wipe
participants and messages. All former participants get `conversation_removed` and their UI
drops the chat immediately — even if it's open. A new chat with the same person gets a new
conversation id and empty history. There is no undo, by design.

## API reference

Base URL: `http://127.0.0.1:8000` · All authenticated routes expect
`Authorization: Bearer <token>`. Errors are JSON `{"detail": "..."}`; validation errors
return 422 with a field breakdown.

| Method | Path | Auth | Description | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/auth/register` | — | Create account → `{token, user}` | 201 |
| `POST` | `/api/auth/login` | — | Log in (case-insensitive username) → `{token, user}` | 200 |
| `POST` | `/api/auth/logout` | ✓ | Invalidate the current token | 204 |
| `GET` | `/api/users/me` | ✓ | Current user | 200 |
| `GET` | `/api/users` | ✓ | All other users + online status, alphabetical | 200 |
| `GET` | `/api/conversations` | ✓ | Your chats, most recent activity first, each with partner + last message | 200 |
| `POST` | `/api/conversations` | ✓ | `{user_id}` — find-or-create a chat | 201 |
| `DELETE` | `/api/conversations/{id}` | ✓ | Permanently delete chat + messages (both sides) | 204 |
| `GET` | `/api/conversations/{id}/messages` | ✓ | History; params `before_id`, `after_id`, `limit` (1–200, default 50) | 200 |
| `POST` | `/api/conversations/{id}/messages` | ✓ | `{content}` → message object | 201 |
| `POST` | `/api/conversations/{id}/read` | ✓ | Advance your read cursor; no-op if nothing new | 204 |
| `WS` | `/api/ws?token=...` | ✓ | Live event stream | — |
| `GET` | `/api/health` | — | Liveness probe → `{"status":"ok"}` | 200 |

Status codes worth knowing: **401** missing/invalid token · **403** not a participant ·
**404** conversation doesn't exist · **409** username taken · **422** invalid input.

Example session:

```bash
# register
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "password123"}'
# → {"token": "Q8f...", "user": {"id": 1, "username": "alice", ...}}

# send a message
curl -X POST http://127.0.0.1:8000/api/conversations/1/messages \
  -H "Authorization: Bearer Q8f..." \
  -H "Content-Type: application/json" \
  -d '{"content": "hello bob"}'
# → {"id": 1, "conversation_id": 1, "sender_id": 1, "content": "hello bob",
#    "created_at": "2026-10-11T09:30:00.123456+00:00", "is_read": false}
```

## Security

- **Passwords** — PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte per-user salt,
  constant-time comparison (`hmac.compare_digest`). Verification against a precomputed
  dummy hash equalizes response time for unknown usernames (no account enumeration).
- **SQL** — every query is parameterized; user input never touches SQL text. Foreign keys
  and CHECK constraints enforce integrity at the database layer.
- **Authorization** — every conversation route verifies participation first (403 for
  outsiders, 404 for missing chats). Validation happens server-side (Pydantic), not just
  in the UI.
- **WebSockets** — authenticated with the same token store; invalid tokens are closed with
  4401. Events are only ever sent to participants of the affected conversation (presence
  is limited to what the user directory already shows).
- **Tokens** — random 256-bit values, stored server-side with expiry, deleted on logout,
  never written to logs. The client keeps its token in `localStorage`.
- **Secrets** — none required; optional behavior is configured via environment variables
  (`.env` is git-ignored).

## Testing

```powershell
& .venv\Scripts\pip install -r requirements-dev.txt
& .venv\Scripts\python -m pytest -q
```

12 tests run against a temporary SQLite database per test (nothing touches your real
`data/` folder). Coverage includes:

- Registration, login (case-insensitive), logout, token expiry, bad-credential handling
- Input validation (username/password/message length + charset, empty messages)
- Messaging: send, chronological history, forward/backward pagination, sidebar previews
- Access control: outsiders get 403 on read/write/delete; missing conversations 404
- Read receipts: cursor flow, no-op re-reads, per-view `is_read`
- Deletion: gone for both sides, 404 afterwards, fresh conversation on re-create
- WebSockets: live message delivery, presence on/offline, conversation + read + removal
  events, 4401 auth rejection
- Persistence: messages survive a simulated server restart
- Migrations: a v1.1 database is upgraded in place (column dropped, cursor added)

## Project structure

```text
├── app/                        # FastAPI backend package
│   ├── main.py                 # App factory, lifespan DB init, serves frontend/dist
│   ├── config.py               # Env-var settings (dotenv)
│   ├── db.py                   # Schema, migrations, connection factory, request dependency
│   ├── security.py             # PBKDF2 hashing, token generation, timing equalization
│   ├── auth.py                 # Register/login/logout, token→user dependency
│   ├── users.py                # Directory + /users/me
│   ├── conversations.py        # Chats, messages, read receipts, deletion
│   ├── presence.py             # ConnectionManager: user → live sockets, event fan-out
│   ├── ws.py                   # /api/ws endpoint: auth, receive loop, presence broadcast
│   └── schemas.py              # Pydantic request/response models + validation
├── frontend/                   # React + Vite + TypeScript + Tailwind CSS v4
│   ├── index.html              # SPA entry, dark background to avoid flashes
│   ├── vite.config.ts          # React + Tailwind plugins, /api proxy (incl. WebSocket)
│   └── src/
│       ├── App.tsx             # Session bootstrap: validate stored token → auth/chat
│       ├── api.ts              # Typed fetch client, ApiError, token storage helpers
│       ├── types.ts            # Shared User/Message/Conversation/WsEvent types
│       ├── time.ts             # Time, relative-time and day-label formatting
│       └── components/
│           ├── AuthScreen.tsx      # Sign in / register card
│           ├── ChatApp.tsx         # Root state: data, WebSocket, polling, actions
│           ├── Sidebar.tsx         # Conversations + People + profile/logout
│           ├── ChatWindow.tsx      # Header + EmptyChat export
│           ├── MessageList.tsx     # Bubbles, day separators, receipts, pagination
│           ├── MessageInput.tsx    # Auto-growing composer
│           ├── Avatar.tsx          # Initials + online dot
│           ├── Banner.tsx          # Error + offline banners
│           └── Icons.tsx           # Inline SVG icon set
├── tests/test_app.py           # 12-test pytest suite
├── conftest.py                 # Makes the project root importable for pytest
├── .env.example                # Documented environment variables
├── requirements.txt            # fastapi, uvicorn[standard], python-dotenv
├── requirements-dev.txt        # + pytest, httpx
└── LICENSE                     # The Messain Custom License
```

## Design decisions & limits

**Chosen for simplicity, on purpose:**

- **SQLite, not Postgres** — a chat server for a team of friends doesn't need a database
  server; WAL gives safe concurrent reads and the whole state is one file you can back up
  by copying.
- **No ORM** — the queries are few and explicit; parameterized stdlib `sqlite3` is easier
  to audit.
- **Opaque tokens, not JWT** — revocation on logout is instant and there's no signing key
  to leak.
- **Single process** — presence and event fan-out live in memory. Don't scale to multiple
  instances without moving that state to Redis or similar.

**Current limits (by design, per scope):**

- 1:1 conversations only (the participants table would generalize to groups)
- No message editing or undelete
- No push notifications; "online" means "has the app open"
- Registration is open — appropriate for a trusted/local deployment
- Frontend token in `localStorage` (standard trade-off; fine for local use)

## Troubleshooting

| Problem | Cause | Fix |
| --- | --- | --- |
| `WinError 10013` / `10048` on startup | Port 8000 already in use | `Get-NetTCPConnection -LocalPort 8000 -State Listen \| ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }` |
| "Cannot reach the server" banner | Backend not running | Start terminal 1 first; check `http://127.0.0.1:8000/api/health` |
| Port 8000 shows an old UI | `frontend/dist` is stale (production mode) | `cd frontend; npm run build` |
| Port 5173 blank / proxy errors | Vite not running, or backend down | Start both terminals; Vite proxies to 8000 |
| Stuck loading after login | Token expired or DB reset | Log in again; a 401 clears the stale session automatically |
| Want to start fresh | — | Stop servers, delete the `data` folder |
| `npm install` fails on Windows | Node < 20 | Upgrade Node.js, then `cd frontend && npm install` again |
| Tests fail with import errors | Wrong interpreter | Use `& .venv\Scripts\python -m pytest -q` from the project root |

## License

Released under the custom **[Messain Custom License](LICENSE)** — in short: free to use,
run, study, modify, and share for personal, educational, and non-commercial purposes; no
commercial redistribution; keep the copyright and license notice intact. For commercial
licensing, contact the copyright holder.
