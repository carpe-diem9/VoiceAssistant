/**
 * Content script：在任意网页注入悬浮球（Shadow DOM 隔离样式）
 * - 朗读整页原文 / LLM 总结朗读 / 点击元素朗读（可切换原文/总结）
 * - 通过 chrome.runtime.sendMessage 让 background 调后端 API
 */

interface ReadResult {
  ok: boolean
  data?: { text: string; audio_base64?: string; audio_format?: string }
  error?: string
}

type ReadStyle = 'read' | 'summary'

const FB_KEY = 'floating_ball_enabled'
const FB_POS_KEY = 'floating_ball_pos'
const FB_MENU_POS_KEY = 'floating_ball_menu_pos'

let rootEl: HTMLDivElement | null = null
let shadow: ShadowRoot | null = null
let menuOpen = false
let pickMode = false
let pickStyle: ReadStyle = 'summary'
let currentAudio: HTMLAudioElement | null = null
let highlightEl: HTMLElement | null = null

// === 公共工具 ===
function base64ToBlob(b64: string, mime = 'audio/wav'): Blob {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}

function playAudioBase64(b64: string) {
  stopAudio()
  const blob = base64ToBlob(b64)
  const url = URL.createObjectURL(blob)
  currentAudio = new Audio(url)
  currentAudio.onended = () => {
    URL.revokeObjectURL(url)
    currentAudio = null
    updateStopBtn()
  }
  currentAudio.onerror = () => {
    URL.revokeObjectURL(url)
    currentAudio = null
    updateStopBtn()
  }
  currentAudio.play().catch(() => {
    currentAudio = null
    updateStopBtn()
  })
  updateStopBtn()
}

function stopAudio() {
  if (currentAudio) {
    currentAudio.pause()
    currentAudio = null
  }
  updateStopBtn()
}

function toast(msg: string, isError = false) {
  if (!shadow) return
  const el = document.createElement('div')
  el.className = 'va-toast' + (isError ? ' va-toast-err' : '')
  el.textContent = msg
  shadow.appendChild(el)
  setTimeout(() => el.remove(), 3000)
}

function updateStopBtn() {
  if (!shadow) return
  const btn = shadow.querySelector<HTMLButtonElement>('.va-stop-btn')
  if (!btn) return
  btn.style.display = currentAudio ? 'flex' : 'none'
}

/** 检测扩展上下文是否已失效（重载扩展后残留的 content script 会如此） */
function isExtensionContextAlive(): boolean {
  try {
    return !!(chrome && chrome.runtime && chrome.runtime.id)
  } catch {
    return false
  }
}

/** 扩展上下文失效后的善后：弹提示 + 移除悬浮球 UI（残留 UI 已无法工作） */
function handleContextInvalidated() {
  try {
    toast('扩展已更新，请刷新当前页面后重试', true)
  } catch {
    /* shadow 可能已销毁 */
  }
  // 延迟移除 UI，让用户看到提示
  setTimeout(() => {
    try {
      teardownUI()
    } catch {
      /* noop */
    }
  }, 2500)
}

// === 朗读流程 ===
async function readContent(text: string, style: ReadStyle) {
  if (!text || !text.trim()) {
    toast('未获取到文字', true)
    return
  }
  if (!isExtensionContextAlive()) {
    handleContextInvalidated()
    return
  }
  toast(style === 'summary' ? '正在总结并朗读…' : '正在朗读…')
  try {
    const res: ReadResult = await chrome.runtime.sendMessage({
      type: 'readText',
      text: text.slice(0, 4000),
      style,
      enableTts: true,
    })
    if (!res?.ok) {
      toast('朗读失败：' + (res?.error || '未知错误'), true)
      return
    }
    const audio = res.data?.audio_base64
    if (audio) {
      playAudioBase64(audio)
    } else {
      toast('未生成音频', true)
    }
  } catch (e: any) {
    const msg = e?.message || String(e)
    // 扩展被重载后 content script 残留，调用 chrome.runtime 会抛此错
    if (/Extension context invalidated|Receiving end does not exist/i.test(msg)) {
      handleContextInvalidated()
      return
    }
    toast('请求失败：' + msg, true)
  }
}

