<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@shared/stores/auth'
import { ElMessage } from 'element-plus'

const auth = useAuthStore()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const email = ref('')

async function submit() {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  const ok =
    mode.value === 'login'
      ? await auth.login(username.value.trim(), password.value)
      : await auth.register(username.value.trim(), password.value, email.value || undefined)
  if (!ok) {
    ElMessage.error(auth.error || (mode.value === 'login' ? '登录失败' : '注册失败'))
  } else {
    ElMessage.success(mode.value === 'login' ? '登录成功' : '注册成功')
  }
}

function openOptions() {
  chrome.runtime.openOptionsPage?.()
}
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <h2>AI 语音助理</h2>
      <p class="sub">{{ mode === 'login' ? '登录以开始对话' : '注册新账号' }}</p>
      <el-input v-model="username" placeholder="用户名" class="field" clearable />
      <el-input
        v-model="password"
        placeholder="密码"
        type="password"
        show-password
        class="field"
        @keyup.enter="submit"
      />
      <el-input
        v-if="mode === 'register'"
        v-model="email"
        placeholder="邮箱（可选）"
        class="field"
        clearable
      />
      <el-button
        type="primary"
        class="field"
        :loading="auth.loading"
        @click="submit"
      >
        {{ mode === 'login' ? '登录' : '注册' }}
      </el-button>
      <div class="toggle">
        <a v-if="mode === 'login'" href="#" @click.prevent="mode = 'register'">还没有账号？去注册</a>
        <a v-else href="#" @click.prevent="mode = 'login'">已有账号，去登录</a>
      </div>
      <div class="toggle"><a href="#" @click.prevent="openOptions">服务器设置</a></div>
    </div>
  </div>
</template>

<style scoped>
.login-wrap { flex:1; display:flex; align-items:center; justify-content:center; padding:16px; }
.login-card { width:100%; background:#fff; border-radius:12px; padding:24px; box-shadow:0 2px 12px rgba(0,0,0,0.06); }
.login-card h2 { margin:0 0 4px; font-size:20px; text-align:center; }
.sub { margin:0 0 16px; color:#909399; font-size:13px; text-align:center; }
.field { margin-bottom:12px; width:100%; }
.toggle { text-align:center; font-size:12px; margin-top:8px; }
.toggle a { color:#409eff; text-decoration:none; }
</style>
