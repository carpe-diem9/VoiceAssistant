import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import * as sessionApi from '../api/session'
import * as chatApi from '../api/chat'
import type { Session, Message } from '../api/session'
import { storageGet, storageSet, StorageKeys } from '../storage/chromeStorage'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<number | null>(null)
  const messages = ref<Message[]>([])
  const isLoadingSessions = ref(false)
  const isStreaming = ref(false)
  const error = ref<string>('')
  const ttsEnabled = ref(false)
  // Deep Research 模式（开启后 text 消息走 tongyi-deepresearch）
  const deepResearchMode = ref(false)
  // 初始化：从 chrome.storage 加载持久化状态
  storageGet<boolean>(StorageKeys.DEEP_RESEARCH_MODE).then(v => {
    if (v !== undefined && v !== null) deepResearchMode.value = v
  })
  // 持久化：状态变化时写入 chrome.storage
  watch(deepResearchMode, (v) => {
    storageSet(StorageKeys.DEEP_RESEARCH_MODE, v)
  })
  // 当前正在展示的 Deep Research 步骤（仅本地 UI，不持久化）
  const drSteps = ref<string[]>([])
  const drThinking = ref<string>('')

  async function loadSessions() {
    isLoadingSessions.value = true
    try {
      sessions.value = await sessionApi.listSessions()
    } catch (e: any) {
      error.value = e.message
    } finally {
      isLoadingSessions.value = false
    }
  }

  async function selectSession(id: number) {
    currentSessionId.value = id
    try {
      messages.value = await sessionApi.getMessages(id)
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function newSession() {
    // 在后端实际创建一个新会话，然后选中它。
    // 若后端创建失败，降级为仅清空本地状态（发消息时会由后端自动创建）。
    try {
      const s = await sessionApi.createSession('新对话')
      sessions.value = [s, ...sessions.value]
      currentSessionId.value = s.id
      messages.value = []
    } catch (e: any) {
      error.value = e.message
      currentSessionId.value = null
      messages.value = []
    }
  }

  async function deleteSession(id: number) {
    await sessionApi.deleteSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (currentSessionId.value === id) {
      // 删除当前会话后，自动切到剩余列表中的第一个
      const next = sessions.value[0]
      if (next) {
        await selectSession(next.id)
      } else {
        currentSessionId.value = null
        messages.value = []
      }
    }
  }

  async function sendText(text: string, onAudio?: (base64: string) => void) {
    if (!text.trim() || isStreaming.value) return
    const userMsg: Message = {
      id: Date.now(),
      session_id: currentSessionId.value || 0,
      role: 'user',
      content: deepResearchMode.value ? `🔬 [Deep Research] ${text}` : text,
      created_at: new Date().toISOString(),
    }
    const assistantMsg: Message = {
      id: Date.now() + 1,
      session_id: currentSessionId.value || 0,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
    }
    messages.value.push(userMsg, assistantMsg)
    isStreaming.value = true
    drSteps.value = []
    drThinking.value = ''
    try {
      if (deepResearchMode.value) {
        for await (const data of chatApi.chatDeepResearchStream(
          text,
          currentSessionId.value,
        )) {
          if (data.type === 'session_id') {
            currentSessionId.value = data.session_id
          } else if (data.type === 'step') {
            const stepText = `✨ 步骤 ${data.step || ''}: ${data.content || ''}`
            drSteps.value.push(stepText)
            // 将步骤汇总到气泡顶部，便于用户看到推理过程
            assistantMsg.content = [
              ...drSteps.value,
              drThinking.value ? `\n> 🧠 ${drThinking.value}` : '',
              '',
            ]
              .filter(Boolean)
              .join('\n')
            messages.value = [...messages.value]
          } else if (data.type === 'thinking') {
            drThinking.value += data.content || ''
            assistantMsg.content =
              drSteps.value.join('\n') +
              (drThinking.value ? `\n\n> 🧠 ${drThinking.value}` : '')
            messages.value = [...messages.value]
          } else if (data.type === 'final_chunk') {
            // 进入正式回答阶段：若还未插入分隔线，先插入
            if (!assistantMsg.content.includes('---\n')) {
              const header =
                (drSteps.value.length
                  ? drSteps.value.join('\n') + '\n\n'
                  : '') +
                (drThinking.value ? `> 🧠 ${drThinking.value}\n\n` : '') +
                '---\n'
              assistantMsg.content = header
            }
            assistantMsg.content += data.content || ''
            messages.value = [...messages.value]
          } else if (data.type === 'final') {
            // 最终完整结果，用于兼容后端一次性返回的情况
            if (data.content && !assistantMsg.content.includes(data.content)) {
              const header =
                (drSteps.value.length
                  ? drSteps.value.join('\n') + '\n\n'
                  : '') +
                (drThinking.value ? `> 🧠 ${drThinking.value}\n\n` : '') +
                '---\n'
              assistantMsg.content = header + data.content
              messages.value = [...messages.value]
            }
          } else if (data.type === 'error') {
            error.value = data.message || 'Deep Research 错误'
          }
        }
        loadSessions()
        return
      }

      for await (const data of chatApi.chatTextStream(
        text,
        currentSessionId.value,
        ttsEnabled.value
      )) {
        if (data.type === 'session') {
          currentSessionId.value = data.session_id
        } else if (data.type === 'text') {
          assistantMsg.content += data.content || ''
          messages.value = [...messages.value]
        } else if (data.type === 'audio' && onAudio) {
          onAudio(data.audio_base64)
        } else if (data.type === 'done') {
          // finish
        } else if (data.type === 'error') {
          error.value = data.message || '对话错误'
        }
      }
      // 刷新会话列表
      loadSessions()
    } catch (e: any) {
      error.value = e.message
    } finally {
      isStreaming.value = false
    }
  }

  async function sendVoice(blob: Blob, onAudio?: (base64: string) => void) {
    if (isStreaming.value) return
    const userMsg: Message = {
      id: Date.now(),
      session_id: currentSessionId.value || 0,
      role: 'user',
      content: '语音识别中…',
      created_at: new Date().toISOString(),
    }
    messages.value.push(userMsg)
    let assistantMsg: Message | null = null
    isStreaming.value = true
    try {
      for await (const data of chatApi.chatVoiceStream(
        blob,
        currentSessionId.value,
        ttsEnabled.value
      )) {
        if (data.type === 'asr') {
          userMsg.content = data.content || ''
          if (data.session_id) currentSessionId.value = data.session_id
          assistantMsg = {
            id: Date.now() + 1,
            session_id: currentSessionId.value || 0,
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
          }
          messages.value.push(assistantMsg)
        } else if (data.type === 'text' && assistantMsg) {
          assistantMsg.content += data.content || ''
          messages.value = [...messages.value]
        } else if (data.type === 'audio' && onAudio) {
          onAudio(data.audio_base64)
        } else if (data.type === 'error') {
          error.value = data.message || '错误'
        }
      }
      loadSessions()
    } catch (e: any) {
      error.value = e.message
    } finally {
      isStreaming.value = false
    }
  }

  return {
    sessions,
    currentSessionId,
    messages,
    isLoadingSessions,
    isStreaming,
    error,
    ttsEnabled,
    deepResearchMode,
    drSteps,
    drThinking,
    loadSessions,
    selectSession,
    newSession,
    deleteSession,
    sendText,
    sendVoice,
  }
})
