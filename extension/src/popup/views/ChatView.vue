<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatDotRound,
  Microphone,
  Setting,
  Delete,
  Plus,
  Expand,
  Menu as MenuIcon,
  SwitchButton,
  Promotion,
  Close,
} from '@element-plus/icons-vue'
import { marked } from 'marked'
import { useAuthStore } from '@shared/stores/auth'
import { useChatStore } from '@shared/stores/chat'
import { useSettingsStore } from '@shared/stores/settings'
import { useRecorder } from '@shared/composables/useRecorder'
import { useTTSPlayer } from '@shared/composables/useTTSPlayer'
import { useWakeWord } from '@shared/composables/useWakeWord'

const auth = useAuthStore()
const chat = useChatStore()
const settings = useSettingsStore()
const recorder = useRecorder()
const tts = useTTSPlayer()
const wake = useWakeWord()

const input = ref('')
const drawerOpen = ref(false)
const listRef = ref<HTMLElement | null>(null)
const recordLevel = ref(0) // 0~1，用于录音时脉冲动画强度
let levelTimer: number | null = null

onMounted(async () => {
  await chat.loadSessions()
  // 保持上一次对话：未选中时自动加载最近的一条会话（后端按 updated_at DESC 返回）
  if (chat.sessions.length > 0 && chat.currentSessionId == null) {
    await chat.selectSession(chat.sessions[0].id)
  }
  // 唤醒词：如用户在设置里启用，popup 打开期间启动监听
  try {
    await settings.init()
  } catch {
    /* noop */
  }
  if (settings.wakeWordEnabled && settings.wakeWord) {
    wake.start(settings.wakeWord, onWakeDetected).catch((e) => {
      console.warn('唤醒词启动失败:', e)
    })
  }
})

onUnmounted(() => {
  try {
    wake.stop()
  } catch {
    /* noop */
  }
  if (levelTimer) {
    clearInterval(levelTimer)
    levelTimer = null
  }
})

// 设置里开关变化实时响应
watch(
  () => [settings.wakeWordEnabled, settings.wakeWord] as const,
  ([enabled, word]) => {
    if (enabled && word) {
      if (!wake.enabled.value) wake.start(word, onWakeDetected).catch(() => {})
    } else {
      if (wake.enabled.value) wake.stop()
    }
  },
)

watch(
  () => chat.messages.length,
  async () => {
    await nextTick()
    listRef.value?.scrollTo({ top: listRef.value.scrollHeight, behavior: 'smooth' })
  },
)

// 录音时每 80ms 取一次音量，供底部脉冲动画使用
watch(
  () => recorder.isRecording.value,
  (rec) => {
    if (rec) {
      if (levelTimer) clearInterval(levelTimer)
      levelTimer = window.setInterval(() => {
        recordLevel.value = recorder.getVolumeLevel()
      }, 80)
    } else {
      if (levelTimer) {
        clearInterval(levelTimer)
        levelTimer = null
      }
      recordLevel.value = 0
    }
  },
)

// ============ 唤醒词：VAD 自动停止录音 ============

async function onWakeDetected() {
  ElMessage.success('已唤醒，请说话')
  wake.stop()
  if (chat.isStreaming) return
  if (recorder.isRecording.value) return
  try {
    const blob = await recordUntilSilence()
    if (blob) await chat.sendVoice(blob, (b64) => tts.enqueue(b64))
  } catch (e: any) {
    ElMessage.error(e?.message || '唤醒后录音失败')
  } finally {
    if (settings.wakeWordEnabled && settings.wakeWord) {
      wake.start(settings.wakeWord, onWakeDetected).catch(() => {})
    }
  }
}

/**
 * VAD 自动结束录音：
 *  - 启动录音后轮询实时音量
 *  - 检测到用户已开口 + 连续 1.5s 静音 → 自动结束
 *  - 最长 20s 强制结束，避免无限录
 *  - 开头 500ms 热身（避开 AudioContext 启动抖动）
 *  - 如果 6s 内完全没检测到人声，视为误唤醒，直接取消
 */
