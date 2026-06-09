<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@shared/stores/auth'
import { useSettingsStore } from '@shared/stores/settings'

const auth = useAuthStore()
const settings = useSettingsStore()

const voice = ref('Cherry')
const speed = ref(1.0)
const pitch = ref(1.0)
const volume = ref(50)
const llmModel = ref('qwen3.5-plus')
const asrModel = ref('qwen3-asr-flash')
const ttsModel = ref('qwen3-tts-instruct-flash')
const baseUrlInput = ref('')
const wakeWordInput = ref('')

// 音色描述映射（只保留一男一女）
const VOICE_LABELS: Record<string, string> = {
  Cherry: '温柔女声',
  Ethan: '沉稳男声',
}
function voiceLabel(v: string): string {
  return VOICE_LABELS[v] || v
}

onMounted(async () => {
  await settings.init()
  await auth.init()
  baseUrlInput.value = settings.baseUrl
  wakeWordInput.value = settings.wakeWord

  if (auth.isLoggedIn) {
    await settings.loadFromServer()
    if (settings.tts) {
      voice.value = settings.tts.voice
      speed.value = settings.tts.speed
      pitch.value = settings.tts.pitch
      volume.value = settings.tts.volume
    }
    llmModel.value = settings.currentModel
    asrModel.value = settings.currentASRModel
    ttsModel.value = settings.currentTTSModel
  }
})

async function saveServer() {
  await settings.setBaseUrl(baseUrlInput.value.trim() || 'http://127.0.0.1:8000')
  ElMessage.success('服务器地址已保存')
}

