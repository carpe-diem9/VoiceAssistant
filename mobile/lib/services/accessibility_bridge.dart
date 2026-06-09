import 'package:flutter/services.dart';

/// 安卓原生无障碍桥接
class AccessibilityBridge {
  static const MethodChannel _method =
      MethodChannel('voice_assistant/accessibility');
  static const EventChannel _event =
      EventChannel('voice_assistant/accessibility_events');

  static Future<bool> isAccessibilityEnabled() async {
    try {
      return await _method.invokeMethod<bool>('isAccessibilityEnabled') ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<void> openAccessibilitySettings() async {
    try {
      await _method.invokeMethod('openAccessibilitySettings');
    } catch (_) {}
  }

  static Future<bool> isOverlayGranted() async {
    try {
      return await _method.invokeMethod<bool>('isOverlayGranted') ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<void> requestOverlayPermission() async {
    try {
      await _method.invokeMethod('requestOverlayPermission');
    } catch (_) {}
  }

  static Future<void> startFloatingBall() async {
    await _method.invokeMethod('startFloatingBall');
  }

  static Future<void> stopFloatingBall() async {
    try {
      await _method.invokeMethod('stopFloatingBall');
    } catch (_) {}
  }

  /// 立即停止当前原生 TTS 播放
  static Future<void> stopReading() async {
    try {
      await _method.invokeMethod('stopReading');
    } catch (_) {}
  }

  static Future<bool> isFloatingBallRunning() async {
    try {
      return await _method.invokeMethod<bool>('isFloatingBallRunning') ?? false;
    } catch (_) {
      return false;
    }
  }

  /// 监听悬浮球捕获到的文字
  /// 返回数据：{text: String, mode: 'read' | 'summary'}
  static Stream<Map<String, String>> get onTextCaptured =>
      _event.receiveBroadcastStream().map((event) {
        if (event is Map) {
          return {
            'text': (event['text'] ?? '').toString(),
            'mode': (event['mode'] ?? 'summary').toString(),
          };
        }
        return <String, String>{};
      });
}
