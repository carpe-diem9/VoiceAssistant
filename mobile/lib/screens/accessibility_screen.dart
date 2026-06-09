import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../services/accessibility_bridge.dart';
import '../services/api_service.dart';
import '../services/audio_service.dart';

/// 无障碍朗读中心页
///
/// 功能：
/// - 检查 & 申请无障碍服务和悬浮窗权限
/// - 启动/关闭跨应用悬浮球
/// - 接收悬浮球捕获的文本 → 展示（原生层直接 POST 后端并播放 TTS）
/// - 随时停止正在进行的朗读
class AccessibilityScreen extends StatefulWidget {
  const AccessibilityScreen({super.key});

  @override
  State<AccessibilityScreen> createState() => _AccessibilityScreenState();
}

class _AccessibilityScreenState extends State<AccessibilityScreen>
    with WidgetsBindingObserver {
  final ApiService _api = ApiService();
  final AudioService _audio = AudioService();

  bool _accessibilityEnabled = false;
  bool _overlayGranted = false;
  bool _floatingRunning = false;
  bool _processing = false;
  String? _lastCapturedText;
  String? _lastProcessedText;
  String? _lastMode; // 'read' | 'summary'，供「重新朗读」使用
  String? _status;

  StreamSubscription<Map<String, String>>? _textSub;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    // 注入 token
    final auth = Provider.of<AuthProvider>(context, listen: false);
    if (auth.token != null) {
      _api.setToken(auth.token!);
    }

    _refreshStatus();
    _subscribeTextStream();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // 从系统设置返回时刷新状态
    if (state == AppLifecycleState.resumed) {
      _refreshStatus();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _textSub?.cancel();
    _audio.dispose();
    super.dispose();
  }

  Future<void> _refreshStatus() async {
    final acc = await AccessibilityBridge.isAccessibilityEnabled();
    final ov = await AccessibilityBridge.isOverlayGranted();
    final run = await AccessibilityBridge.isFloatingBallRunning();
    if (!mounted) return;
    setState(() {
      _accessibilityEnabled = acc;
      _overlayGranted = ov;
      _floatingRunning = run;
    });
  }

  void _subscribeTextStream() {
    _textSub = AccessibilityBridge.onTextCaptured.listen((data) {
      final text = data['text'] ?? '';
      final mode = data['mode'] ?? 'summary';
      if (text.trim().isEmpty) return;
      _handleCapturedText(text, mode);
    }, onError: (e) {
      _showSnack('接收文字失败：$e');
    });
  }

  Future<void> _handleCapturedText(String text, String mode) async {
    if (_processing) return;
    setState(() {
      _processing = true;
      _lastCapturedText = text;
      _lastProcessedText = null;
      _lastMode = mode;
      _status = mode == 'read' ? '正在整理原文…' : '正在 LLM 总结…';
    });
    try {
      final style = (mode == 'read') ? 'read' : 'summary';
      // 注：实际的 HTTP+播放已由原生 TextReadClient 在悬浮球触发时完成，
      // 这里再请求一次仅用于 UI 展示处理后的文本（不要求返回音频）
      final resp = await _api.readText(text, style: style, enableTts: false);
      final processed = (resp['text'] ?? '').toString();
      if (!mounted) return;
      setState(() {
        _lastProcessedText = processed;
        _status = '已请求朗读';
      });
    } catch (e) {
      if (mounted) {
        setState(() => _status = '失败：$e');
      }
    } finally {
      if (mounted) {
        setState(() => _processing = false);
      }
    }
  }

  Future<void> _toggleFloatingBall() async {
    if (_floatingRunning) {
      await AccessibilityBridge.stopFloatingBall();
      // 悬浮球关闭前立即停止正在进行的朗读
      await AccessibilityBridge.stopReading();
      // 等待 Service onDestroy 落地后再刷新状态
      await Future.delayed(const Duration(milliseconds: 400));
      if (mounted) {
        setState(() {
          _floatingRunning = false;
        });
      }
      await _refreshStatus();
      return;
    }
    if (!_accessibilityEnabled) {
      _showSnack('请先开启无障碍服务');
      return;
    }
    if (!_overlayGranted) {
      _showSnack('请先授予悬浮窗权限');
      await AccessibilityBridge.requestOverlayPermission();
      return;
    }
    try {
      await AccessibilityBridge.startFloatingBall();
      await Future.delayed(const Duration(milliseconds: 300));
      await _refreshStatus();
      _showSnack('悬浮球已启动，可切到其他 APP 使用');
    } catch (e) {
      _showSnack('启动失败：$e');
    }
  }

  void _showSnack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('无障碍朗读'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: '刷新状态',
            onPressed: _refreshStatus,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _buildIntroCard(theme),
          const SizedBox(height: 12),
          _buildPermissionCard(theme),
          const SizedBox(height: 12),
          _buildFloatingBallCard(theme),
          const SizedBox(height: 12),
          if (_lastCapturedText != null) _buildCaptureCard(theme),
        ],
      ),
    );
  }

  Widget _buildIntroCard(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.accessibility_new, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                const Text(
                  '跨应用朗读',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 8),
            const Text(
              '启动悬浮球后，在任意 APP 中点击悬浮球菜单，即可朗读整屏内容或精准点选元素文字。\n'
              '支持「原文朗读」和「LLM 总结朗读」两种模式。',
              style: TextStyle(fontSize: 13, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPermissionCard(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('权限状态',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            _permRow(
              icon: Icons.accessibility,
              label: '无障碍服务',
              desc: '读取其他 APP 屏幕文字',
              granted: _accessibilityEnabled,
              action: AccessibilityBridge.openAccessibilitySettings,
            ),
            const Divider(),
            _permRow(
              icon: Icons.filter_none,
              label: '悬浮窗权限',
              desc: '在其他 APP 上层显示悬浮球',
              granted: _overlayGranted,
              action: AccessibilityBridge.requestOverlayPermission,
            ),
          ],
        ),
      ),
    );
  }

  Widget _permRow({
    required IconData icon,
    required String label,
    required String desc,
    required bool granted,
    required Future<void> Function() action,
  }) {
    return Row(
      children: [
        Icon(icon, color: granted ? Colors.green : Colors.orange),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label,
                  style: const TextStyle(fontWeight: FontWeight.w500)),
              Text(desc,
                  style: TextStyle(fontSize: 12, color: Colors.grey[600])),
            ],
          ),
        ),
        granted
            ? const Chip(
                label: Text('已授权'),
                backgroundColor: Color(0xFFE8F5E9),
                labelStyle: TextStyle(color: Colors.green, fontSize: 12),
              )
            : TextButton(
                onPressed: () async {
                  await action();
                  await Future.delayed(const Duration(milliseconds: 500));
                  _refreshStatus();
                },
                child: const Text('去开启'),
              ),
      ],
    );
  }

  Widget _buildFloatingBallCard(ThemeData theme) {
    final ready = _accessibilityEnabled && _overlayGranted;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('跨应用悬浮球',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
                const Spacer(),
                if (_floatingRunning)
                  const Chip(
                    label: Text('运行中'),
                    backgroundColor: Color(0xFFE3F2FD),
                    labelStyle: TextStyle(color: Colors.blue, fontSize: 12),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              ready
                  ? '启动后可在任意 APP 上层操作；关闭后悬浮球消失'
                  : '请先授予上方两项权限',
              style: TextStyle(fontSize: 12, color: Colors.grey[600]),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: ready ? _toggleFloatingBall : null,
                icon: Icon(
                  _floatingRunning ? Icons.stop_circle : Icons.play_circle,
                ),
                label: Text(_floatingRunning ? '关闭悬浮球' : '启动悬浮球'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCaptureCard(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.text_snippet, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                const Text('最近捕获',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
                const Spacer(),
                if (_processing)
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
            if (_status != null) ...[
              const SizedBox(height: 8),
              Text('状态：$_status',
                  style: TextStyle(fontSize: 12, color: Colors.grey[700])),
            ],
            const SizedBox(height: 12),
            Text('原始文本：',
                style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey[600],
                    fontWeight: FontWeight.w500)),
            const SizedBox(height: 4),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.grey[100],
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                _lastCapturedText ?? '',
                style: const TextStyle(fontSize: 13),
                maxLines: 6,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (_lastProcessedText != null) ...[
              const SizedBox(height: 12),
              Text('朗读文本：',
                  style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey[600],
                      fontWeight: FontWeight.w500)),
              const SizedBox(height: 4),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withOpacity(0.06),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  _lastProcessedText!,
                  style: const TextStyle(fontSize: 13, height: 1.5),
                ),
              ),
              const SizedBox(height: 8),
              TextButton.icon(
                onPressed: _processing
                    ? null
                    : () async {
                        // 重新用上次模式再处理一次
                        final mode = _lastMode ?? 'summary';
                        if (_lastCapturedText != null) {
                          await _handleCapturedText(
                              _lastCapturedText!, mode);
                        }
                      },
                icon: const Icon(Icons.refresh, size: 16),
                label: const Text('重新朗读'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