async function saveTTS() {
  if (!auth.isLoggedIn) {
    ElMessage.warning('请先在扩展弹窗中登录')
    return
  }
  try {
    await settings.saveTTS({
      voice: voice.value,
      speed: speed.value,
      pitch: pitch.value,
      volume: volume.value,
    })
    ElMessage.success('语音设置已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function saveLLMModel() {
  if (!auth.isLoggedIn) {
    ElMessage.warning('请先在扩展弹窗中登录')
    return
  }
  const m = (llmModel.value || '').trim()
  if (!m) {
    ElMessage.warning('请选择或输入语言模型')
    return
  }
  try {
    await settings.saveModel(m)
    ElMessage.success(`语言模型已切换为 ${m}`)
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function saveASRModel() {
  if (!auth.isLoggedIn) {
    ElMessage.warning('请先在扩展弹窗中登录')
    return
  }
  const m = (asrModel.value || '').trim()
  if (!m) { ElMessage.warning('请选择 ASR 模型'); return }
  try {
    await settings.saveASRModel(m)
    ElMessage.success(`ASR 模型已切换为 ${m}`)
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function saveTTSModel() {
  if (!auth.isLoggedIn) {
    ElMessage.warning('请先在扩展弹窗中登录')
    return
  }
  const m = (ttsModel.value || '').trim()
  if (!m) { ElMessage.warning('请选择 TTS 模型'); return }
  try {
    await settings.saveTTSModel(m)
    ElMessage.success(`TTS 模型已切换为 ${m}`)
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function saveWakeWord() {
  const v = wakeWordInput.value.trim()
  if (!v) {
    ElMessage.warning('唤醒词不能为空')
    return
  }
  await settings.setWakeWord(v)
  ElMessage.success(`唤醒词已设置为"${v}"`)
}

async function toggleWakeWord(v: boolean) {
  await settings.setWakeWordEnabled(v)
}

async function toggleBall(v: boolean) {
  await settings.setFloatingBallEnabled(v)
  if (v) {
    // 兜底：直接让 service worker 执行一次注入，不依赖 storage.onChanged 是否能唤醒 SW
    try {
      const resp: any = await chrome.runtime.sendMessage({ type: 'forceInjectFloatingBall' })
      if (resp && resp.ok) {
        ElMessage.success(`悬浮球已开启，已注入 ${resp.ok} 个页面（跳过 ${resp.skip || 0} 个）`)
      } else {
        ElMessage.success('悬浮球已开启，请刷新需要使用的网页')
      }
    } catch (e: any) {
      ElMessage.warning('已开启，但自动注入失败，请刷新页面：' + (e?.message || e))
    }
  } else {
    ElMessage.info('悬浮球已关闭，刷新页面后完全卸载')
  }
}
</script>

<template>
  <div class="options-wrap">
    <h1>AI 语音助理 · 设置</h1>

    <el-card class="sec">
      <template #header><b>服务器</b></template>
      <el-form label-width="100px">
        <el-form-item label="后端地址">
          <el-input v-model="baseUrlInput" placeholder="http://127.0.0.1:8000" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveServer">保存地址</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="sec">
      <template #header><b>语音设置（TTS）</b></template>
      <el-form label-width="100px" v-loading="settings.loading">
        <el-form-item label="音色">
          <el-select v-model="voice" style="width:220px" placeholder="选择音色" class="select-right">
            <el-option
              v-for="v in settings.voices"
              :key="v"
              :label="voiceLabel(v)"
              :value="v"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="语速">
          <el-slider v-model="speed" :min="0.5" :max="2" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="音调">
          <el-slider v-model="pitch" :min="0.5" :max="2" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="音量">
          <el-slider v-model="volume" :min="0" :max="100" :step="1" show-input />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveTTS">保存语音设置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="sec">
      <template #header><b>语言模型</b></template>
      <el-form label-width="100px" v-loading="settings.loading">
        <el-form-item label="语言模型">
          <el-select
            v-model="llmModel"
            style="width:220px"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入模型名"
            no-data-text="暂无可用模型"
            class="select-right"
          >
            <el-option v-for="m in settings.models" :key="m" :label="m" :value="m" />
          </el-select>
          <el-button type="primary" style="margin-left:8px" @click="saveLLMModel">
            保存模型
          </el-button>
        </el-form-item>
        <el-form-item label="ASR 模型">
          <el-select
            v-model="asrModel"
            style="width:260px"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入 ASR 模型"
            no-data-text="暂无可用模型"
            class="select-right"
          >
            <el-option v-for="m in settings.asrModels" :key="m" :label="m" :value="m" />
          </el-select>
          <el-button type="primary" style="margin-left:8px" @click="saveASRModel">
            保存
          </el-button>
        </el-form-item>
        <el-form-item label="TTS 模型">
          <el-select
            v-model="ttsModel"
            style="width:260px"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入 TTS 模型"
            no-data-text="暂无可用模型"
            class="select-right"
          >
            <el-option v-for="m in settings.ttsModels" :key="m" :label="m" :value="m" />
          </el-select>
          <el-button type="primary" style="margin-left:8px" @click="saveTTSModel">
            保存
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="sec">
      <template #header><b>语音唤醒</b></template>
      <el-form label-width="100px">
        <el-form-item label="唤醒词">
          <el-input v-model="wakeWordInput" style="width:220px" />
          <el-button type="primary" style="margin-left:8px" @click="saveWakeWord">保存</el-button>
        </el-form-item>
        <el-form-item label="启用唤醒">
          <el-switch
            :model-value="settings.wakeWordEnabled"
            @change="toggleWakeWord($event as boolean)"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="sec">
      <template #header><b>网页悬浮球（无障碍朗读）</b></template>
      <el-form label-width="100px">
        <el-form-item label="开启悬浮球">
          <el-switch
            :model-value="settings.floatingBallEnabled"
            @change="toggleBall($event as boolean)"
          />
          <span class="hint">开启后在任意网页右下角出现悬浮按钮；朗读模式通过悬浮球菜单选择</span>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.options-wrap { max-width:760px; margin:0 auto; padding:24px; }
.options-wrap h1 { font-size:22px; margin:0 0 16px; }
.sec { margin-bottom:16px; }
.hint { margin-left:12px; color:#909399; font-size:12px; }
/* 下拉框选中后显示文本右对齐 */
.select-right :deep(.el-select__selected-item),
.select-right :deep(.el-select__placeholder),
.select-right :deep(input.el-input__inner) {
  text-align: right;
}
</style>
