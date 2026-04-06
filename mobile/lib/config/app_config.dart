/// 应用配置 - 后端 API 地址等
class AppConfig {
  // 后端 API 基础地址（本地开发）
  // 真机通过 adb reverse tcp:8000 tcp:8000 使用 localhost
  // 模拟器使用 10.0.2.2
  static const String baseUrl = 'http://127.0.0.1:8000';
  static const String wsUrl = 'ws://127.0.0.1:8000';

  // API 路径
  static const String apiAuth = '/api/auth';
  static const String apiSessions = '/api/sessions';
  static const String apiChat = '/api/chat';
  static const String apiSettings = '/api/settings';

  // WebSocket 路径
  static const String wsChat = '/api/chat/ws';
}
