export interface User {
  id: number
  username: string
  created_at: string
  is_online: boolean
}

export interface Message {
  id: number
  conversation_id: number
  sender_id: number
  content: string
  created_at: string
  is_read: boolean
}

export interface Conversation {
  id: number
  created_at: string
  partner: User
  last_message: Message | null
}

export interface AuthResponse {
  token: string
  user: User
}

export type WsStatus = 'connecting' | 'open' | 'closed'

export type WsEvent =
  | { type: 'message'; conversation_id: number; message: Message }
  | { type: 'presence'; user_id: number; online: boolean }
  | { type: 'conversation'; conversation: Conversation }
  | { type: 'conversation_removed'; conversation_id: number }
  | { type: 'read'; conversation_id: number; reader_id: number; last_read_message_id: number }
  | { type: 'user'; user: User }
