import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as settingsApi from '../api/settings'
import type { TTSSettings } from '../api/settings'
import { storageGet, storageSet, StorageKeys } from '../storage/chromeStorage'

export const useSettingsStore = defineStore('settings', () => {
  // TTS 设置（voice/speed/pitch/volume，严格对齐后端）
  const tts = ref<TTSSettings | null>(null)
  const voices = ref<string[]>(['Cherry', 'Serena', 'Ethan', 'Chelsie', 'Bella'])
  const models = ref<string[]>([])
  const currentModel = ref<string>('qwen3.5-plus')
  // ASR / TTS 模型选择
  const asrModels = ref<string[]>([])
  const currentASRModel = ref<string>('qwen3-asr-flash')
  const ttsModels = ref<string[]>([])
  const currentTTSModel = ref<string>('qwen3-tts-instruct-flash')
  const wakeWord = ref<string>('你好助手')
  const wakeWordEnabled = ref(false)
  const floatingBallEnabled = ref(false)
  const baseUrl = ref<string>('http://127.0.0.1:8000')
  const loading = ref(false)
  const error = ref<string>('')

  async function init() {
    baseUrl.value = (await storageGet<string>(StorageKeys.BASE_URL)) || 'http://127.0.0.1:8000'
    wakeWord.value = (await storageGet<string>(StorageKeys.WAKE_WORD)) || '你好助手'
    wakeWordEnabled.value =
      (await storageGet<boolean>(StorageKeys.WAKE_WORD_ENABLED)) || false
    floatingBallEnabled.value =
      (await storageGet<boolean>(StorageKeys.FLOATING_BALL_ENABLED)) || false
  }

  async function loadFromServer() {
    loading.value = true
    error.value = ''
    try {
      const ttsResp = await settingsApi.getTTSSettings()
      tts.value = {
        voice: ttsResp.voice,
        speed: ttsResp.speed,
        pitch: ttsResp.pitch,
        volume: ttsResp.volume,
      }
      if (ttsResp.available_voices?.length) voices.value = ttsResp.available_voices
      try {
        const m = await settingsApi.listModels()
        if (m?.available_models?.length) models.value = m.available_models
        if (m?.current_model) currentModel.value = m.current_model
        // 新的分类返回
        if (m?.llm?.available?.length) models.value = m.llm.available
        if (m?.llm?.current) currentModel.value = m.llm.current
        if (m?.asr?.available?.length) asrModels.value = m.asr.available
        if (m?.asr?.current) currentASRModel.value = m.asr.current
        if (m?.tts?.available?.length) ttsModels.value = m.tts.available
        if (m?.tts?.current) currentTTSModel.value = m.tts.current
      } catch {
        /* 忽略 */
      }
    } catch (e: any) {
      error.value = e.message || '设置加载失败'
    } finally {
      loading.value = false
    }
  }

  async function saveTTS(data: Partial<TTSSettings>) {
    const updated = await settingsApi.updateTTSSettings(data)
    tts.value = {
      voice: updated.voice,
      speed: updated.speed,
      pitch: updated.pitch,
      volume: updated.volume,
    }
    await storageSet(StorageKeys.TTS_SETTINGS, tts.value)
    return tts.value
  }

  async function saveModel(llm_model: string) {
    const resp = await settingsApi.updateModel(llm_model)
    currentModel.value = resp.current_model || llm_model
    return currentModel.value
  }

  async function saveASRModel(asr_model: string) {
    await settingsApi.updateASRModel(asr_model)
    currentASRModel.value = asr_model
    return asr_model
  }

  async function saveTTSModel(tts_model: string) {
    await settingsApi.updateTTSModel(tts_model)
    currentTTSModel.value = tts_model
    return tts_model
  }

  async function setBaseUrl(url: string) {
    baseUrl.value = url
    await storageSet(StorageKeys.BASE_URL, url)
  }

  async function setWakeWord(val: string) {
    wakeWord.value = val
    await storageSet(StorageKeys.WAKE_WORD, val)
  }

  async function setWakeWordEnabled(v: boolean) {
    wakeWordEnabled.value = v
    await storageSet(StorageKeys.WAKE_WORD_ENABLED, v)
  }

  async function setFloatingBallEnabled(v: boolean) {
    floatingBallEnabled.value = v
    await storageSet(StorageKeys.FLOATING_BALL_ENABLED, v)
  }

  return {
    tts,
    voices,
    models,
    currentModel,
    asrModels,
    currentASRModel,
    ttsModels,
    currentTTSModel,
    wakeWord,
    wakeWordEnabled,
    floatingBallEnabled,
    baseUrl,
    loading,
    error,
    init,
    loadFromServer,
    saveTTS,
    saveModel,
    saveASRModel,
    saveTTSModel,
    setBaseUrl,
    setWakeWord,
    setWakeWordEnabled,
    setFloatingBallEnabled,
  }
})