function grabPageText(): string {
  const body = document.body
  if (!body) return ''
  const clone = body.cloneNode(true) as HTMLElement
  clone
    .querySelectorAll('script,style,noscript,iframe,svg,nav,header,footer,button,input,textarea')
    .forEach((n) => n.remove())
  const text = clone.innerText || ''
  return text.replace(/\n{3,}/g, '\n\n').trim()
}

// === 元素拾取模式 ===
function enterPickMode(style: ReadStyle) {
  pickMode = true
  pickStyle = style
  document.body.style.cursor = 'crosshair'
  document.addEventListener('mousemove', onPickMove, true)
  document.addEventListener('click', onPickClick, true)
  document.addEventListener('keydown', onPickKey, true)
  toast(`已进入点击朗读模式（${style === 'summary' ? '总结' : '原文'}），按 ESC 退出`)
}

function exitPickMode() {
  pickMode = false
  document.body.style.cursor = ''
  document.removeEventListener('mousemove', onPickMove, true)
  document.removeEventListener('click', onPickClick, true)
  document.removeEventListener('keydown', onPickKey, true)
  if (highlightEl) {
    highlightEl.style.outline = ''
    highlightEl = null
  }
}

function onPickMove(e: MouseEvent) {
  if (!pickMode) return
  const t = e.target as HTMLElement
  if (!t || t === highlightEl) return
  if (rootEl && (t === rootEl || rootEl.contains(t))) return
  if (highlightEl) highlightEl.style.outline = ''
  highlightEl = t
  t.style.outline = '2px solid #409eff'
}

function onPickClick(e: MouseEvent) {
  if (!pickMode) return
  const t = e.target as HTMLElement
  if (!t) return
  if (rootEl && (t === rootEl || rootEl.contains(t))) return
  e.preventDefault()
  e.stopPropagation()
  const text = t.innerText || t.textContent || ''
  exitPickMode()
  closeMenu()
  readContent(text, pickStyle)
}

function onPickKey(e: KeyboardEvent) {
  if (e.key === 'Escape') exitPickMode()
}

