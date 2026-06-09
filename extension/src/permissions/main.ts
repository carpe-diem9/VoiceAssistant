// 扩展独立授权页：在此页面调用 getUserMedia 触发 Chrome 原生权限对话框
// 授权成功后整个扩展（popup/sidepanel/options）获得麦克风权限

const statusEl = document.getElementById('status') as HTMLDivElement
const textEl = document.getElementById('statusText') as HTMLSpanElement
const btnRetry = document.getElementById('btnRetry') as HTMLButtonElement
const btnClose = document.getElementById('btnClose') as HTMLButtonElement

function setStatus(kind: 'pending' | 'ok' | 'err', html: string) {
  statusEl.className = 'status ' + kind
  textEl.innerHTML = html
}

async function requestMic() {
  setStatus('pending', '正在向浏览器申请麦克风权限，请在弹出的对话框中点击<b>「允许」</b>…')
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    // 立即停掉流，仅为触发授权
    stream.getTracks().forEach((t) => t.stop())
    setStatus(
      'ok',
      '<b>授权成功！</b> 现在可以关闭本页面，回到扩展弹窗点击麦克风按钮开始录音。',
    )
  } catch (e: any) {
    const name = e?.name || ''
    const msg = e?.message || String(e)
    let tip = msg
    if (name === 'NotAllowedError' || /denied|dismissed|Permission/i.test(msg)) {
      tip =
        '权限被拒绝或关闭。请点击浏览器地址栏左侧的<b>锁形/调节</b>图标 → 将<b>「麦克风」</b>改为<b>「允许」</b>，然后点击下方<b>「重新申请权限」</b>。'
    } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      tip = '未检测到可用的麦克风设备，请检查系统音频设置。'
    } else if (name === 'NotReadableError') {
      tip = '麦克风被其他程序占用，请关闭占用程序（如会议、录音软件）后重试。'
    }
    setStatus('err', tip)
  }
}

btnRetry.addEventListener('click', () => {
  requestMic()
})

btnClose.addEventListener('click', () => {
  // Chrome 扩展自身 tab 可以被脚本关闭
  try {
    window.close()
  } catch {
    /* noop */
  }
})

// 页面加载后立即请求一次（用户主动打开本页即视为"我要授权"）
requestMic()