async function recordUntilSilence(): Promise<Blob | null> {
  const SILENCE_MS = 1500
  const MAX_MS = 20000
  const WARMUP_MS = 500
  const NO_VOICE_MAX = 6000
  const THRESHOLD = 0.025

  await recorder.start()
  const startT = Date.now()
  let lastVoiceT = 0

  return await new Promise<Blob | null>((resolve) => {
    let done = false
    const tick = async () => {
      if (done) return
      const now = Date.now()
      const elapsed = now - startT
      const level = recorder.getVolumeLevel()
      if (level > THRESHOLD) lastVoiceT = now
      const hasSpoken = lastVoiceT > 0
      const silenceDur = hasSpoken ? now - lastVoiceT : 0
      const warmupOver = elapsed >= WARMUP_MS

      const byMax = elapsed >= MAX_MS
      const bySilence = warmupOver && hasSpoken && silenceDur >= SILENCE_MS
      const byNoVoice = !hasSpoken && elapsed >= NO_VOICE_MAX

      if (byMax || bySilence || byNoVoice) {
        done = true
        if (byNoVoice) {
          // 没听到人声，取消而不发送
          recorder.cancel()
          ElMessage.info('未检测到语音，已取消')
          resolve(null)
          return
        }
        try {
          const blob = await recorder.stop()
          resolve(blob)
        } catch {
          resolve(null)
        }
        return
      }
      setTimeout(tick, 100)
    }
    tick()
  })
}

// ============ 输入框发送 / 手动录音 ============

async function send() {
  const text = input.value.trim()
  if (!text) return
  input.value = ''
  await chat.sendText(text, (b64) => tts.enqueue(b64))
}

async function toggleRecord() {
  if (chat.isStreaming) {
    ElMessage.warning('等待上一条回复完成')
    return
  }
  if (recorder.isRecording.value) {
    try {
      const blob = await recorder.stop()
      await chat.sendVoice(blob, (b64) => tts.enqueue(b64))
    } catch (e: any) {
      ElMessage.error(e.message || '录音失败')
    }
  } else {
    try {
      await recorder.start()
    } catch (e: any) {
      const raw = e?.message || '麦克风访问失败'
      const isPermission = /麦克风权限|拒绝|dismissed|denied|NotAllowed|Permission/i.test(raw)
      if (isPermission) {
        try {
          await ElMessageBox.confirm(
            'Chrome 扩展弹窗无法直接请求麦克风权限（弹窗失焦后会立即关闭）。\n' +
              '\n请按下方按钮打开授权页，在那里点击浏览器弹出的「允许」后，本扩展所有页面即可使用麦克风。\n' +
              '\n授权完成后回到本弹窗再次点击麦克风按钮即可开始录音。',
            '需要麦克风授权',
            {
              confirmButtonText: '打开授权页',
              cancelButtonText: '稍后',
              type: 'warning',
              customClass: 'va-mic-dialog',
            },
          )
          try {
            await chrome.tabs.create({
              url: chrome.runtime.getURL('src/permissions/index.html'),
            })
          } catch {
            ElMessage.warning('打开授权页失败，请手动在新标签访问扩展的 permissions 页')
          }
        } catch {
          /* 用户取消 */
        }
      } else {
        ElMessage({
          message: raw,
          type: 'error',
          duration: 8000,
          showClose: true,
        })
      }
    }
  }
}

// ============ 会话 / 其它 ============

async function selectSession(id: number) {
  drawerOpen.value = false
  await chat.selectSession(id)
}

async function newChat() {
  drawerOpen.value = false
  await chat.newSession()
}

async function delSession(id: number) {
  try {
    await ElMessageBox.confirm('删除该会话？', '提示', { type: 'warning' })
    await chat.deleteSession(id)
    ElMessage.success('已删除')
  } catch {
    /* 取消 */
  }
}