// === 悬浮球 UI ===
function buildUI() {
  // 幂等：如果已存在（或页面上之前的 root 节点仍在），清理后重建
  if (rootEl) return
  const stale = document.getElementById('va-floating-ball-root')
  if (stale) stale.remove()
  rootEl = document.createElement('div')
  rootEl.id = 'va-floating-ball-root'
  rootEl.style.cssText = 'all: initial; position: fixed; z-index: 2147483647;'
  shadow = rootEl.attachShadow({ mode: 'open' })

  const style = document.createElement('style')
  style.textContent = `
    :host, * {
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    .va-ball {
      position: fixed; width: 52px; height: 52px; border-radius: 50%;
      background: linear-gradient(135deg,#409eff,#67c23a); color: #fff;
      box-shadow: 0 6px 20px rgba(64,158,255,0.45); cursor: grab;
      display: flex; align-items: center; justify-content: center;
      font-size: 24px; user-select: none; -webkit-user-select: none;
      transition: transform .15s, box-shadow .15s;
    }
    .va-ball:hover { transform: scale(1.08); box-shadow: 0 8px 24px rgba(64,158,255,0.55); }

    /* === 对话弹窗（菜单面板） === */
    .va-menu {
      position: fixed; width: 280px; background: #fff; border-radius: 14px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.18);
      font-size: 14px; color: #303133; overflow: hidden;
      border: 1px solid rgba(0,0,0,0.06);
      animation: va-menu-in .15s ease-out;
    }
    @keyframes va-menu-in {
      from { opacity: 0; transform: translateY(-4px) scale(0.98); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }
    .va-menu-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 14px;
      background: linear-gradient(135deg,#409eff,#67c23a);
      color: #fff; cursor: grab; user-select: none; -webkit-user-select: none;
    }
    .va-menu-header.dragging { cursor: grabbing; }
    .va-menu-title {
      display: flex; align-items: center; gap: 6px;
      font-size: 14px; font-weight: 600;
    }
    .va-menu-close {
      width: 22px; height: 22px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      background: rgba(255,255,255,0.15); color: #fff; cursor: pointer;
      font-size: 14px; line-height: 1; transition: background .12s;
    }
    .va-menu-close:hover { background: rgba(255,255,255,0.3); }
    .va-menu-body { padding: 6px 0; }
    .va-menu-group-title {
      padding: 8px 16px 4px; font-size: 11px; color: #909399;
      letter-spacing: 0.5px; text-transform: uppercase;
    }
    .va-menu-item {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 16px; cursor: pointer; white-space: nowrap;
      transition: background .12s;
    }
    .va-menu-item:hover { background: #f5f7fa; }
    .va-menu-item .va-icon {
      width: 22px; height: 22px; border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      background: #ecf5ff; color: #409eff; font-size: 13px;
    }
    .va-menu-item.summary .va-icon { background: #f0f9eb; color: #67c23a; }
    .va-menu-item.pick .va-icon { background: #fdf6ec; color: #e6a23c; }
    .va-menu-item.danger { color: #f56c6c; border-top: 1px solid #ebeef5; margin-top: 4px; padding-top: 12px; }
    .va-menu-item.danger .va-icon { background: #fef0f0; color: #f56c6c; }

    .va-stop-btn {
      position: fixed; bottom: 88px; right: 20px; display: none;
      padding: 10px 16px; border-radius: 22px; background: #f56c6c; color:#fff;
      border: none; cursor: pointer; box-shadow: 0 4px 14px rgba(245,108,108,0.4);
      align-items: center; gap: 6px; font-size: 13px; font-weight: 500;
    }
    .va-stop-btn:hover { background: #f78989; }

    .va-toast {
      position: fixed; left: 50%; top: 30px; transform: translateX(-50%);
      background: rgba(0,0,0,0.78); color: #fff; padding: 10px 18px;
      border-radius: 20px; font-size: 13px; z-index: 2147483647;
      max-width: 80%; text-align: center;
    }
    .va-toast-err { background: #f56c6c; }
  `
  shadow.appendChild(style)

  // 悬浮球
  const ball = document.createElement('div')
  ball.className = 'va-ball'
  ball.textContent = '🎤'
  ball.title = 'AI 语音助理 · 点击展开'
  shadow.appendChild(ball)

  // 菜单容器（对话弹窗）
  const menu = document.createElement('div')
  menu.className = 'va-menu'
  menu.style.display = 'none'
  menu.innerHTML = `
    <div class="va-menu-header" data-role="drag-handle">
      <div class="va-menu-title">
        <span>🎤</span>
        <span>AI 语音助理</span>
      </div>
      <div class="va-menu-close" data-act="close-menu" title="关闭">✕</div>
    </div>
    <div class="va-menu-body">
      <div class="va-menu-group-title">整页朗读</div>
      <div class="va-menu-item" data-act="read-page-raw">
        <span class="va-icon">📖</span><span>朗读整页原文</span>
      </div>
      <div class="va-menu-item summary" data-act="read-page-sum">
        <span class="va-icon">🧠</span><span>LLM 总结朗读</span>
      </div>
      <div class="va-menu-group-title">点击元素朗读</div>
      <div class="va-menu-item pick" data-act="pick-raw">
        <span class="va-icon">🎯</span><span>点击元素 · 原文</span>
      </div>
      <div class="va-menu-item pick" data-act="pick-sum">
        <span class="va-icon">🎯</span><span>点击元素 · 总结</span>
      </div>
      <div class="va-menu-item danger" data-act="close">
        <span class="va-icon">✖</span><span>关闭悬浮球</span>
      </div>
    </div>
  `
  shadow.appendChild(menu)

  // 停止朗读按钮
  const stopBtn = document.createElement('button')
  stopBtn.className = 'va-stop-btn'
  stopBtn.innerHTML = '⏹ 停止朗读'
  stopBtn.onclick = () => stopAudio()
  shadow.appendChild(stopBtn)

  // === 交互：悬浮球拖动 ===
  let ballDrag: { x: number; y: number; ox: number; oy: number; moved: boolean } | null = null
  const loadBallPos = async () => {
    const r = await chrome.storage.local.get(FB_POS_KEY)
    const p = r[FB_POS_KEY] as { x: number; y: number } | undefined
    if (p && typeof p.x === 'number' && typeof p.y === 'number') {
      // 边界 clamp：避免之前在大屏幕拖拽后，在小屏幕上超出可视区看不见
      const SIZE = 52 // 跟 .va-ball width/height 保持一致
      const MARGIN = 4
      const maxX = Math.max(MARGIN, window.innerWidth - SIZE - MARGIN)
      const maxY = Math.max(MARGIN, window.innerHeight - SIZE - MARGIN)
      const x = Math.min(Math.max(MARGIN, p.x), maxX)
      const y = Math.min(Math.max(MARGIN, p.y), maxY)
      ball.style.left = x + 'px'
      ball.style.top = y + 'px'
      ball.style.right = ''
      ball.style.bottom = ''
      // 如果被 clamp 了，同步修正 storage，免得下次又跳出可视区
      if (x !== p.x || y !== p.y) {
        try {
          await chrome.storage.local.set({ [FB_POS_KEY]: { x, y } })
        } catch { /* ignore */ }
      }
    } else {
      ball.style.right = '20px'
      ball.style.bottom = '20px'
    }
  }
  loadBallPos()

  // 窗口 resize 时重新 clamp，防止拖动后缩窗口丢失悬浮球
  window.addEventListener('resize', () => { loadBallPos() })

  ball.addEventListener('mousedown', (e) => {
    const rect = ball.getBoundingClientRect()
    ballDrag = { x: e.clientX, y: e.clientY, ox: rect.left, oy: rect.top, moved: false }
    ball.style.cursor = 'grabbing'
    e.preventDefault()
  })

  // === 交互：菜单拖动（通过标题栏） ===
  let menuDrag: { x: number; y: number; ox: number; oy: number; moved: boolean } | null = null
  const header = menu.querySelector<HTMLElement>('.va-menu-header')!
  header.addEventListener('mousedown', (e) => {
    const target = e.target as HTMLElement
    if (target.closest('.va-menu-close')) return // 关闭按钮不触发拖拽
    const rect = menu.getBoundingClientRect()
    menuDrag = { x: e.clientX, y: e.clientY, ox: rect.left, oy: rect.top, moved: false }
    header.classList.add('dragging')
    e.preventDefault()
  })

  document.addEventListener('mousemove', (e) => {
    if (ballDrag) {
      const dx = e.clientX - ballDrag.x
      const dy = e.clientY - ballDrag.y
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) ballDrag.moved = true
      ball.style.left = ballDrag.ox + dx + 'px'
      ball.style.top = ballDrag.oy + dy + 'px'
      ball.style.right = ''
      ball.style.bottom = ''
    }
    if (menuDrag) {
      const dx = e.clientX - menuDrag.x
      const dy = e.clientY - menuDrag.y
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) menuDrag.moved = true
      const nx = Math.max(4, menuDrag.ox + dx)
      const ny = Math.max(4, menuDrag.oy + dy)
      menu.style.left = nx + 'px'
      menu.style.top = ny + 'px'
    }
  })

  document.addEventListener('mouseup', async () => {
    if (ballDrag) {
      ball.style.cursor = 'grab'
      if (ballDrag.moved) {
        const rect = ball.getBoundingClientRect()
        await chrome.storage.local.set({ [FB_POS_KEY]: { x: rect.left, y: rect.top } })
      }
      ballDrag = null
    }
    if (menuDrag) {
      header.classList.remove('dragging')
      if (menuDrag.moved) {
        const rect = menu.getBoundingClientRect()
        await chrome.storage.local.set({ [FB_MENU_POS_KEY]: { x: rect.left, y: rect.top } })
      }
      menuDrag = null
    }
  })

  ball.addEventListener('click', (e) => {
    if (e.detail === 0) return
    if (menuOpen) closeMenuInner()
    else openMenu()
  })

  menu.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    // 点击关闭按钮
    if (target.closest('[data-act="close-menu"]')) {
      closeMenuInner()
      return
    }
    const item = target.closest('.va-menu-item') as HTMLElement | null
    if (!item) return
    const act = item.getAttribute('data-act')
    closeMenuInner()
    switch (act) {
      case 'read-page-raw':
        readContent(grabPageText(), 'read')
        break
      case 'read-page-sum':
        readContent(grabPageText(), 'summary')
        break
      case 'pick-raw':
        enterPickMode('read')
        break
      case 'pick-sum':
        enterPickMode('summary')
        break
      case 'close':
        disableBall()
        break
    }
  })

  async function openMenu() {
    // 先尝试恢复上次拖拽到的位置
    const saved = (await chrome.storage.local.get(FB_MENU_POS_KEY))[FB_MENU_POS_KEY] as
      | { x: number; y: number }
      | undefined
    const vw = window.innerWidth
    const vh = window.innerHeight
    const menuW = 280
    const menuH = 360 // 估算
    if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
      const x = Math.min(Math.max(8, saved.x), vw - menuW - 8)
      const y = Math.min(Math.max(8, saved.y), vh - 80)
      menu.style.left = x + 'px'
      menu.style.top = y + 'px'
    } else {
      // 默认出现在悬浮球左上方
      const rect = ball.getBoundingClientRect()
      let x = rect.left - menuW - 8
      let y = rect.top - 40
      if (x < 8) x = Math.min(rect.right + 8, vw - menuW - 8)
      if (y < 8) y = 8
      if (y + menuH > vh) y = Math.max(8, vh - menuH - 8)
      menu.style.left = x + 'px'
      menu.style.top = y + 'px'
    }
    menu.style.display = 'block'
    menuOpen = true
  }
  function closeMenuInner() {
    menu.style.display = 'none'
    menuOpen = false
  }
  ;(globalThis as any).__va_closeMenu = closeMenuInner

  document.addEventListener('click', (e) => {
    if (!menuOpen) return
    const path = e.composedPath()
    if (!path.includes(ball) && !path.includes(menu)) closeMenuInner()
  })

  document.documentElement.appendChild(rootEl)
}

