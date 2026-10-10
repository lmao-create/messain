import { WifiOffIcon, XIcon } from './Icons'

export function ErrorBanner({ text, onDismiss }: { text: string; onDismiss: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 border-b border-red-900/60 bg-red-950/70 px-4 py-2 text-sm text-red-200"
    >
      <span className="min-w-0 truncate">{text}</span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 rounded p-1 hover:bg-red-900/50"
      >
        <XIcon className="h-4 w-4" />
      </button>
    </div>
  )
}

export function ConnectionBanner() {
  return (
    <div className="flex items-center gap-2 border-b border-amber-900/60 bg-amber-950/50 px-4 py-2 text-sm text-amber-200">
      <WifiOffIcon className="h-4 w-4 shrink-0" />
      <span>Live connection lost — new messages are being fetched periodically.</span>
    </div>
  )
}