function toggleTts() {
  chat.ttsEnabled = !chat.ttsEnabled
  if (!chat.ttsEnabled) tts.stop()
}

function toggleDeepResearch() {
  chat.deepResearchMode = !chat.deepResearchMode
  if (chat.deepResearchMode) {
    // Deep Research 模式下默认关闭 TTS（结果较长，不适合朗读）
    chat.ttsEnabled = false
    tts.stop()
    ElMessage.success('已开启 Deep Research 模式')
  } else {
    ElMessage.info('已关闭 Deep Research 模式')
  }
}

function openSidePanel() {
  chrome.tabs?.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]?.windowId != null) {
      chrome.sidePanel?.open({ windowId: tabs[0].windowId }).catch(() => {
        ElMessage.info('请从扩展图标右键打开侧边栏')
      })
    }
  })
}

function openOptions() {
  chrome.runtime.openOptionsPage?.()
}

async function logout() {
  try {
    await ElMessageBox.confirm('确定退出登录？', '提示', { type: 'warning' })
    await auth.logout()
  } catch {
    /* 取消 */
  }
}

function renderMd(text: string) {
  try {
    return marked.parse(text || '', { async: false }) as string
  } catch {
    return text
  }
}

function fmtTime(t?: string) {
  if (!t) return ''
  try {
    const d = new Date(t)
    const now = new Date()
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    if (sameDay) return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return t
  }
}

const currentTitle = computed(() => {
  const s = chat.sessions.find((x) => x.id === chat.currentSessionId)
  return s?.title || '新对话'
})

const pulseScale = computed(() => 1 + Math.min(recordLevel.value * 6, 0.6))
</script>