function closeMenu() {
  ;(globalThis as any).__va_closeMenu?.()
}

async function disableBall() {
  // 先立即销毁 UI，避免因 storage 异常（例如扩展重载导致 context invalidated）
  // 导致 teardown 被跳过，悬浮球残留在页面上。
  teardownUI()
  // chrome.runtime.id 在 context 失效后为 undefined，提前判断，避免静默失败
  if (!chrome.runtime?.id) {
    console.warn('[FB] context invalidated, please reload the extension')
    return
  }
  try {
    await chrome.storage.local.set({ [FB_KEY]: false })
  } catch (e) {
    console.warn('[FB] disable: storage set failed', e)
  }
}

function teardownUI() {
  stopAudio()
  exitPickMode()
  rootEl?.remove()
  rootEl = null
  shadow = null
  menuOpen = false
}

// === 启动 / 响应配置变化 ===
async function bootstrap() {
  const r = await chrome.storage.local.get(FB_KEY)
  if (r[FB_KEY]) buildUI()

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return
    if (FB_KEY in changes) {
      const enabled = !!changes[FB_KEY].newValue
      if (enabled && !rootEl) buildUI()
      else if (!enabled && rootEl) teardownUI()
    }
  })
}

// 同一页面可能被多次注入（manifest 自动 + service worker 手动），
// 不能用 window 锁劲性拦截：旧脚本可能因扩展重载丢失 chrome.* context，
// 导致监听器全部失效但锁仍在，进而新脚本不会 bootstrap。改用进程内幂等
// 检查（buildUI 本身已判重），以及下面 onChanged 判 rootEl 存在则跳过。
bootstrap()
