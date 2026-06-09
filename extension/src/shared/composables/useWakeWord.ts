import { ref } from 'vue'
import { useRecorder } from './useRecorder'
import { detectWakeWord } from '../api/chat'

/**
 * 唤醒词监听：每 3 秒录一段，发送到后端检测
 */
export function useWakeWord() {
  const enabled = ref(false)
  const detecting = ref(false)
  const lastText = ref('')
  let timer: number | null = null
  let recorder = useRecorder()

  async function start(wakeWord: string, onDetected: () => void) {
    if (enabled.value) return
    enabled.value = true
    await loop(wakeWord, onDetected)
  }

  async function loop(wakeWord: string, onDetected: () => void) {
    while (enabled.value) {
      try {
        await recorder.start()
        await new Promise((r) => (timer = window.setTimeout(r, 3000)))
        if (!enabled.value) {
          recorder.cancel()
          break
        }
        const blob = await recorder.stop()
        detecting.value = true
        const res = await detectWakeWord(blob, wakeWord)
        lastText.value = res.text
        detecting.value = false
        if (res.detected) {
          onDetected()
        }
      } catch (e) {
        detecting.value = false
        await new Promise((r) => setTimeout(r, 1000))
      }
    }
  }

  function stop() {
    enabled.value = false
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    recorder.cancel()
  }

  return { enabled, detecting, lastText, start, stop }
}