<template>
  <div class="chat-root">
    <!-- 顶栏 -->
    <header class="top-bar">
      <button class="icon-btn" @click="drawerOpen = true" title="会话列表">
        <el-icon :size="18"><MenuIcon /></el-icon>
      </button>
      <div class="title-wrap">
        <div class="title">{{ currentTitle }}</div>
        <div class="subtitle">
          <span v-if="wake.enabled.value" class="dot-green" />
          <span v-if="wake.enabled.value">正在监听「{{ settings.wakeWord }}」</span>
          <span v-else>AI 语音助理</span>
        </div>
      </div>
      <div class="actions">
        <button class="icon-btn" @click="openSidePanel" title="展开侧边栏">
          <el-icon :size="16"><Expand /></el-icon>
        </button>
        <button class="icon-btn" @click="openOptions" title="设置">
          <el-icon :size="16"><Setting /></el-icon>
        </button>
        <button class="icon-btn" @click="logout" title="退出登录">
          <el-icon :size="16"><SwitchButton /></el-icon>
        </button>
      </div>
    </header>

    <!-- 消息列表 -->
    <div class="msg-list" ref="listRef">
      <div v-if="chat.messages.length === 0" class="empty">
        <div class="empty-icon">
          <el-icon :size="46"><ChatDotRound /></el-icon>
        </div>
        <div class="empty-title">你好，我是 AI 语音助理</div>
        <div class="empty-sub">可以直接输入文字，或点击下方麦克风说话</div>
        <div v-if="settings.wakeWordEnabled && settings.wakeWord" class="empty-tip">
          💡 试试说 "{{ settings.wakeWord }}" 来唤醒我
        </div>
      </div>

      <template v-else>
        <div
          v-for="m in chat.messages"
          :key="m.id"
          class="msg-row"
          :class="{ 'is-user': m.role === 'user' }"
        >
          <div class="avatar">
            <span v-if="m.role === 'user'">我</span>
            <span v-else>AI</span>
          </div>
          <div class="bubble-wrap">
            <div class="bubble" v-html="renderMd(m.content || '…')" />
            <div class="meta">{{ fmtTime(m.created_at) }}</div>
          </div>
        </div>
      </template>
    </div>

    <!-- 录音状态条 -->
    <transition name="fade-slide">
      <div v-if="recorder.isRecording.value" class="record-strip">
        <div class="pulse" :style="{ transform: `scale(${pulseScale})` }" />
        <div class="record-text">
          正在聆听<span class="dots">…</span>
        </div>
        <div class="record-tip">再次点击麦克风结束</div>
      </div>
    </transition>

    <!-- 底部输入区 -->
    <footer class="bottom-bar">
      <button
        class="pill-btn"
        :class="{ on: chat.deepResearchMode }"
        @click="toggleDeepResearch"
        :title="chat.deepResearchMode ? 'Deep Research 已开启，点击关闭' : '开启 Deep Research 深入调研模式'"
      >
        🔬
      </button>
      <button
        class="pill-btn"
        :class="{ on: chat.ttsEnabled }"
        @click="toggleTts"
        :title="chat.ttsEnabled ? '已开启语音回答' : '点击开启语音回答'"
      >
        {{ chat.ttsEnabled ? '🔊' : '📝' }}
      </button>
      <div class="input-wrap">
        <input
          v-model="input"
          :placeholder="chat.deepResearchMode ? '提问后将进行多步深入调研…' : '发送消息，或点麦克风说话…'"
          class="input"
          :disabled="chat.isStreaming"
          @keyup.enter="send"
        />
      </div>
      <button
        class="mic-btn"
        :class="{ recording: recorder.isRecording.value }"
        @click="toggleRecord"
        title="点击开始/结束录音"
      >
        <el-icon :size="18">
          <Close v-if="recorder.isRecording.value" />
          <Microphone v-else />
        </el-icon>
      </button>
      <button
        class="send-btn"
        :disabled="chat.isStreaming || !input.trim()"
        @click="send"
        title="发送"
      >
        <el-icon :size="18"><Promotion /></el-icon>
      </button>
    </footer>

    <!-- 会话抽屉 -->
    <el-drawer
      v-model="drawerOpen"
      title="会话列表"
      direction="ltr"
      size="300px"
      :with-header="true"
    >
      <button class="new-chat-btn" @click="newChat">
        <el-icon :size="16"><Plus /></el-icon>
        <span>新建对话</span>
      </button>
      <div
        v-if="chat.isLoadingSessions && chat.sessions.length === 0"
        class="loading-text"
      >
        加载中…
      </div>
      <div v-else-if="chat.sessions.length === 0" class="empty-sessions">
        暂无会话
      </div>
      <div v-else class="session-list">
        <div
          v-for="s in chat.sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === chat.currentSessionId }"
          @click="selectSession(s.id)"
        >
          <div class="session-main">
            <div class="session-title">{{ s.title }}</div>
            <div class="session-time">{{ fmtTime(s.updated_at) }}</div>
          </div>
          <button
            class="session-del"
            @click.stop="delSession(s.id)"
            title="删除"
          >
            <el-icon :size="14"><Delete /></el-icon>
          </button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.chat-root {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #f8faff 0%, #eef2ff 100%);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  color: #1f2937;
}

/* 顶栏 */
.top-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
  z-index: 2;
}
.title-wrap { flex: 1; min-width: 0; }
.title {
  font-weight: 600;
  font-size: 15px;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.subtitle {
  font-size: 11px;
  opacity: 0.85;
  margin-top: 1px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.dot-green {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.7);
  animation: va-pulse 1.6s infinite;
}
@keyframes va-pulse {
  0% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.7); }
  70% { box-shadow: 0 0 0 6px rgba(52, 211, 153, 0); }
  100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
}
.actions { display: flex; gap: 2px; }
.icon-btn {
  width: 30px;
  height: 30px;
  border: none;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.icon-btn:hover { background: rgba(255, 255, 255, 0.22); }

/* 消息列表 */
.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 14px 12px 12px;
  scroll-behavior: smooth;
}
.msg-list::-webkit-scrollbar { width: 6px; }
.msg-list::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 3px; }

