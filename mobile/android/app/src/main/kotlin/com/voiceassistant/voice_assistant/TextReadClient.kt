package com.voiceassistant.voice_assistant

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import android.widget.Toast
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.FileOutputStream
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * 原生朗读链路：POST /api/accessibility/read-text → base64 音频 → MediaPlayer
 * 这样即使 Flutter engine 处于后台被系统休眠也不会中断朗读。
 */
object TextReadClient {
    private const val TAG = "VA_READ"
    private const val BASE_URL = "http://127.0.0.1:8000" // 与 AppConfig.baseUrl 对齐，依赖 adb reverse
    private const val ENDPOINT = "/api/accessibility/read-text"

    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var player: MediaPlayer? = null

    /** 当前是否有音频正在播放。供悬浮球动态显示「停止」按钮 */
    @Volatile var isPlaying: Boolean = false
        private set

    /** 播放状态变化回调（已在主线程） */
    var onStateChanged: ((playing: Boolean) -> Unit)? = null

    private fun setPlayingState(playing: Boolean) {
        if (isPlaying == playing) return
        isPlaying = playing
        main.post { onStateChanged?.invoke(playing) }
    }

    fun read(context: Context, text: String, style: String) {
        val appCtx = context.applicationContext
        executor.execute {
            val token = loadAuthToken(appCtx)
            if (token.isNullOrEmpty()) {
                toast(appCtx, "未登录或登录已过期，请先在 APP 内登录")
                return@execute
            }
            try {
                val (code, bodyStr) = doPost(token, text, style)
                Log.d(TAG, "read-text code=$code bodyLen=${bodyStr.length}")
                if (code !in 200..299) {
                    toast(appCtx, "朗读请求失败：HTTP $code")
                    Log.w(TAG, "body=${bodyStr.take(500)}")
                    return@execute
                }
                val json = JSONObject(bodyStr)
                val audioB64 = json.optString("audio_base64", "")
                val format = json.optString("audio_format", "wav")
                if (audioB64.isEmpty()) {
                    val processed = json.optString("text", "")
                    toast(appCtx, "后端未返回音频：${processed.take(40)}")
                    return@execute
                }
                val bytes = Base64.decode(audioB64, Base64.DEFAULT)
                val file = File(appCtx.cacheDir, "tts_${System.currentTimeMillis()}.${format}")
                FileOutputStream(file).use { it.write(bytes) }
                main.post { playFile(appCtx, file) }
            } catch (e: Throwable) {
                Log.e(TAG, "read-text failed", e)
                toast(appCtx, "朗读失败：${e.message ?: e.javaClass.simpleName}")
            }
        }
    }

    /** 直接停止当前播放（供菜单/悬浮球关闭时调用） */
    fun stop() {
        main.post {
            releaseCurrent()
            setPlayingState(false)
        }
    }

    /** 同步释放当前 player。必须在主线程调用 */
    private fun releaseCurrent() {
        val old = player ?: return
        player = null
        try { old.setOnPreparedListener(null) } catch (_: Throwable) {}
        try { old.setOnCompletionListener(null) } catch (_: Throwable) {}
        try { old.setOnErrorListener(null) } catch (_: Throwable) {}
        try { old.stop() } catch (_: Throwable) {}
        try { old.release() } catch (_: Throwable) {}
    }

    private fun playFile(ctx: Context, file: File) {
        try {
            // 同步释放旧 player；绝不能用 stop() 异步 post，
            // 否则旧任务会在新 player 赋值后执行，将新 player 误杀。
            releaseCurrent()
            setPlayingState(false)
            val mp = MediaPlayer()
            // 注：以前使用 USAGE_ASSISTANCE_ACCESSIBILITY 会在华为 EMUI 上被路由到「辅助音量」流，
            // 默认音量极小或为 0，导致听不到声音。改为 USAGE_MEDIA 走普通媒体流。
            mp.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            mp.setDataSource(file.absolutePath)
            mp.setOnPreparedListener { p ->
                // 若 player 已被替换或清空（说明用户或新请求中止了本次），不要 start
                if (player !== p) {
                    Log.w(TAG, "onPrepared but player replaced, skip start")
                    try { p.release() } catch (_: Throwable) {}
                    return@setOnPreparedListener
                }
                try {
                    p.start()
                    setPlayingState(true)
                    Log.d(TAG, "MediaPlayer started duration=${p.duration}ms")
                } catch (e: Throwable) {
                    Log.e(TAG, "start failed", e)
                    toast(ctx, "播放启动失败：${e.message}")
                    setPlayingState(false)
                }
            }
            mp.setOnCompletionListener {
                Log.d(TAG, "MediaPlayer onCompletion")
                if (player === it) player = null
                try { it.release() } catch (_: Throwable) {}
                try { file.delete() } catch (_: Throwable) {}
                setPlayingState(false)
            }
            mp.setOnErrorListener { p, what, extra ->
                Log.w(TAG, "MediaPlayer error what=$what extra=$extra")
                toast(ctx, "播放失败(what=$what extra=$extra)")
                if (player === p) player = null
                try { p.release() } catch (_: Throwable) {}
                setPlayingState(false)
                true
            }
            player = mp
            mp.prepareAsync()
        } catch (e: Throwable) {
            Log.e(TAG, "play failed", e)
            toast(ctx, "播放失败：${e.message}")
            setPlayingState(false)
        }
    }

    private fun doPost(token: String, text: String, style: String): Pair<Int, String> {
        val url = URL(BASE_URL + ENDPOINT)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15000
            readTimeout = 60000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Authorization", "Bearer $token")
        }
        try {
            val body = JSONObject()
                .put("text", text)
                .put("style", style)
                .put("enable_tts", true)
                .toString()
            OutputStreamWriter(conn.outputStream, "UTF-8").use { it.write(body) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val sb = StringBuilder()
            BufferedReader(InputStreamReader(stream, "UTF-8")).use { r ->
                val buf = CharArray(4096)
                while (true) { val n = r.read(buf); if (n <= 0) break; sb.append(buf, 0, n) }
            }
            return code to sb.toString()
        } finally {
            conn.disconnect()
        }
    }

    private fun loadAuthToken(ctx: Context): String? {
        // Flutter 的 shared_preferences 在 Android 端存入 FlutterSharedPreferences.xml，key 前缀 flutter.
        val prefs = ctx.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
        return prefs.getString("flutter.auth_token", null)
    }

    private fun toast(ctx: Context, msg: String) {
        main.post { Toast.makeText(ctx, msg, Toast.LENGTH_LONG).show() }
    }
}
