import { useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { SendIcon } from './Icons'

interface MessageInputProps {
  onSend: (content: string) => Promise<boolean>
}

export default function MessageInput({ onSend }: MessageInputProps) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const autoResize = () => {
    const element = textareaRef.current
    if (element === null) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 144)}px`
  }

  const submit = async () => {
    const content = text.trim()
    if (content.length === 0 || sending) return
    setSending(true)
    const ok = await onSend(content)
    setSending(false)
    if (ok) {
      setText('')
      const element = textareaRef.current
      if (element !== null) {
        element.style.height = 'auto'
        element.focus()
      }
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <div className="border-t border-slate-800 bg-slate-900 p-3">
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
        className="mx-auto flex max-w-2xl items-end gap-2 rounded-xl border border-slate-700 bg-slate-800 p-2 transition-colors focus-within:border-indigo-500"
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={(event) => {
            setText(event.target.value)
            autoResize()
          }}
          onKeyDown={handleKeyDown}
          placeholder="Type a message…"
          className="max-h-36 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-slate-100 placeholder-slate-500 outline-none"
        />
        <button
          type="submit"
          disabled={sending || text.trim().length === 0}
          aria-label="Send message"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SendIcon className="h-4 w-4" />
        </button>
      </form>
      <p className="mt-2 hidden text-center text-xs text-slate-600 sm:block">
        Enter to send, Shift + Enter for a new line.
      </p>
    </div>
  )
}
