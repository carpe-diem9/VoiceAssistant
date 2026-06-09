import { ref } from 'vue'

/**
 * TTS 播放队列（base64 音频分片顺序播放）
 */
export function useTTSPlayer() {
  const isPlaying = ref(false)
  const queue: string[] = []
  let currentAudio: HTMLAudioElement | null = null

  function base64ToBlob(b64: string, mime = 'audio/wav'): Blob {
    const binStr = atob(b64)
    const len = binStr.length
    const bytes = new Uint8Array(len)
    for (let i = 0; i < len; i++) bytes[i] = binStr.charCodeAt(i)
    return new Blob([bytes], { type: mime })
  }

  function enqueue(base64: string) {
    queue.push(base64)
    if (!isPlaying.value) playNext()
  }

  function playNext() {
    const next = queue.shift()
    if (!next) {
      isPlaying.value = false
      return
    }
    isPlaying.value = true
    const blob = base64ToBlob(next)
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    currentAudio = audio
    audio.onended = () => {
      URL.revokeObjectURL(url)
      currentAudio = null
      playNext()
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      currentAudio = null
      playNext()
    }
    audio.play().catch(() => playNext())
  }

  function stop() {
    queue.length = 0
    if (currentAudio) {
      currentAudio.pause()
      currentAudio = null
    }
    isPlaying.value = false
  }

  return { isPlaying, enqueue, stop }
}
