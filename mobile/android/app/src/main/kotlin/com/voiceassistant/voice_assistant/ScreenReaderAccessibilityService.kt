package com.voiceassistant.voice_assistant

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo

/**
 * 屏幕文字抽取无障碍服务
 * - 提供坐标命中查询（点击元素朗读）
 * - 提供整屏可见文字拼接（整屏朗读 / 总结）
 */
class ScreenReaderAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "VA_ACC"

        @Volatile
        private var instance: ScreenReaderAccessibilityService? = null

        fun isRunning(): Boolean = instance != null

        /** 获取屏幕坐标 (x,y) 所在节点文本 */
        fun getTextAtPosition(x: Int, y: Int): String? {
            val r = instance?.findTextAtPosition(x, y)
            Log.d(TAG, "getTextAtPosition($x,$y) len=${r?.length ?: -1}")
            return r
        }

        /** 获取当前窗口的所有可见文本 */
        fun getAllVisibleText(): String {
            val t = instance?.collectAllText() ?: ""
            Log.d(TAG, "getAllVisibleText len=${t.length}")
            return t
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.d(TAG, "onServiceConnected")
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // 不需要处理事件，只在需要时主动读取节点
    }

    override fun onInterrupt() {}

    // === 工具 ===

    /**
     * 返回用户前台 APP 的根节点
     * 1) 从 windows 列表中找「active/focused 的应用窗口」，排除自身包名、systemui、输入法
     * 2) 否则按 layer 倒序取首个非自身 TYPE_APPLICATION 窗口
     * 3) 都不行就回退 rootInActiveWindow（若它的包名是自己则返回 null）
     */
    private fun findForegroundRoot(): AccessibilityNodeInfo? {
        val myPkg = packageName
        try {
            val ws = windows
            Log.d(TAG, "windows.size=${ws?.size ?: -1}")
            if (ws != null && ws.isNotEmpty()) {
                // 打印每个窗口的摘要
                for (w in ws) {
                    val r = try { w.root } catch (_: Throwable) { null }
                    Log.d(TAG, "  win type=${w.type} layer=${w.layer} active=${w.isActive} focused=${w.isFocused} pkg=${r?.packageName}")
                }
                // 1) 优先 active/focused 的应用窗口
                for (w in ws) {
                    if (w.type != AccessibilityWindowInfo.TYPE_APPLICATION) continue
                    if (!(w.isActive || w.isFocused)) continue
                    val root = w.root ?: continue
                    val pkg = root.packageName?.toString() ?: ""
                    if (pkg.isEmpty() || pkg == myPkg) continue
                    if (pkg == "com.android.systemui" || pkg.contains("inputmethod")) continue
                    Log.d(TAG, "pick(active)=$pkg")
                    return root
                }
                // 2) layer 倒序取最顶层 APP 窗口
                val sorted = ws.sortedByDescending { it.layer }
                for (w in sorted) {
                    if (w.type != AccessibilityWindowInfo.TYPE_APPLICATION) continue
                    val root = w.root ?: continue
                    val pkg = root.packageName?.toString() ?: ""
                    if (pkg.isEmpty() || pkg == myPkg) continue
                    if (pkg == "com.android.systemui" || pkg.contains("inputmethod")) continue
                    Log.d(TAG, "pick(top)=$pkg")
                    return root
                }
            }
        } catch (e: Throwable) {
            Log.w(TAG, "windows() failed", e)
        }
        // 3) 回退 rootInActiveWindow
        val root = rootInActiveWindow
        val pkg = root?.packageName?.toString() ?: ""
        Log.d(TAG, "fallback rootInActiveWindow pkg=$pkg")
        if (pkg.isEmpty() || pkg == myPkg) return null
        return root
    }

    private fun findTextAtPosition(x: Int, y: Int): String? {
        val root = findForegroundRoot() ?: return null
        val hit = findHitNode(root, x, y) ?: return null
        return extractText(hit)
    }

    private fun findHitNode(node: AccessibilityNodeInfo, x: Int, y: Int): AccessibilityNodeInfo? {
        val rect = Rect()
        node.getBoundsInScreen(rect)
        if (!rect.contains(x, y)) return null
        // 先找最深的命中子节点
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val deeper = findHitNode(child, x, y)
            if (deeper != null) return deeper
        }
        return node
    }

    private fun extractText(node: AccessibilityNodeInfo): String {
        val sb = StringBuilder()
        val t = node.text?.toString()
        if (!t.isNullOrBlank()) sb.append(t).append('\n')
        val d = node.contentDescription?.toString()
        if (!d.isNullOrBlank() && d != t) sb.append(d).append('\n')
        // 向下补子节点文本（最多拼 500 字以避免过长）
        for (i in 0 until node.childCount) {
            if (sb.length > 500) break
            val c = node.getChild(i) ?: continue
            val ct = extractText(c)
            if (ct.isNotBlank()) sb.append(ct)
        }
        return sb.toString().trim()
    }

    private fun collectAllText(): String {
        val root = findForegroundRoot() ?: return ""
        val sb = StringBuilder()
        walk(root, sb)
        return sb.toString().replace(Regex("\\n{3,}"), "\n\n").trim()
    }

    private fun walk(node: AccessibilityNodeInfo, sb: StringBuilder) {
        val t = node.text?.toString()
        if (!t.isNullOrBlank()) sb.append(t).append('\n')
        val d = node.contentDescription?.toString()
        if (!d.isNullOrBlank() && d != t) sb.append(d).append('\n')
        for (i in 0 until node.childCount) {
            val c = node.getChild(i) ?: continue
            walk(c, sb)
        }
    }
}
