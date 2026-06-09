/**
 * chrome.storage.local 封装，Promise 风格
 */

export async function storageGet<T = any>(key: string): Promise<T | undefined> {
  const result = await chrome.storage.local.get(key)
  return result[key] as T | undefined
}

export async function storageSet(key: string, value: any): Promise<void> {
  await chrome.storage.local.set({ [key]: value })
}

export async function storageRemove(key: string): Promise<void> {
  await chrome.storage.local.remove(key)
}

export async function storageGetMany<T = Record<string, any>>(
  keys: string[]
): Promise<Partial<T>> {
  const result = await chrome.storage.local.get(keys)
  return result as Partial<T>
}

export function storageOnChanged(
  callback: (changes: { [key: string]: chrome.storage.StorageChange }) => void
): () => void {
  const listener = (
    changes: { [key: string]: chrome.storage.StorageChange },
    areaName: string
  ) => {
    if (areaName === 'local') callback(changes)
  }
  chrome.storage.onChanged.addListener(listener)
  return () => chrome.storage.onChanged.removeListener(listener)
}

// 常用键名常量
export const StorageKeys = {
  TOKEN: 'auth_token',
  USER: 'auth_user',
  BASE_URL: 'base_url',
  TTS_ENABLED: 'tts_enabled',
  TTS_SETTINGS: 'tts_settings',
  WAKE_WORD: 'wake_word',
  WAKE_WORD_ENABLED: 'wake_word_enabled',
  FLOATING_BALL_ENABLED: 'floating_ball_enabled',
  FLOATING_BALL_MODE: 'floating_ball_mode', // 'read' | 'summary'
  FLOATING_BALL_POS: 'floating_ball_pos',
  DEEP_RESEARCH_MODE: 'deep_research_mode',
} as const