/* 空状态 */
.empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  text-align: center;
  padding: 0 24px;
}
.empty-icon {
  width: 72px;
  height: 72px;
  border-radius: 20px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.35);
  margin-bottom: 14px;
}
.empty-title { font-size: 16px; font-weight: 600; color: #1f2937; }
.empty-sub { font-size: 13px; color: #6b7280; margin-top: 6px; }
.empty-tip {
  margin-top: 14px;
  font-size: 12px;
  background: #fff;
  border: 1px dashed #c4b5fd;
  color: #6d28d9;
  padding: 6px 12px;
  border-radius: 999px;
}

/* 消息气泡 */
.msg-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  align-items: flex-start;
}
.msg-row.is-user { flex-direction: row-reverse; }
.avatar {
  width: 30px;
  height: 30px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  background: linear-gradient(135deg, #10b981, #06b6d4);
  color: #fff;
  box-shadow: 0 2px 6px rgba(6, 182, 212, 0.3);
}
.msg-row.is-user .avatar {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.3);
}
.bubble-wrap { max-width: 78%; display: flex; flex-direction: column; }
.msg-row.is-user .bubble-wrap { align-items: flex-end; }
.bubble {
  padding: 10px 14px;
  background: #fff;
  border-radius: 14px 14px 14px 4px;
  font-size: 13.5px;
  line-height: 1.65;
  word-break: break-word;
  box-shadow: 0 2px 8px rgba(17, 24, 39, 0.06);
  border: 1px solid #eef2ff;
}
.msg-row.is-user .bubble {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: #fff;
  border-radius: 14px 14px 4px 14px;
  border: none;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}
.bubble :deep(p) { margin: 0; }
.bubble :deep(p + p) { margin-top: 8px; }
.bubble :deep(pre) {
  background: rgba(17, 24, 39, 0.06);
  padding: 8px 10px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 12px;
}
.msg-row.is-user .bubble :deep(pre) { background: rgba(255, 255, 255, 0.15); }
.bubble :deep(code) {
  font-family: Menlo, Consolas, monospace;
  font-size: 12px;
}
/* Markdown 扩充样式（主要用于 Deep Research / GPT / Gemini 返回的结构化文本）*/
.bubble :deep(h1),
.bubble :deep(h2),
.bubble :deep(h3),
.bubble :deep(h4) {
  margin: 10px 0 6px;
  font-weight: 600;
  line-height: 1.35;
  color: #111827;
}
.bubble :deep(h1) { font-size: 16px; }
.bubble :deep(h2) { font-size: 15px; }
.bubble :deep(h3) { font-size: 14px; }
.bubble :deep(h4) { font-size: 13.5px; }
.msg-row.is-user .bubble :deep(h1),
.msg-row.is-user .bubble :deep(h2),
.msg-row.is-user .bubble :deep(h3),
.msg-row.is-user .bubble :deep(h4) { color: #fff; }
.bubble :deep(ul),
.bubble :deep(ol) {
  margin: 6px 0;
  padding-left: 22px;
}
.bubble :deep(li) { margin: 2px 0; }
.bubble :deep(li > p) { margin: 0; }
.bubble :deep(strong) { font-weight: 600; }
.bubble :deep(em) { font-style: italic; }
.bubble :deep(a) { color: #6366f1; text-decoration: underline; word-break: break-all; }
.msg-row.is-user .bubble :deep(a) { color: #fde68a; }
.bubble :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 10px;
  border-left: 3px solid #c4b5fd;
  background: rgba(139, 92, 246, 0.06);
  color: #4b5563;
  border-radius: 4px;
}
.msg-row.is-user .bubble :deep(blockquote) {
  border-left-color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}
.bubble :deep(hr) {
  border: none;
  border-top: 1px dashed #d1d5db;
  margin: 10px 0;
}
.msg-row.is-user .bubble :deep(hr) { border-top-color: rgba(255, 255, 255, 0.45); }
.bubble :deep(table) {
  border-collapse: collapse;
  font-size: 12.5px;
  margin: 8px 0;
}
.bubble :deep(th),
.bubble :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 4px 8px;
}
.bubble :deep(th) { background: #f9fafb; font-weight: 600; }
.meta { font-size: 10.5px; color: #9ca3af; margin-top: 3px; padding: 0 6px; }

/* 录音状态条 */
.record-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  margin: 0 12px;
  background: linear-gradient(135deg, #fecaca, #fca5a5);
  color: #7f1d1d;
  border-radius: 12px;
  font-size: 12.5px;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.2);
}
.pulse {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #dc2626;
  transition: transform 0.08s;
  box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.7);
  animation: va-pulse-red 1.4s infinite;
}
@keyframes va-pulse-red {
  0% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.6); }
  70% { box-shadow: 0 0 0 10px rgba(220, 38, 38, 0); }
  100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
}
.record-text { font-weight: 600; }
.record-tip { margin-left: auto; font-size: 11px; opacity: 0.8; }
.dots { display: inline-block; animation: va-dots 1.2s infinite; }
@keyframes va-dots {
  0%, 20% { opacity: 0; }
  50% { opacity: 1; }
  80%, 100% { opacity: 0; }
}

