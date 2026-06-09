package com.voiceassistant.voice_assistant

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.IBinder
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.app.NotificationCompat
import kotlin.math.abs

/**
 * 悬浮球前台服务 - 在任意 App 之上显示按钮，点击后：
 *  - 「整屏原文」：抓当前屏幕所有文本广播"read"
 *  - 「整屏总结」：同上，mode=summary
 *  - 「点击元素」：进入拾取模式，拦截触摸坐标并查询节点文本
 *  - 「关闭」：停止服务
 */
class FloatingBallService : Service() {

    companion object {
        const val ACTION_START = "com.voiceassistant.action.START_BALL"
        const val ACTION_STOP = "com.voiceassistant.action.STOP_BALL"

        /** 悬浮球前台服务是否正在运行——供 UI 状态以及其他地方判断 */
        @Volatile
        var isRunning: Boolean = false
            private set

        /**
         * 广播抓取到的文字给 Flutter 端。由 MainActivity 的 EventChannel 监听
         */
        var onTextCaptured: ((text: String, mode: String) -> Unit)? = null

        private const val CHANNEL_ID = "voice_assistant_floating_ball"
        private const val NOTIFY_ID = 9901
    }

    private var windowManager: WindowManager? = null
    private var ballView: View? = null
    private var menuView: View? = null
    private var overlayView: View? = null // 拾取遮罩
    private var stopBallView: View? = null // 朗读中显示的「停止」悬浮球
    private var ballParams: WindowManager.LayoutParams? = null

    private var defaultMode: String = "summary" // 保留仅用作 pickMode fallback，不再从 Flutter 侧设置
    private var pickMode: String? = null // null=未启用

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        startAsForeground()
        showBall()
        isRunning = true
        // 监听原生播放状态：播放时显示「停止」悬浮球
        TextReadClient.onStateChanged = { playing ->
            if (playing) showStopBall() else hideStopBall()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        isRunning = false
        TextReadClient.onStateChanged = null
        TextReadClient.stop()
        removeAllViews()
        super.onDestroy()
    }

