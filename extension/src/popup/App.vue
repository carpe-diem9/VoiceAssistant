<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useAuthStore } from '@shared/stores/auth'
import { useSettingsStore } from '@shared/stores/settings'
import LoginView from './views/LoginView.vue'
import ChatView from './views/ChatView.vue'

const auth = useAuthStore()
const settings = useSettingsStore()

onMounted(async () => {
  await auth.init()
  await settings.init()
})

const showChat = computed(() => auth.isLoggedIn)
</script>

<template>
  <div class="popup-root">
    <ChatView v-if="showChat" />
    <LoginView v-else />
  </div>
</template>

<style>
.popup-root { width:100%; height:100%; display:flex; flex-direction:column; background:#f5f7fa; }
</style>
