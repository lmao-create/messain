import { useEffect, useState } from 'react'
import { api, ApiError, clearToken, storedToken, storeToken } from './api'
import type { User } from './types'
import AuthScreen from './components/AuthScreen'
import ChatApp from './components/ChatApp'

export default function App() {
  const [token, setToken] = useState<string | null>(() => storedToken())
  const [user, setUser] = useState<User | null>(null)
  const [booting, setBooting] = useState(true)
  const [fatal, setFatal] = useState<string | null>(null)

  // Validate the stored session on startup.
  useEffect(() => {
    let cancelled = false
    if (token === null) {
      setBooting(false)
      return
    }
    api
      .me(token)
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch((error) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 401) {
          clearToken()
          setToken(null)
        } else {
          setFatal(error instanceof Error ? error.message : 'Failed to load your session')
        }
      })
      .finally(() => {
        if (!cancelled) setBooting(false)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const handleAuthenticated = (newToken: string, newUser: User) => {
    storeToken(newToken)
    setToken(newToken)
    setUser(newUser)
  }

  const handleLogout = async () => {
    if (token !== null) {
      try {
        await api.logout(token)
      } catch {
        // Best effort; the local session is cleared either way.
      }
    }
    clearToken()
    setToken(null)
    setUser(null)
  }

  if (booting) {
    return (
      <div className="flex h-dvh items-center justify-center bg-slate-950">
        <div
          aria-label="Loading"
          className="h-7 w-7 animate-spin rounded-full border-2 border-slate-700 border-t-indigo-500"
        />
      </div>
    )
  }

  if (fatal !== null) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-4 bg-slate-950 px-4 text-center">
        <p className="max-w-sm text-slate-300">{fatal}</p>
        <button
          onClick={() => window.location.reload()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
        >
          Try again
        </button>
      </div>
    )
  }

  if (token === null || user === null) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />
  }

  return <ChatApp token={token} me={user} onLogout={() => void handleLogout()} />
}
