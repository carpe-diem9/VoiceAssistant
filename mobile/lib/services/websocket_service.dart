import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../config/app_config.dart';

/// WebSocket 服务 - 管理与后端的 WebSocket 连接
class WebSocketService {
  WebSocketChannel? _channel;
  Function(Map<String, dynamic>)? onMessage;
  Function()? onDisconnect;
  bool _isConnected = false;

  bool get isConnected => _isConnected;

  /// 连接 WebSocket
  void connect(String token) {
    try {
      _channel = WebSocketChannel.connect(
        Uri.parse('${AppConfig.wsUrl}${AppConfig.wsChat}'),
      );

      // 监听消息
      _channel!.stream.listen(
        (data) {
          try {
            final json = jsonDecode(data as String);
            if (json['type'] == 'auth_success') {
              _isConnected = true;
            }
            onMessage?.call(json);
          } catch (_) {}
        },
        onDone: () {
          _isConnected = false;
          onDisconnect?.call();
        },
        onError: (error) {
          _isConnected = false;
          onDisconnect?.call();
        },
      );

      // 发送认证
      _channel!.sink.add(jsonEncode({
        'type': 'auth',
        'token': token,
      }));
    } catch (e) {
      _isConnected = false;
    }
  }

  /// 发送文本消息
  void sendTextMessage(String message, {int? sessionId}) {
    if (_channel == null) return;
    _channel!.sink.add(jsonEncode({
      'type': 'text',
      'message': message,
      if (sessionId != null) 'session_id': sessionId,
    }));
  }

  /// 发送语音消息（base64 编码的音频数据）
  void sendVoiceMessage(String audioBase64, {int? sessionId}) {
    if (_channel == null) return;
    _channel!.sink.add(jsonEncode({
      'type': 'voice',
      'audio_base64': audioBase64,
      if (sessionId != null) 'session_id': sessionId,
    }));
  }

  /// 断开连接
  void disconnect() {
    _channel?.sink.close();
    _channel = null;
    _isConnected = false;
  }
}
