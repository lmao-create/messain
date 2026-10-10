import type { Conversation, User, WsStatus } from '../types'
import { formatRelative } from '../time'
import Avatar from './Avatar'
import { ChatIcon, LogoutIcon, TrashIcon, UserIcon } from './Icons'

interface SidebarProps {
  me: User
  conversations: Conversation[] | null
  users: User[] | null
  selectedId: number | null
  wsStatus: WsStatus
  onSelect: (conversationId: number) => void
  onStartChat: (userId: number) => void
  onRemove: (conversationId: number) => void
  onLogout: () => void
}

function SectionHeading({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <h2 className="flex items-center gap-1.5 px-2 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
      {icon}
      {title}
    </h2>
  )
}

function ConversationRow({
  conversation,
  me,
  active,
  onSelect,
  onRemove,
}: {
  conversation: Conversation
  me: User
  active: boolean
  onSelect: (id: number) => void
  onRemove: (id: number) => void
}) {
  const last = conversation.last_message
  const preview = last
    ? `${last.sender_id === me.id ? 'You: ' : ''}${last.content.replace(/\s+/g, ' ')}`
    : 'No messages yet'

  const handleRemove = () => {
    if (
      window.confirm(
        `Delete the conversation with ${conversation.partner.username}? This permanently deletes all messages in it, for both of you.`,
      )
    ) {
      onRemove(conversation.id)
    }
  }

  return (
    <li className="group">
      <div className="flex items-center gap-1">
        <button
          onClick={() => onSelect(conversation.id)}
          className={`flex min-w-0 flex-1 items-center gap-3 rounded-lg px-2 py-2 text-left ${
            active ? 'bg-slate-800' : 'hover:bg-slate-800/60'
          }`}
        >
          <Avatar username={conversation.partner.username} online={conversation.partner.is_online} />
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline justify-between gap-2">
              <span className="truncate font-medium text-slate-100">{conversation.partner.username}</span>
              {last !== null && (
                <span className="shrink-0 text-xs text-slate-500">{formatRelative(last.created_at)}</span>
              )}
            </span>
            <span className="block truncate text-sm text-slate-400">{preview}</span>
          </span>
        </button>
        <button
          onClick={handleRemove}
          aria-label={`Delete conversation with ${conversation.partner.username}`}
          title="Delete conversation"
          className="shrink-0 rounded-md p-1.5 text-slate-500 transition-all hover:bg-slate-800 hover:text-red-400 focus-visible:opacity-100 md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100"
        >
          <TrashIcon className="h-4 w-4" />
        </button>
      </div>
    </li>
  )
}

function UserRow({ user, onStartChat }: { user: User; onStartChat: (id: number) => void }) {
  return (
    <li>
      <button
        onClick={() => onStartChat(user.id)}
        className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-slate-800/60"
      >
        <Avatar username={user.username} online={user.is_online} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium text-slate-100">{user.username}</span>
          <span className={`block text-xs ${user.is_online ? 'text-emerald-400' : 'text-slate-500'}`}>
            {user.is_online ? 'Online' : 'Offline'}
          </span>
        </span>
      </button>
    </li>
  )
}

function Skeleton({ count }: { count: number }) {
  return (
    <div aria-hidden className="space-y-1">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="flex animate-pulse items-center gap-3 rounded-lg px-2 py-2">
          <div className="h-10 w-10 rounded-full bg-slate-800" />
          <div className="flex-1 space-y-2">
            <div className="h-3 w-24 rounded bg-slate-800" />
            <div className="h-3 w-36 rounded bg-slate-800" />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Sidebar({
  me,
  conversations,
  users,
  selectedId,
  wsStatus,
  onSelect,
  onStartChat,
  onRemove,
  onLogout,
}: SidebarProps) {
  const people = (users ?? []).filter(
    (user) => !(conversations ?? []).some((conversation) => conversation.partner.id === user.id),
  )

  return (
    <aside className="flex h-full w-full flex-col bg-slate-900">
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
          <ChatIcon className="h-5 w-5" />
        </span>
        <span className="text-base font-semibold text-slate-100">Messain</span>
        <span
          className={`ml-auto flex items-center gap-1.5 text-xs ${
            wsStatus === 'open' ? 'text-emerald-400' : 'text-slate-500'
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${wsStatus === 'open' ? 'bg-emerald-400' : 'bg-slate-500 animate-pulse'}`}
          />
          {wsStatus === 'open' ? 'Live' : 'Connecting…'}
        </span>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        <SectionHeading icon={<ChatIcon className="h-3.5 w-3.5" />} title="Messages" />
        {conversations === null ? (
          <Skeleton count={4} />
        ) : conversations.length === 0 ? (
          <p className="px-2 py-2 text-sm text-slate-500">
            No conversations yet. Start one from “People” below.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((conversation) => (
              <ConversationRow
                key={conversation.id}
                conversation={conversation}
                me={me}
                active={conversation.id === selectedId}
                onSelect={onSelect}
                onRemove={onRemove}
              />
            ))}
          </ul>
        )}

        <SectionHeading icon={<UserIcon className="h-3.5 w-3.5" />} title="People" />
        {users === null ? (
          <Skeleton count={3} />
        ) : people.length === 0 ? (
          <p className="px-2 py-2 text-sm text-slate-500">
            No one new to message. Register another account to start a chat.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {people.map((user) => (
              <UserRow key={user.id} user={user} onStartChat={onStartChat} />
            ))}
          </ul>
        )}
      </nav>

      <div className="flex items-center gap-3 border-t border-slate-800 px-4 py-3">
        <Avatar username={me.username} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-slate-100">{me.username}</p>
          <p className="text-xs text-slate-500">Signed in</p>
        </div>
        <button
          onClick={onLogout}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-2.5 py-1.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-slate-100"
        >
          <LogoutIcon className="h-4 w-4" />
          <span className="hidden sm:inline">Log out</span>
        </button>
      </div>
    </aside>
  )
}
