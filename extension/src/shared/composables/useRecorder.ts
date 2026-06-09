import { ref } from 'vue'

/**
 * 浏览器录音 composable
 * 录制 WebM/Opus（浏览器默认），停止时通过 WebAudio 解码 + 重采样为
 * 16kHz / 单声道 / 16bit PCM WAV，返回标准 audio/wav Blob，
 * 保证后端 ASR 管线可直接解析（后端依据 filename .wav 走 WAV 分支）。
 */
export function useRecorder() {
  const isRecording = ref(false)
  const error = ref<string>('')
  let mediaStream: MediaStream | null = null
  let mediaRecorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  // 用于实时音量检测（VAD 自动停止）
  let analyserCtx: AudioContext | null = null
  let analyserNode: AnalyserNode | null = null
  let analyserBuf: Uint8Array | null = null

  async function start() {
    if (isRecording.value) return
    error.value = ''
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      let mime = 'audio/webm;codecs=opus'
      if (!MediaRecorder.isTypeSupported(mime)) mime = 'audio/webm'
      if (!MediaRecorder.isTypeSupported(mime)) mime = 'audio/ogg'
      if (!MediaRecorder.isTypeSupported(mime)) mime = ''
      mediaRecorder = mime
        ? new MediaRecorder(mediaStream, { mimeType: mime })
        : new MediaRecorder(mediaStream)
      chunks = []
      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data)
      }
      // 在同一 stream 上搭建音量分析节点
      try {
        const Ctx: typeof AudioContext =
          (window as any).AudioContext || (window as any).webkitAudioContext
        if (Ctx) {
          analyserCtx = new Ctx()
          const src = analyserCtx.createMediaStreamSource(mediaStream)
          analyserNode = analyserCtx.createAnalyser()
          analyserNode.fftSize = 1024
          src.connect(analyserNode)
          analyserBuf = new Uint8Array(analyserNode.fftSize)
        }
      } catch {
        // 分析节点创建失败不影响录音本身
        analyserCtx = null
        analyserNode = null
        analyserBuf = null
      }
      mediaRecorder.start()
      isRecording.value = true
    } catch (e: any) {
      const name: string = e?.name || ''
      const raw: string = e?.message || String(e)
      let msg = raw
      if (name === 'NotAllowedError' || /dismissed|denied|Permission/i.test(raw)) {
        msg =
          '麦克风权限被拒绝或关闭。请在 chrome://settings/content/microphone 中允许本扩展/当前网站，或点击地址栏左侧的锁头图标开启麦克风，然后重试。'
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        msg = '未检测到可用麦克风设备'
      } else if (name === 'NotReadableError') {
        msg = '麦克风被其他应用占用'
      } else if (!raw) {
        msg = '麦克风访问失败'
      }
      error.value = msg
      const err: any = new Error(msg)
      err.name = name
      throw err
    }
  }

  function stop(): Promise<Blob> {
    return new Promise((resolve, reject) => {
      if (!mediaRecorder || !isRecording.value) {
        reject(new Error('录音未开始'))
        return
      }
      mediaRecorder.onstop = async () => {
        const rawBlob = new Blob(chunks, {
          type: mediaRecorder?.mimeType || 'audio/webm',
        })
        mediaStream?.getTracks().forEach((t) => t.stop())
        mediaStream = null
        mediaRecorder = null
        isRecording.value = false
        disposeAnalyser()
        try {
          const wav = await encodeBlobToWav(rawBlob, 16000)
          resolve(wav)
        } catch (e: any) {
          // 解码失败兼底：仍返回原始 blob（后端大概率解析失败，但不应阻塞）
          console.warn('[recorder] 转 WAV 失败，回退原始 blob:', e)
          resolve(rawBlob)
        }
      }
      mediaRecorder.stop()
    })
  }

  function cancel() {
    try {
      mediaRecorder?.stop()
    } catch {
      /* noop */
    }
    mediaStream?.getTracks().forEach((t) => t.stop())
    mediaStream = null
    mediaRecorder = null
    isRecording.value = false
    disposeAnalyser()
  }

  function disposeAnalyser() {
    try {
      analyserCtx?.close()
    } catch {
      /* noop */
    }
    analyserCtx = null
    analyserNode = null
    analyserBuf = null
  }

  /** 获取当前瞬时音量 RMS（0~1），未录音或不支持返回 0 */
  function getVolumeLevel(): number {
    if (!analyserNode || !analyserBuf) return 0
    // 调用前用独立 ArrayBuffer 的临时 buf，规避 TS 对 SharedArrayBuffer 的类型校验
    const tmp = new Uint8Array(analyserBuf.length)
    analyserNode.getByteTimeDomainData(tmp)
    let sum = 0
    for (let i = 0; i < tmp.length; i++) {
      const v = (tmp[i] - 128) / 128
      sum += v * v
    }
    return Math.sqrt(sum / tmp.length)
  }

  return { isRecording, error, start, stop, cancel, getVolumeLevel }
}

