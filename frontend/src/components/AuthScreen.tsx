import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from '../api'
import type { User } from '../types'
import { ChatIcon } from './Icons'

interface AuthScreenProps {
  onAuthenticated: (token: string, user: User) => void
}

const inputClass =
  'mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 ' +
  'placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500'

export default function AuthScreen({ onAuthenticated }: AuthScreenProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const switchMode = (next: 'login' | 'register') => {
    setMode(next)
    setError(null)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const result =
        mode === 'login' ? await api.login(username, password) : await api.register(username, password)
      onAuthenticated(result.token, result.user)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const tabClass = (active: boolean) =>
    `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
      active ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-200'
    }`

  return (
    <div className="flex min-h-dvh items-center justify-center bg-slate-950 px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-white">
            <ChatIcon className="h-7 w-7" />
          </span>
          <div className="text-center">
            <h1 className="text-2xl font-semibold text-slate-100">Messain</h1>
            <p className="mt-1 text-sm text-slate-400">Simple, real-time messaging.</p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl shadow-black/30">
          <div className="mb-6 grid grid-cols-2 gap-1 rounded-lg bg-slate-800 p-1">
            <button type="button" onClick={() => switchMode('login')} className={tabClass(mode === 'login')}>
              Sign in
            </button>
            <button type="button" onClick={() => switchMode('register')} className={tabClass(mode === 'register')}>
              Register
            </button>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <label className="block text-sm text-slate-300">
              Username
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
                minLength={3}
                maxLength={32}
                autoComplete="username"
                autoFocus
                placeholder="e.g. alice"
                className={inputClass}
              />
            </label>
            <label className="block text-sm text-slate-300">
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                placeholder="At least 8 characters"
                className={inputClass}
              />
            </label>

            {error !== null && (
              <p className="rounded-lg border border-red-900/60 bg-red-950/50 px-3 py-2 text-sm text-red-300" role="alert">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy || username.trim().length === 0 || password.length === 0}
              className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </form>

          <p className="mt-4 text-center text-xs text-slate-500">
            {mode === 'login' ? 'No account yet? ' : 'Already registered? '}
            <button
              type="button"
              onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}
              className="font-medium text-indigo-400 hover:text-indigo-300"
            >
              {mode === 'login' ? 'Register' : 'Sign in'}
            </button>
          </p>
        </div>

        <p className="mt-6 text-center text-xs text-slate-600">
          Register a second account in another browser window to chat with yourself.
        </p>
      </div>
    </div>
  )
}
