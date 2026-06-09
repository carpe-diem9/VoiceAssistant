import { apiRequest } from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
  user: { id: number; username: string; email?: string }
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  return await apiRequest<LoginResponse>('/api/auth/login', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ username, password }),
  })
}

export async function register(
  username: string,
  password: string,
  email?: string
): Promise<LoginResponse> {
  return await apiRequest<LoginResponse>('/api/auth/register', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ username, password, email }),
  })
}

export async function getCurrentUser() {
  return await apiRequest('/api/auth/me', { method: 'GET' })
}