    private fun startAsForeground() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.floating_ball_notification_title),
                NotificationManager.IMPORTANCE_LOW
            )
            nm.createNotificationChannel(channel)
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val notif: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.floating_ball_notification_title))
            .setContentText(getString(R.string.floating_ball_notification_text))
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFY_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFY_ID, notif)
        }
    }

    // === UI ===
    private fun dp(v: Int): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun showBall() {
        if (ballView != null) return
        val tv = TextView(this).apply {
            text = "🎤"
            textSize = 22f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            val bg = GradientDrawable()
            bg.shape = GradientDrawable.OVAL
            bg.setColors(intArrayOf(0xFF409EFF.toInt(), 0xFF67C23A.toInt()))
            bg.orientation = GradientDrawable.Orientation.TL_BR
            background = bg
        }
        val size = dp(52)
        val params = WindowManager.LayoutParams(
            size, size,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        val dm = resources.displayMetrics
        params.x = dm.widthPixels - size - dp(16)
        params.y = dm.heightPixels / 2
        ballParams = params

        tv.setOnTouchListener(object : View.OnTouchListener {
            var startX = 0
            var startY = 0
            var downX = 0f
            var downY = 0f
            var moved = false
            override fun onTouch(v: View, e: MotionEvent): Boolean {
                when (e.action) {
                    MotionEvent.ACTION_DOWN -> {
                        startX = params.x; startY = params.y
                        downX = e.rawX; downY = e.rawY
                        moved = false
                    }
                    MotionEvent.ACTION_MOVE -> {
                        val dx = (e.rawX - downX).toInt()
                        val dy = (e.rawY - downY).toInt()
                        if (abs(dx) > 6 || abs(dy) > 6) moved = true
                        params.x = startX + dx
                        params.y = startY + dy
                        windowManager?.updateViewLayout(tv, params)
                    }
                    MotionEvent.ACTION_UP -> {
                        if (!moved) toggleMenu()
                    }
                }
                return true
            }
        })

        windowManager?.addView(tv, params)
        ballView = tv
    }

    private fun toggleMenu() {
        if (menuView != null) {
            hideMenu()
        } else {
            showMenu()
        }
    }

    private fun showMenu() {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(8), dp(8), dp(8), dp(8))
            val bg = GradientDrawable()
            bg.setColor(0xFFFFFFFF.toInt())
            bg.cornerRadius = dp(10).toFloat()
            background = bg
            elevation = dp(6).toFloat()
        }
        fun addItem(label: String, onClick: () -> Unit) {
            val t = TextView(this@FloatingBallService).apply {
                text = label
                textSize = 14f
                setTextColor(0xFF303133.toInt())
                setPadding(dp(14), dp(10), dp(14), dp(10))
                isClickable = true
                setOnClickListener {
                    hideMenu()
                    onClick()
                }
            }
            container.addView(t)
        }
        addItem("📖 朗读整屏原文") { captureAllText("read") }
        addItem("🧠 LLM 总结朗读") { captureAllText("summary") }
        addItem("🎯 点击元素 · 原文") { enterPickMode("read") }
        addItem("🎯 点击元素 · 总结") { enterPickMode("summary") }
        addItem("✖ 关闭悬浮球") {
            stopSelf()
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        val bp = ballParams ?: return
        val dm = resources.displayMetrics
        params.x = (bp.x - dp(180)).coerceAtLeast(dp(8))
        params.y = (bp.y - dp(20)).coerceAtMost(dm.heightPixels - dp(260))

        windowManager?.addView(container, params)
        menuView = container
    }

    private fun hideMenu() {
        menuView?.let { runCatching { windowManager?.removeView(it) } }
        menuView = null
    }

    private fun captureAllText(mode: String) {
        if (!ScreenReaderAccessibilityService.isRunning()) {
            Toast.makeText(this, "请先开启无障碍服务", Toast.LENGTH_SHORT).show()
            return
        }
        // 延迟 300ms 再抓取，给菜单关闭/前台切换一些时间
        ballView?.postDelayed({
            val text = ScreenReaderAccessibilityService.getAllVisibleText()
            android.util.Log.d("VA_BALL", "captureAllText mode=$mode textLen=${text.length}")
            if (text.isBlank()) {
                Toast.makeText(this, "未识别到屏幕文字(检查无障碍权限)", Toast.LENGTH_LONG).show()
                return@postDelayed
            }
            Toast.makeText(this, "已抓取${text.length}字，正在请求朗读…", Toast.LENGTH_SHORT).show()
            // 直接原生链路请求+播放，不再依赖 Flutter engine
            TextReadClient.read(this, text, if (mode == "summary") "summary" else "read")
            // 同时通知 Flutter 端（用于展示文字，即使 Flutter 休眠也不影响朗读）
            onTextCaptured?.invoke(text, mode)
        }, 300L)
    }

    // === 拾取模式：全屏透明遮罩接管触摸，点击后查询节点 ===
    private fun enterPickMode(mode: String) {
        if (!ScreenReaderAccessibilityService.isRunning()) {
            Toast.makeText(this, "请先开启无障碍服务", Toast.LENGTH_SHORT).show()
            return
        }
        pickMode = mode
        val overlay = View(this).apply {
            setBackgroundColor(0x22409EFF) // 半透明蓝
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        )
        overlay.setOnTouchListener { _, e ->
            if (e.action == MotionEvent.ACTION_UP) {
                val x = e.rawX.toInt()
                val y = e.rawY.toInt()
                val savedMode = pickMode ?: defaultMode
                exitPickMode()
                // 延迟抓取，等遮罩移除后窗口层更新
                ballView?.postDelayed({
                    val txt = ScreenReaderAccessibilityService.getTextAtPosition(x, y)
                    android.util.Log.d("VA_BALL", "pick($x,$y) len=${txt?.length ?: -1}")
                    if (txt.isNullOrBlank()) {
                        Toast.makeText(this, "该位置未识别到文字", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this, "已抓取，正在请求朗读…", Toast.LENGTH_SHORT).show()
                        TextReadClient.read(this, txt, if (savedMode == "summary") "summary" else "read")
                        onTextCaptured?.invoke(txt, savedMode)
                    }
                }, 250L)
            }
            true
        }
        windowManager?.addView(overlay, params)
        overlayView = overlay
        Toast.makeText(
            this,
            "请点击要朗读的文字区域（${if (mode == "summary") "总结" else "原文"}）",
            Toast.LENGTH_SHORT
        ).show()
    }

    private fun exitPickMode() {
        overlayView?.let { runCatching { windowManager?.removeView(it) } }
        overlayView = null
        pickMode = null
    }

    private fun removeAllViews() {
        hideMenu()
        exitPickMode()
        hideStopBall()
        ballView?.let { runCatching { windowManager?.removeView(it) } }
        ballView = null
    }

    // === 朗读中的「停止」悬浮球（模仿网页端） ===
    private fun showStopBall() {
        if (stopBallView != null) return
        val tv = TextView(this).apply {
            text = "⏹"
            textSize = 22f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            val bg = GradientDrawable()
            bg.shape = GradientDrawable.OVAL
            bg.setColor(0xFFE53935.toInt()) // 红色
            background = bg
        }
        val size = dp(46)
        val params = WindowManager.LayoutParams(
            size, size,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        val bp = ballParams
        val dm = resources.displayMetrics
        if (bp != null) {
            // 在主悬浮球左侧偶移显示
            params.x = (bp.x - dp(54)).coerceAtLeast(dp(8))
            params.y = bp.y
        } else {
            params.x = dm.widthPixels - size - dp(76)
            params.y = dm.heightPixels / 2
        }
        tv.setOnClickListener {
            Toast.makeText(this, "已停止朗读", Toast.LENGTH_SHORT).show()
            TextReadClient.stop()
        }
        runCatching { windowManager?.addView(tv, params) }
        stopBallView = tv
    }

    private fun hideStopBall() {
        stopBallView?.let { runCatching { windowManager?.removeView(it) } }
        stopBallView = null
    }
}
