import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister } from '../api/auth'
import { storageGet, storageSet, storageRemove, StorageKeys } from '../storage/chromeStorage'

export interface User {
  id: number
  username: string
  email?: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<User | null>(null)
  const loading = ref(false)
  const error = ref<string>('')

  const isLoggedIn = computed(() => !!token.value)

  async function init() {
    token.value = (await storageGet<string>(StorageKeys.TOKEN)) || null
    user.value = (await storageGet<User>(StorageKeys.USER)) || null
  }

  async function login(username: string, password: string) {
    loading.value = true
    error.value = ''
    try {
      const res = await apiLogin(username, password)
      token.value = res.access_token
      user.value = res.user
      await storageSet(StorageKeys.TOKEN, res.access_token)
      await storageSet(StorageKeys.USER, res.user)
      return true
    } catch (e: any) {
      error.value = e.message || '登录失败'
      return false
    } finally {
      loading.value = false
    }
  }

  async function register(username: string, password: string, email?: string) {
    loading.value = true
    error.value = ''
    try {
      const res = await apiRegister(username, password, email)
      token.value = res.access_token
      user.value = res.user
      await storageSet(StorageKeys.TOKEN, res.access_token)
      await storageSet(StorageKeys.USER, res.user)
      return true
    } catch (e: any) {
      error.value = e.message || '注册失败'
      return false
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    token.value = null
    user.value = null
    await storageRemove(StorageKeys.TOKEN)
    await storageRemove(StorageKeys.USER)
  }

  return { token, user, loading, error, isLoggedIn, init, login, register, logout }
})
