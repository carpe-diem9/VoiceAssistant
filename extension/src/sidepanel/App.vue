<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useAuthStore } from '@shared/stores/auth'
import { useSettingsStore } from '@shared/stores/settings'
import LoginView from '../popup/views/LoginView.vue'
import ChatView from '../popup/views/ChatView.vue'

const auth = useAuthStore()
const settings = useSettingsStore()

onMounted(async () => {
  await auth.init()
  await settings.init()
})

const showChat = computed(() => auth.isLoggedIn)
</script>

<template>
  <div class="side-root">
    <ChatView v-if="showChat" />
    <LoginView v-else />
  </div>
</template>

<style>
.side-root { width:100%; height:100vh; display:flex; flex-direction:column; background:#f5f7fa; }
</style>
