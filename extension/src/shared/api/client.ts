/**
 * 统一的 API 客户端 - fetch 封装 + JWT + baseUrl
 * 适用于 popup / sidepanel / options / background service worker
 */
import { storageGet, StorageKeys } from '../storage/chromeStorage'

export interface ApiError extends Error {
  status?: number
  code?: string
}

export async function getBaseUrl(): Promise<string> {
  const url = await storageGet<string>(StorageKeys.BASE_URL)
  return url || 'http://127.0.0.1:8000'
}

async function getToken(): Promise<string | undefined> {
  return await storageGet<string>(StorageKeys.TOKEN)
}

export interface RequestOptions extends RequestInit {
  auth?: boolean // 默认 true
  parseJson?: boolean // 默认 true
  isForm?: boolean
}

export async function apiRequest<T = any>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { auth = true, parseJson = true, isForm = false, headers, ...rest } = options
  const baseUrl = await getBaseUrl()
  const finalHeaders: Record<string, string> = { ...(headers as Record<string, string>) }

  if (auth) {
    const token = await getToken()
    if (token) finalHeaders['Authorization'] = `Bearer ${token}`
  }
  if (!isForm && !finalHeaders['Content-Type'] && rest.body) {
    finalHeaders['Content-Type'] = 'application/json'
  }

  const res = await fetch(`${baseUrl}${path}`, { ...rest, headers: finalHeaders })
  if (!res.ok) {
    let detail = ''
    try {
      const err = await res.json()
      detail = err.detail || err.message || JSON.stringify(err)
    } catch {
      detail = await res.text()
    }
    const error: ApiError = new Error(detail || `HTTP ${res.status}`)
    error.status = res.status
    throw error
  }

  if (!parseJson) return res as any
  return (await res.json()) as T
}

/** SSE 流式读取（POST JSON） */
export async function* streamSSE(
  path: string,
  body: object,
  opts: { auth?: boolean } = {}
): AsyncGenerator<any, void, unknown> {
  const baseUrl = await getBaseUrl()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (opts.auth !== false) {
    const token = await getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      const line = part.trim()
      if (!line || !line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (!payload) continue
      try {
        yield JSON.parse(payload)
      } catch {
        // 忽略非 JSON
      }
    }
  }
}
