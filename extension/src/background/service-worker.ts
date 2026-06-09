/**
 * Chrome 扩展 service worker
 * - 代理 content script 的朗读请求（带 JWT 调后端）
 * - 初次安装打开设置页
 * - 监听悬浮球开关，开启后主动向所有已打开的 tab 注入 content script
 */

const MSG_READ_TEXT = 'readText'
const MSG_STOP = 'stopReading'
const MSG_FORCE_INJECT = 'forceInjectFloatingBall'

const BASE_URL_KEY = 'base_url'
const TOKEN_KEY = 'auth_token'
// 与 content script 共享同名、但在不同作用域；变量名加后缀避免 tsc 误报 redeclare
const FB_KEY_SW = 'floating_ball_enabled'

/** 从当前清单中拿到悬浮球 content script 编译产物路径 */
function getFloatingBallScripts(): string[] {
  try {
    const m = chrome.runtime.getManifest()
    const list: string[] = []
    for (const cs of m.content_scripts || []) {
      for (const js of cs.js || []) {
        if (js && js.includes('floating-ball')) list.push(js)
      }
    }
    return list
  } catch {
    return []
  }
}

/** 向所有 http(s) tab 主动注入悬浮球脚本（开关从 false→true 时调用）*/
async function injectFloatingBallToAllTabs(): Promise<{ ok: number; skip: number; total: number }> {
  const files = getFloatingBallScripts()
  console.log('[FB] inject scripts:', files)
  if (!files.length) return { ok: 0, skip: 0, total: 0 }
  try {
    const tabs = await chrome.tabs.query({})
    let okCnt = 0
    let skipCnt = 0
    for (const tab of tabs) {
      if (!tab.id || !tab.url) { skipCnt++; continue }
      if (!/^https?:/i.test(tab.url)) { skipCnt++; continue } // chrome:// / file:// 不能注入
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id, allFrames: false },
          files,
        })
        okCnt++
      } catch (e) {
        // 有些页面 (chrome web store / pdf viewer) 拒绝注入，忽略
        skipCnt++
      }
    }
    console.log(`[FB] injected: ok=${okCnt} skip=${skipCnt} total=${tabs.length}`)
    return { ok: okCnt, skip: skipCnt, total: tabs.length }
  } catch (e) {
    console.warn('[FB] inject failed', e)
    return { ok: 0, skip: 0, total: 0 }
  }
}

async function getBaseUrl(): Promise<string> {
  const r = await chrome.storage.local.get(BASE_URL_KEY)
  return (r[BASE_URL_KEY] as string) || 'http://127.0.0.1:8000'
}

async function getToken(): Promise<string | undefined> {
  const r = await chrome.storage.local.get(TOKEN_KEY)
  return r[TOKEN_KEY] as string | undefined
}

async function readTextApi(text: string, style: 'read' | 'summary', enableTts: boolean) {
  const baseUrl = await getBaseUrl()
  const token = await getToken()
  if (!token) {
    return { ok: false, error: '未登录，请先在扩展弹窗登录' }
  }
  try {
    const res = await fetch(`${baseUrl}/api/accessibility/read-text`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ text, style, enable_tts: enableTts }),
    })
    if (!res.ok) {
      const errText = await res.text()
      return { ok: false, error: errText || `HTTP ${res.status}` }
    }
    const data = await res.json()
    return { ok: true, data }
  } catch (e: any) {
    return { ok: false, error: e.message || String(e) }
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === MSG_READ_TEXT) {
    const { text, style, enableTts } = msg
    readTextApi(text, style || 'summary', enableTts !== false).then(sendResponse)
    return true // keep channel open for async
  }
  if (msg?.type === MSG_STOP) {
    // content script 自己控制播放，background 无状态
    sendResponse({ ok: true })
    return false
  }
  if (msg?.type === MSG_FORCE_INJECT) {
    // Options 页 toggle 强制注入兜底
    injectFloatingBallToAllTabs().then(sendResponse)
    return true
  }
  return false
})

chrome.runtime.onInstalled.addListener((details) => {
  // 任何安装/更新/重载场景，都强制将悬浮球开关重置为关闭，
  // 避免上一个会话因 context invalidated 导致写入失败而残留 stale 状态。
  chrome.storage.local.set({ [FB_KEY_SW]: false }).catch(() => {})
  if (details.reason === 'install') {
    chrome.runtime.openOptionsPage?.()
  }
})

// 浏览器启动时也重置一次，保证默认不启动悬浮球
chrome.runtime.onStartup?.addListener(() => {
  chrome.storage.local.set({ [FB_KEY_SW]: false }).catch(() => {})
})

// 监听存储变化：悬浮球开关从关闭变为开启时，主动注入悬浮球到所有 tab
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local') return
  if (FB_KEY_SW in changes) {
    const newVal = !!changes[FB_KEY_SW].newValue
    const oldVal = !!changes[FB_KEY_SW].oldValue
    if (newVal && !oldVal) {
      injectFloatingBallToAllTabs()
    }
    // 关闭逻辑由 content script 自己监听并 teardown，无需处理
  }
})

// 点击扩展图标时，允许通过 sidePanel 打开（可选）
chrome.sidePanel
  ?.setPanelBehavior({ openPanelOnActionClick: false })
  .catch(() => {})

