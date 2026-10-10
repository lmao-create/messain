interface AvatarProps {
  username: string
  /** Omit to hide the status dot entirely. */
  online?: boolean
  className?: string
}

function hueFor(username: string): number {
  let hash = 0
  for (let i = 0; i < username.length; i += 1) {
    hash = (hash * 31 + username.charCodeAt(i)) % 360
  }
  return hash
}

export default function Avatar({ username, online, className = 'h-10 w-10 text-sm' }: AvatarProps) {
  return (
    <span className={`relative inline-flex shrink-0 ${className}`}>
      <span
        className="flex h-full w-full items-center justify-center rounded-full font-semibold text-slate-100"
        style={{ backgroundColor: `hsl(${hueFor(username)} 35% 32%)` }}
      >
        {username.charAt(0).toUpperCase()}
      </span>
      {online !== undefined && (
        <span
          title={online ? 'Online' : 'Offline'}
          className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-slate-900 ${
            online ? 'bg-emerald-400' : 'bg-slate-500'
          }`}
        />
      )}
    </span>
  )
}