/* fade-slide 过渡 */
.fade-slide-enter-active, .fade-slide-leave-active {
  transition: all 0.22s ease;
}
.fade-slide-enter-from, .fade-slide-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

/* 底部输入栏 */
.bottom-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 12px;
  background: #fff;
  border-top: 1px solid #eef2ff;
}
.pill-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: #f3f4f6;
  color: #1f2937;
  cursor: pointer;
  font-size: 15px;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.pill-btn:hover { background: #e5e7eb; }
.pill-btn.on {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  box-shadow: 0 4px 10px rgba(99, 102, 241, 0.35);
}
.input-wrap { flex: 1; }
.input {
  width: 100%;
  height: 36px;
  padding: 0 14px;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  outline: none;
  font-size: 13.5px;
  background: #f9fafb;
  transition: all 0.15s;
  box-sizing: border-box;
  color: #1f2937;
}
.input:focus {
  border-color: #8b5cf6;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15);
}
.input:disabled { opacity: 0.6; cursor: not-allowed; }
.mic-btn, .send-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  flex-shrink: 0;
}
.mic-btn {
  background: #f3f4f6;
  color: #4b5563;
}
.mic-btn:hover { background: #e5e7eb; }
.mic-btn.recording {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: #fff;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.4);
  animation: va-mic-pulse 1.2s infinite;
}
@keyframes va-mic-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}
.send-btn {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.45);
}
.send-btn:disabled {
  background: #cbd5e1;
  box-shadow: none;
  cursor: not-allowed;
}

/* 会话抽屉 */
.new-chat-btn {
  width: 100%;
  padding: 10px 14px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-bottom: 10px;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
  transition: all 0.15s;
}
.new-chat-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
}
.session-list { display: flex; flex-direction: column; gap: 4px; }
.session-item {
  position: relative;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  background: #f9fafb;
  border: 1px solid transparent;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.15s;
}
.session-item:hover { background: #f3f4f6; }
.session-item.active {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(139, 92, 246, 0.08));
  border-color: #c4b5fd;
}
.session-main { flex: 1; min-width: 0; }
.session-title {
  font-size: 13px;
  font-weight: 500;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-time {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 2px;
}
.session-del {
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.15s;
  flex-shrink: 0;
}
.session-item:hover .session-del { opacity: 1; }
.session-del:hover { background: #fee2e2; color: #dc2626; }
.loading-text, .empty-sessions {
  padding: 20px;
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
}
</style>
