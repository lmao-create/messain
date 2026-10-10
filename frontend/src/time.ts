function sameDayDates(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

export function sameDay(aIso: string, bIso: string): boolean {
  return sameDayDates(new Date(aIso), new Date(bIso))
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

export function formatRelative(iso: string): string {
  const date = new Date(iso)
  const minutes = Math.floor((Date.now() - date.getTime()) / 60_000)
  if (minutes < 1) return 'now'
  if (minutes < 60) return `${minutes}m`
  const today = new Date()
  if (minutes < 1440 && sameDayDates(date, today)) return `${Math.floor(minutes / 60)}h`
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  if (sameDayDates(date, yesterday)) return 'yesterday'
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function dayLabel(iso: string): string {
  const date = new Date(iso)
  const today = new Date()
  if (sameDayDates(date, today)) return 'Today'
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  if (sameDayDates(date, yesterday)) return 'Yesterday'
  const options: Intl.DateTimeFormatOptions =
    date.getFullYear() === today.getFullYear()
      ? { weekday: 'short', month: 'short', day: 'numeric' }
      : { month: 'long', day: 'numeric', year: 'numeric' }
  return date.toLocaleDateString(undefined, options)
}
