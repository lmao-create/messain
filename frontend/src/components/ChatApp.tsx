import { useCallback, useEffect, useRef, useState } from 'react'
import type { Conversation, Message, User, WsEvent, WsStatus } from '../types'
import { api } from '../api'
import Sidebar from './Sidebar'
import ChatWindow from './ChatWindow'
import { EmptyChat } from './ChatWindow'
import { ConnectionBanner, ErrorBanner } from './Banner'

interface ChatAppProps {
  token: string
  me: User
  onLogout: () => void
}

const PAGE_SIZE = 50

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong'
}

function activityKey(conversation: Conversation): string {
  return conversation.last_message?.created_at ?? conversation.created_at
}

/** Merge message lists, dropping duplicates by id and keeping chronological order. */
function mergeUnique(previous: Message[], incoming: Message[]): Message[] {
  const seen = new Set(previous.map((message) => message.id))
  const merged = [...previous]
  for (const message of incoming) {
    if (!seen.has(message.id)) {
      merged.push(message)
      seen.add(message.id)
    }
  }
  return merged.sort((a, b) => a.id - b.id)
}

export default function ChatApp({ token, me, onLogout }: ChatAppProps) {
  const [conversations, setConversations] = useState<Conversation[] | null>(null)
  const [users, setUsers] = useState<User[] | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[] | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting')
  const [banner, setBanner] = useState<string | null>(null)
  const [showOffline, setShowOffline] = useState(false)
  const [pane, setPane] = useState<'list' | 'chat'>('list')

  // Mirrors for use inside WebSocket callbacks and timers, where closures
  // would otherwise go stale.
  const selectedIdRef = useRef<number | null>(null)
  const lastMessageIdRef = useRef<number | null>(null)
  const conversationsRef = useRef<Conversation[] | null>(null)

  useEffect(() => {
    selectedIdRef.current = selectedId
  }, [selectedId])
  useEffect(() => {
    lastMessageIdRef.current = messages !== null && messages.length > 0 ? messages[messages.length - 1].id : null
  }, [messages])
  useEffect(() => {
    conversationsRef.current = conversations
  }, [conversations])

  const selected = conversations?.find((conversation) => conversation.id === selectedId) ?? null

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.listConversations(token))
    } catch (error) {
      setBanner(errorMessage(error))
    }
  }, [token])

  const refreshUsers = useCallback(async () => {
    try {
      setUsers(await api.listUsers(token))
    } catch (error) {
      setBanner(errorMessage(error))
    }
  }, [token])

  /** Best-effort "I have read up to the latest message" ping. */
  const markRead = useCallback(
    async (conversationId: number) => {
      try {
        await api.markConversationRead(token, conversationId)
      } catch {
        // Read receipts are best-effort; never surface this error.
      }
    },
    [token],
  )

  /** Refetch the open conversation's history (used after a reconnect). */
  const reloadSelectedMessages = useCallback(async () => {
    const conversationId = selectedIdRef.current
    if (conversationId === null) return
    try {
      const history = await api.listMessages(token, conversationId, { limit: PAGE_SIZE })
      setMessages((previous) => (previous === null ? history : mergeUnique(previous, history)))
      setHasMore(history.length >= PAGE_SIZE)
      if (history.length > 0) void markRead(conversationId)
    } catch {
      // Ignore; polling will retry.
    }
  }, [token, markRead])

  // Initial data load.
  useEffect(() => {
    void refreshConversations()
    void refreshUsers()
  }, [refreshConversations, refreshUsers])

  // Load history whenever a conversation is opened.
  useEffect(() => {
    if (selectedId === null) {
      setMessages(null)
      setHasMore(false)
      return
    }
    let cancelled = false
    setMessages(null)
    api
      .listMessages(token, selectedId, { limit: PAGE_SIZE })
      .then((history) => {
        if (cancelled) return
        setMessages(history)
        setHasMore(history.length >= PAGE_SIZE)
        // Opening a conversation reads it; this also drives the sender's
        // "Read" indicator.
        if (history.length > 0) void markRead(selectedId)
      })
      .catch((error) => {
        if (cancelled) return
        setMessages([])
        setBanner(errorMessage(error))
      })
    return () => {
      cancelled = true
    }
  }, [selectedId, token])

  const handleEvent = useCallback(
    (event: WsEvent) => {
      if (event.type === 'message') {
        const known = conversationsRef.current?.some((c) => c.id === event.conversation_id) ?? false
        if (!known) void refreshConversations()
        setConversations((previous) => {
          if (previous === null) return previous
          const index = previous.findIndex((c) => c.id === event.conversation_id)
          if (index === -1) return previous
          const next = [...previous]
          next[index] = { ...next[index], last_message: event.message }
          next.sort((a, b) => activityKey(b).localeCompare(activityKey(a)))
          return next
        })
        if (selectedIdRef.current === event.conversation_id) {
          setMessages((previous) => (previous === null ? previous : mergeUnique(previous, [event.message])))
          // We are looking at this conversation, so the message is read.
          void markRead(event.conversation_id)
        }
      } else if (event.type === 'presence') {
        setUsers((previous) =>
          previous?.map((user) => (user.id === event.user_id ? { ...user, is_online: event.online } : user)) ?? previous,
        )
        setConversations((previous) =>
          previous
            ?.map((conversation) =>
              conversation.partner.id === event.user_id
                ? { ...conversation, partner: { ...conversation.partner, is_online: event.online } }
                : conversation,
            ) ?? previous,
        )
      } else if (event.type === 'conversation') {
        setConversations((previous) =>
          previous !== null && !previous.some((c) => c.id === event.conversation.id)
            ? [event.conversation, ...previous]
            : previous,
        )
      } else if (event.type === 'conversation_removed') {
        // This conversation was removed from our list (possibly in another tab).
        setConversations(
          (previous) => previous?.filter((c) => c.id !== event.conversation_id) ?? previous,
        )
        if (selectedIdRef.current === event.conversation_id) {
          setSelectedId(null)
          setPane('list')
        }
      } else if (event.type === 'read') {
        // The partner read our messages; flag them if this conversation is open.
        if (event.reader_id === me.id || selectedIdRef.current !== event.conversation_id) return
        setMessages((previous) => {
          if (previous === null) return previous
          return previous.map((message) =>
            message.sender_id === me.id && message.id <= event.last_read_message_id
              ? { ...message, is_read: true }
              : message,
          )
        })
      } else if (event.type === 'user') {
        setUsers((previous) =>
          previous !== null && !previous.some((user) => user.id === event.user.id)
            ? [...previous, event.user].sort((a, b) => a.username.localeCompare(b.username))
            : previous,
        )
      }
    },
    [me.id, markRead, refreshConversations],
  )

  // Live connection with automatic reconnection.
  useEffect(() => {
    let disposed = false
    let attempt = 0
    let retryTimer: number | undefined
    let socket: WebSocket | null = null

    const connect = () => {
      if (disposed) return
      setWsStatus('connecting')
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      socket = new WebSocket(`${protocol}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`)
      socket.onopen = () => {
        attempt = 0
        setWsStatus('open')
        // Catch up on anything missed while offline.
        void refreshConversations()
        void refreshUsers()
        void reloadSelectedMessages()
      }
      socket.onmessage = (event) => {
        try {
          handleEvent(JSON.parse(String(event.data)) as WsEvent)
        } catch {
          // Ignore malformed frames.
        }
      }
      socket.onclose = (event) => {
        if (disposed) return
        setWsStatus('closed')
        if (event.code === 4401) {
          // The session is no longer valid server-side; return to the login screen.
          onLogout()
          return
        }
        const delay = Math.min(10_000, 1_000 * 2 ** attempt)
        attempt += 1
        retryTimer = window.setTimeout(connect, delay)
      }
      socket.onerror = () => {
        // onclose follows automatically.
      }
    }

    connect()
    return () => {
      disposed = true
      window.clearTimeout(retryTimer)
      socket?.close()
    }
  }, [token, handleEvent, refreshConversations, refreshUsers, reloadSelectedMessages, onLogout])

  // Polling fallback while the live connection is down.
  useEffect(() => {
    if (wsStatus === 'open') return
    const interval = window.setInterval(async () => {
      try {
        setConversations(await api.listConversations(token))
        setUsers(await api.listUsers(token))
        const conversationId = selectedIdRef.current
        if (conversationId === null) return
        const lastId = lastMessageIdRef.current
        const fetched =
          lastId !== null
            ? await api.listMessages(token, conversationId, { afterId: lastId })
            : await api.listMessages(token, conversationId, { limit: PAGE_SIZE })
        if (fetched.length > 0) {
          setMessages((previous) => (previous === null ? previous : mergeUnique(previous, fetched)))
          // New messages arrived in the open conversation; they are read.
          void markRead(conversationId)
        }
      } catch {
        // Stay quiet while offline; the banner already tells the story.
      }
    }, 3_000)
    return () => window.clearInterval(interval)
  }, [wsStatus, token])

  // Only surface the offline banner after a short grace period.
  useEffect(() => {
    if (wsStatus === 'open') {
      setShowOffline(false)
      return
    }
    const timer = window.setTimeout(() => setShowOffline(true), 3_000)
    return () => window.clearTimeout(timer)
  }, [wsStatus])

  const openConversation = useCallback(
    async (partnerId: number) => {
      setBanner(null)
      const existing = conversations?.find((conversation) => conversation.partner.id === partnerId)
      if (existing !== undefined) {
        setSelectedId(existing.id)
        setPane('chat')
        return
      }
      try {
        const conversation = await api.createConversation(token, partnerId)
        setConversations((previous) =>
          previous !== null && !previous.some((c) => c.id === conversation.id)
            ? [conversation, ...previous]
            : previous,
        )
        setSelectedId(conversation.id)
        setPane('chat')
      } catch (error) {
        setBanner(errorMessage(error))
      }
    },
    [conversations, token],
  )

  const removeConversation = useCallback(
    async (conversationId: number) => {
      try {
        await api.removeConversation(token, conversationId)
        setConversations(
          (previous) => previous?.filter((c) => c.id !== conversationId) ?? previous,
        )
        if (selectedIdRef.current === conversationId) {
          setSelectedId(null)
          setPane('list')
        }
      } catch (error) {
        setBanner(errorMessage(error))
      }
    },
    [token],
  )

  const handleSend = useCallback(
    async (content: string): Promise<boolean> => {
      const conversationId = selectedIdRef.current
      if (conversationId === null) return false
      try {
        const message = await api.sendMessage(token, conversationId, content)
        setMessages((previous) => (previous === null ? [message] : mergeUnique(previous, [message])))
        setConversations((previous) => {
          if (previous === null) return previous
          const index = previous.findIndex((c) => c.id === conversationId)
          if (index === -1) return previous
          const next = [...previous]
          next[index] = { ...next[index], last_message: message }
          next.sort((a, b) => activityKey(b).localeCompare(activityKey(a)))
          return next
        })
        return true
      } catch (error) {
        setBanner(errorMessage(error))
        return false
      }
    },
    [token],
  )

  const handleLoadEarlier = useCallback(async (): Promise<void> => {
    const conversationId = selectedIdRef.current
    const first = messages !== null && messages.length > 0 ? messages[0] : null
    if (conversationId === null || first === null) return
    const older = await api.listMessages(token, conversationId, { beforeId: first.id, limit: PAGE_SIZE })
    setHasMore(older.length >= PAGE_SIZE)
    if (older.length > 0) {
      setMessages((previous) => (previous === null ? [...older] : [...older, ...previous]))
    }
  }, [messages, token])

  return (
    <div className="flex h-dvh flex-col bg-slate-950 text-slate-200">
      {banner !== null && <ErrorBanner text={banner} onDismiss={() => setBanner(null)} />}
      {showOffline && <ConnectionBanner />}

      <div className="flex min-h-0 flex-1">
        <div
          className={`${pane === 'chat' ? 'hidden md:block' : 'block'} h-full w-full md:w-80 md:shrink-0 md:border-r md:border-slate-800 lg:w-96`}
        >
          <Sidebar
            me={me}
            conversations={conversations}
            users={users}
            selectedId={selectedId}
            wsStatus={wsStatus}
            onSelect={(id) => {
              setSelectedId(id)
              setPane('chat')
            }}
            onStartChat={(userId) => void openConversation(userId)}
            onRemove={(conversationId) => void removeConversation(conversationId)}
            onLogout={onLogout}
          />
        </div>
        {selected !== null ? (
          <div className={`${pane === 'list' ? 'hidden md:flex' : 'flex'} min-h-0 min-w-0 flex-1`}>
            <ChatWindow
              me={me}
              conversation={selected}
              messages={messages}
              hasMore={hasMore}
              onBack={() => setPane('list')}
              onLoadEarlier={handleLoadEarlier}
              onSend={handleSend}
            />
          </div>
        ) : (
          <EmptyChat />
        )}
      </div>
    </div>
  )
}
