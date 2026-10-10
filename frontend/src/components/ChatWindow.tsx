import type { Conversation, Message, User } from '../types'
import Avatar from './Avatar'
import MessageList from './MessageList'
import MessageInput from './MessageInput'
import { ArrowLeftIcon, ChatIcon } from './Icons'

interface ChatWindowProps {
  me: User
  conversation: Conversation
  messages: Message[] | null
  hasMore: boolean
  onBack: () => void
  onLoadEarlier: () => Promise<void>
  onSend: (content: string) => Promise<boolean>
}

export default function ChatWindow({
  me,
  conversation,
  messages,
  hasMore,
  onBack,
  onLoadEarlier,
  onSend,
}: ChatWindowProps) {
  const partner = conversation.partner
  return (
    <section className="flex h-full min-w-0 flex-1 flex-col bg-slate-950">
      <header className="flex items-center gap-3 border-b border-slate-800 bg-slate-900 px-4 py-3">
        <button
          onClick={onBack}
          aria-label="Back to conversations"
          className="-ml-1 rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200 md:hidden"
        >
          <ArrowLeftIcon className="h-5 w-5" />
        </button>
        <Avatar username={partner.username} online={partner.is_online} />
        <div className="min-w-0">
          <h2 className="truncate font-semibold text-slate-100">{partner.username}</h2>
          <p className={`text-xs ${partner.is_online ? 'text-emerald-400' : 'text-slate-500'}`}>
            {partner.is_online ? 'Online' : 'Offline'}
          </p>
        </div>
      </header>

      <MessageList
        key={conversation.id}
        me={me}
        partnerName={partner.username}
        messages={messages}
        hasMore={hasMore}
        onLoadEarlier={onLoadEarlier}
      />
      <MessageInput onSend={onSend} />
    </section>
  )
}

export function EmptyChat() {
  return (
    <section className="hidden flex-1 flex-col items-center justify-center gap-3 bg-slate-950 px-6 text-center md:flex">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
        <ChatIcon className="h-7 w-7" />
      </span>
      <p className="text-slate-400">Select a conversation to start messaging.</p>
      <p className="max-w-sm text-sm text-slate-600">
        Pick someone from “Messages”, or start a new chat from “People” in the sidebar.
      </p>
    </section>
  )
}