// ============ 工具：WebM/Opus Blob -> 16k/mono/16bit WAV Blob ============

async function encodeBlobToWav(blob: Blob, targetSampleRate = 16000): Promise<Blob> {
  const arrayBuffer = await blob.arrayBuffer()
  // Safari 下 AudioContext 在 window 上；Chrome/Firefox 均有
  const Ctx: typeof AudioContext =
    (window as any).AudioContext || (window as any).webkitAudioContext
  if (!Ctx) throw new Error('当前浏览器不支持 AudioContext')
  const audioCtx = new Ctx()

  // decodeAudioData 接收 ArrayBuffer；不同浏览器参数签名略有差异
  const decoded: AudioBuffer = await new Promise((resolve, reject) => {
    try {
      const p = (audioCtx as any).decodeAudioData(arrayBuffer.slice(0), resolve, reject)
      if (p && typeof (p as Promise<AudioBuffer>).then === 'function') {
        ;(p as Promise<AudioBuffer>).then(resolve, reject)
      }
    } catch (e) {
      reject(e)
    }
  })

  // 混合多声道为单声道 Float32
  const mono = mixdownToMono(decoded)

  // 重采样到 targetSampleRate（用 OfflineAudioContext，兼容性最好）
  const resampled = await resampleMono(mono, decoded.sampleRate, targetSampleRate)

  try {
    await audioCtx.close()
  } catch {
    /* ignore */
  }

  const wavBuffer = encodeWav(resampled, targetSampleRate)
  return new Blob([wavBuffer], { type: 'audio/wav' })
}

function mixdownToMono(buffer: AudioBuffer): Float32Array {
  const ch = buffer.numberOfChannels
  const length = buffer.length
  if (ch === 1) return buffer.getChannelData(0)
  const out = new Float32Array(length)
  for (let c = 0; c < ch; c++) {
    const data = buffer.getChannelData(c)
    for (let i = 0; i < length; i++) out[i] += data[i] / ch
  }
  return out
}

async function resampleMono(
  samples: Float32Array,
  inRate: number,
  outRate: number,
): Promise<Float32Array> {
  if (inRate === outRate) return samples
  const OfflineCtx: typeof OfflineAudioContext =
    (window as any).OfflineAudioContext || (window as any).webkitOfflineAudioContext
  if (!OfflineCtx) {
    // 简易线性插值降采样兜底
    const ratio = inRate / outRate
    const outLen = Math.floor(samples.length / ratio)
    const out = new Float32Array(outLen)
    for (let i = 0; i < outLen; i++) {
      const idx = i * ratio
      const lo = Math.floor(idx)
      const hi = Math.min(lo + 1, samples.length - 1)
      const frac = idx - lo
      out[i] = samples[lo] * (1 - frac) + samples[hi] * frac
    }
    return out
  }
  const duration = samples.length / inRate
  const outLen = Math.ceil(duration * outRate)
  const offline = new OfflineCtx(1, outLen, outRate)
  const buf = offline.createBuffer(1, samples.length, inRate)
  // 拷贝到独立 ArrayBuffer 上，避免 SharedArrayBuffer 类型冲突
  const monoCopy = new Float32Array(samples.length)
  monoCopy.set(samples)
  buf.copyToChannel(monoCopy, 0)
  const src = offline.createBufferSource()
  src.buffer = buf
  src.connect(offline.destination)
  src.start(0)
  const rendered = await offline.startRendering()
  return rendered.getChannelData(0)
}

function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const byteLen = 44 + samples.length * 2
  const buffer = new ArrayBuffer(byteLen)
  const view = new DataView(buffer)

  // RIFF header
  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, byteLen - 8, true)
  writeAscii(view, 8, 'WAVE')

  // fmt chunk
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true) // PCM chunk size
  view.setUint16(20, 1, true) // format = 1 (PCM)
  view.setUint16(22, 1, true) // channels = 1
  view.setUint32(24, sampleRate, true) // sample rate
  view.setUint32(28, sampleRate * 2, true) // byte rate (mono * 16bit)
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample

  // data chunk
  writeAscii(view, 36, 'data')
  view.setUint32(40, samples.length * 2, true)

  // 写入 PCM 16bit LE
  let offset = 44
  for (let i = 0; i < samples.length; i++) {
    let s = samples[i]
    if (s > 1) s = 1
    else if (s < -1) s = -1
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    offset += 2
  }
  return buffer
}

function writeAscii(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
}
