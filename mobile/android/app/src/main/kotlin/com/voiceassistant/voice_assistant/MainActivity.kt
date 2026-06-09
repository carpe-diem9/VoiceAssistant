package com.voiceassistant.voice_assistant

import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.text.TextUtils
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private val methodChannelName = "voice_assistant/accessibility"
    private val eventChannelName = "voice_assistant/accessibility_events"

    private var eventSink: EventChannel.EventSink? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // 将悬浮球回调绑定到当前 Activity 的 eventSink——只要 Flutter engine 存活就能收到。
        FloatingBallService.onTextCaptured = { text, mode ->
            runOnUiThread {
                android.util.Log.d("VA_MA", "onTextCaptured len=${text.length} mode=$mode sinkNull=${eventSink == null}")
                eventSink?.success(mapOf("text" to text, "mode" to mode))
            }
        }

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, methodChannelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "isAccessibilityEnabled" -> result.success(isAccessibilityServiceEnabled())
                    "openAccessibilitySettings" -> {
                        startActivity(
                            Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
                                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        )
                        result.success(null)
                    }
                    "isOverlayGranted" -> result.success(canDrawOverlay())
                    "requestOverlayPermission" -> {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
                            startActivity(
                                Intent(
                                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                    Uri.parse("package:$packageName")
                                ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            )
                        }
                        result.success(null)
                    }
                    "startFloatingBall" -> {
                        if (!canDrawOverlay()) {
                            result.error("NO_OVERLAY_PERMISSION", "未授予悬浮窗权限", null)
                            return@setMethodCallHandler
                        }
                        val intent = Intent(this, FloatingBallService::class.java)
                            .setAction(FloatingBallService.ACTION_START)
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                            startForegroundService(intent)
                        } else {
                            startService(intent)
                        }
                        result.success(null)
                    }
                    "stopFloatingBall" -> {
                        val intent = Intent(this, FloatingBallService::class.java)
                            .setAction(FloatingBallService.ACTION_STOP)
                        startService(intent)
                        result.success(null)
                    }
                    "stopReading" -> {
                        // 立即停止原生 MediaPlayer 播放
                        TextReadClient.stop()
                        result.success(null)
                    }
                    "isFloatingBallRunning" -> {
                        result.success(FloatingBallService.isRunning)
                    }
                    else -> result.notImplemented()
                }
            }

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, eventChannelName)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    eventSink = events
                }

                override fun onCancel(arguments: Any?) {
                    eventSink = null
                }
            })
    }

    private fun canDrawOverlay(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(this)
        } else true
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val cn = ComponentName(this, ScreenReaderAccessibilityService::class.java)
        val expected = cn.flattenToString()
        val enabledSetting = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false
        val splitter = TextUtils.SimpleStringSplitter(':')
        splitter.setString(enabledSetting)
        while (splitter.hasNext()) {
            val entry = splitter.next()
            if (entry.equals(expected, ignoreCase = true)) return true
        }
        return false
    }
}
