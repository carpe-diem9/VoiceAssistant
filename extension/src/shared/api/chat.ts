import { streamSSE, apiRequest, getBaseUrl } from './client'
import { storageGet, StorageKeys } from '../storage/chromeStorage'

/** 文本对话 SSE */
export async function* chatTextStream(
  message: string,
  sessionId: number | null,
  enableTts: boolean
) {
  yield* streamSSE('/api/chat/text', {
    message,
    session_id: sessionId,
    enable_tts: enableTts,
  })
}

/** 语音对话 - 上传音频 + 接收 SSE */
export async function* chatVoiceStream(
  audioBlob: Blob,
  sessionId: number | null,
  enableTts: boolean
) {
  const baseUrl = await getBaseUrl()
  const token = await storageGet<string>(StorageKeys.TOKEN)
  const fd = new FormData()
  fd.append('audio', audioBlob, 'audio.wav')
  if (sessionId != null) fd.append('session_id', String(sessionId))
  fd.append('enable_tts', String(enableTts))

  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${baseUrl}/api/chat/voice/stream`, {
    method: 'POST',
    headers,
    body: fd,
  })
  if (!res.ok || !res.body) {
    throw new Error(await res.text())
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
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (!payload) continue
      try {
        yield JSON.parse(payload)
      } catch {
        /* noop */
      }
    }
  }
}

/** Deep Research SSE (tongyi-deepresearch via OpenRouter)
 * 事件类型: session_id | step | thinking | final_chunk | final | error
 */
export async function* chatDeepResearchStream(
  question: string,
  sessionId: number | null
) {
  yield* streamSSE('/api/chat/deep-research', {
    question,
    session_id: sessionId,
  })
}

/** 唤醒词检测 */
export async function detectWakeWord(audioBlob: Blob, wakeWord: string) {
  const fd = new FormData()
  fd.append('audio', audioBlob, 'wake.wav')
  fd.append('wake_word', wakeWord)
  return await apiRequest<{ detected: boolean; text: string }>('/api/chat/wake-word', {
    method: 'POST',
    body: fd,
    isForm: true,
  })
}
