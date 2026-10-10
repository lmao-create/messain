import type { AuthResponse, Conversation, Message, User } from './types'

const TOKEN_STORAGE_KEY = 'messain_token'

export function storedToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function storeToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function extractMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        item && typeof item === 'object' && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : String(item),
      )
      .join(', ')
  }
  return 'Unexpected server error'
}

async function request<T>(path: string, token: string | null, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  if (init?.body != null) headers['Content-Type'] = 'application/json'
  if (token !== null) headers['Authorization'] = `Bearer ${token}`

  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }

  if (response.status === 204) return undefined as T

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail
    throw new ApiError(
      response.status,
      detail ? extractMessage(detail) : `Request failed (${response.status})`,
    )
  }
  return payload as T
}

export const api = {
  register: (username: string, password: string) =>
    request<AuthResponse>('/auth/register', null, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  login: (username: string, password: string) =>
    request<AuthResponse>('/auth/login', null, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  logout: (token: string) => request<void>('/auth/logout', token, { method: 'POST' }),

  me: (token: string) => request<User>('/users/me', token),

  listUsers: (token: string) => request<User[]>('/users', token),

  listConversations: (token: string) => request<Conversation[]>('/conversations', token),

  createConversation: (token: string, userId: number) =>
    request<Conversation>('/conversations', token, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId }),
    }),

  listMessages: (
    token: string,
    conversationId: number,
    params: { afterId?: number; beforeId?: number; limit?: number } = {},
  ) => {
    const query = new URLSearchParams()
    if (params.afterId !== undefined) query.set('after_id', String(params.afterId))
    if (params.beforeId !== undefined) query.set('before_id', String(params.beforeId))
    if (params.limit !== undefined) query.set('limit', String(params.limit))
    const suffix = query.size > 0 ? `?${query.toString()}` : ''
    return request<Message[]>(`/conversations/${conversationId}/messages${suffix}`, token)
  },

  sendMessage: (token: string, conversationId: number, content: string) =>
    request<Message>(`/conversations/${conversationId}/messages`, token, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),

  removeConversation: (token: string, conversationId: number) =>
    request<void>(`/conversations/${conversationId}`, token, { method: 'DELETE' }),

  markConversationRead: (token: string, conversationId: number) =>
    request<void>(`/conversations/${conversationId}/read`, token, { method: 'POST' }),
}
