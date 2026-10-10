import { Fragment, useEffect, useRef, useState } from 'react'
import type { Message, User } from '../types'
import { dayLabel, formatTime, sameDay } from '../time'
import { CheckCheckIcon, CheckIcon } from './Icons'

interface MessageListProps {
  me: User
  partnerName: string
  /** null while the history is being fetched. */
  messages: Message[] | null
  hasMore: boolean
  onLoadEarlier: () => Promise<void>
}

export default function MessageList({
  me,
  partnerName,
  messages,
  hasMore,
  onLoadEarlier,
}: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const busyRef = useRef(false)
  const [busy, setBusy] = useState(false)

  // Keep the view pinned to the newest message unless the user scrolled up.
  useEffect(() => {
    const element = containerRef.current
    if (element === null || messages === null) return
    if (stickToBottomRef.current) element.scrollTop = element.scrollHeight
  }, [messages])

  const handleScroll = () => {
    const element = containerRef.current
    if (element === null) return
    stickToBottomRef.current = element.scrollHeight - element.scrollTop - element.clientHeight < 140
  }

  const handleLoadEarlier = async () => {
    const element = containerRef.current
    if (element === null || busyRef.current) return
    busyRef.current = true
    setBusy(true)
    const previousHeight = element.scrollHeight
    const previousTop = element.scrollTop
    try {
      await onLoadEarlier()
      // Keep the viewport anchored on the messages the user was reading.
      requestAnimationFrame(() => {
        element.scrollTop = element.scrollHeight - previousHeight + previousTop
      })
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const list = messages ?? []
  const decorated = list.map((message, index) => ({
    message,
    mine: message.sender_id === me.id,
    newDay: index === 0 || !sameDay(list[index - 1].created_at, message.created_at),
    grouped:
      index > 0 &&
      list[index - 1].sender_id === message.sender_id &&
      sameDay(list[index - 1].created_at, message.created_at),
  }))

  return (
    <div ref={containerRef} onScroll={handleScroll} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      {messages === null ? (
        <div className="flex h-full items-center justify-center">
          <div
            aria-label="Loading messages"
            className="h-6 w-6 animate-spin rounded-full border-2 border-slate-700 border-t-indigo-500"
          />
        </div>
      ) : (
        <>
          {hasMore && (
            <div className="mb-4 flex justify-center">
              <button
                onClick={() => void handleLoadEarlier()}
                disabled={busy}
                className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 transition-colors hover:bg-slate-800 disabled:opacity-50"
              >
                {busy ? 'Loading…' : 'Load earlier messages'}
              </button>
            </div>
          )}
          {decorated.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 py-16 text-center">
              <p className="text-slate-400">No messages yet.</p>
              <p className="text-sm text-slate-600">Say hello to {partnerName}!</p>
            </div>
          ) : (
            <ul className="mx-auto flex max-w-2xl flex-col">
              {decorated.map(({ message, mine, newDay, grouped }) => (
                <Fragment key={message.id}>
                  {newDay && (
                    <li className="my-4 flex justify-center">
                      <span className="rounded-full bg-slate-800/80 px-3 py-1 text-xs text-slate-400">
                        {dayLabel(message.created_at)}
                      </span>
                    </li>
                  )}
                  <li
                    className={`flex ${mine ? 'justify-end' : 'justify-start'} ${
                      grouped ? 'mt-0.5' : 'mt-3'
                    }`}
                  >
                    <div
                      className={`max-w-[75%] rounded-2xl px-3.5 py-2 ${
                        mine
                          ? 'rounded-br-md bg-indigo-600 text-white'
                          : 'rounded-bl-md bg-slate-800 text-slate-100'
                      }`}
                    >
                      <p className="whitespace-pre-wrap break-words text-sm">{message.content}</p>
                      <p
                        className={`mt-1 flex items-center justify-end gap-1 text-[10px] leading-none ${
                          mine ? 'text-indigo-200' : 'text-slate-500'
                        }`}
                      >
                        {mine &&
                          (message.is_read ? (
                            <span className="flex items-center gap-0.5 text-sky-300" title="Read">
                              <CheckCheckIcon className="h-3 w-3" />
                              Read
                            </span>
                          ) : (
                            <span title="Sent">
                              <CheckIcon className="h-3 w-3 text-indigo-300/70" />
                            </span>
                          ))}
                        <span>{formatTime(message.created_at)}</span>
                      </p>
                    </div>
                  </li>
                </Fragment>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
