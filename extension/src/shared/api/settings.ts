import { apiRequest } from './client'

/** TTS 设置（与后端 models.py::TTSSettings 严格对齐） */
export interface TTSSettings {
  voice: string
  speed: number
  pitch: number
  volume: number
}

/** 后端 TTSSettingsResponse 额外带 available_voices */
export interface TTSSettingsResponse extends TTSSettings {
  available_voices?: string[]
}

/** 后端 AvailableModelsResponse */
export interface ModelsResponse {
  current_model: string
  available_models: string[]
  llm?: { current: string; available: string[] }
  asr?: { current: string; available: string[] }
  tts?: { current: string; available: string[] }
}

export async function getTTSSettings(): Promise<TTSSettingsResponse> {
  return await apiRequest<TTSSettingsResponse>('/api/settings/tts', { method: 'GET' })
}

export async function updateTTSSettings(data: Partial<TTSSettings>): Promise<TTSSettingsResponse> {
  return await apiRequest<TTSSettingsResponse>('/api/settings/tts', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function listModels(): Promise<ModelsResponse> {
  return await apiRequest<ModelsResponse>('/api/settings/models', { method: 'GET' })
}

/** 切换 LLM 模型 */
export async function updateModel(llm_model: string): Promise<{ current_model: string }> {
  return await apiRequest<{ current_model: string }>('/api/settings/models', {
    method: 'PUT',
    body: JSON.stringify({ llm_model }),
  })
}

/** 切换 ASR 模型 */
export async function updateASRModel(asr_model: string): Promise<any> {
  return await apiRequest<any>('/api/settings/models', {
    method: 'PUT',
    body: JSON.stringify({ asr_model }),
  })
}

/** 切换 TTS 模型 */
export async function updateTTSModel(tts_model: string): Promise<any> {
  return await apiRequest<any>('/api/settings/models', {
    method: 'PUT',
    body: JSON.stringify({ tts_model }),
  })
}

/** 可用音色列表（若后端未提供该端点，listVoices 会失败） */
export async function listVoices(): Promise<{ voices: string[] }> {
  // 目前后端未单独暴露 /voices，改为从 TTSSettingsResponse.available_voices 读取
  const resp = await getTTSSettings()
  return { voices: resp.available_voices || [] }
}
