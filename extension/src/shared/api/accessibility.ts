import { apiRequest } from './client'

export type ReadStyle = 'read' | 'summary'

export interface ReadTextResponse {
  text: string
  audio_base64?: string
  audio_format: string
}

/** 无障碍朗读接口：任意文本 → LLM 清洗/总结 → TTS 音频 */
export async function readText(
  text: string,
  style: ReadStyle = 'summary',
  enableTts = true
): Promise<ReadTextResponse> {
  return await apiRequest<ReadTextResponse>('/api/accessibility/read-text', {
    method: 'POST',
    body: JSON.stringify({ text, style, enable_tts: enableTts }),
  })
}
