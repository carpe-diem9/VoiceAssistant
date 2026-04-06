import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/app_config.dart';
import '../models/models.dart';

class ApiService {
  String? _token;

  void setToken(String token) {
    _token = token;
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Future<Map<String, dynamic>> _get(String path) async {
    final response = await http.get(
      Uri.parse('${AppConfig.baseUrl}$path'),
      headers: _headers,
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(utf8.decode(response.bodyBytes));
    }
    throw Exception(_parseError(response));
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final response = await http.post(
      Uri.parse('${AppConfig.baseUrl}$path'),
      headers: _headers,
      body: jsonEncode(body),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(utf8.decode(response.bodyBytes));
    }
    throw Exception(_parseError(response));
  }

  Future<Map<String, dynamic>> _put(String path, Map<String, dynamic> body) async {
    final response = await http.put(
      Uri.parse('${AppConfig.baseUrl}$path'),
      headers: _headers,
      body: jsonEncode(body),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(utf8.decode(response.bodyBytes));
    }
    throw Exception(_parseError(response));
  }

  Future<void> _delete(String path) async {
    final response = await http.delete(
      Uri.parse('${AppConfig.baseUrl}$path'),
      headers: _headers,
    );
    if (response.statusCode >= 300) {
      throw Exception(_parseError(response));
    }
  }

  String _parseError(http.Response response) {
    try {
      final body = jsonDecode(utf8.decode(response.bodyBytes));
      return body['detail'] ?? 'Error ${response.statusCode}';
    } catch (_) {
      return 'Error ${response.statusCode}';
    }
  }

  // ===== Auth =====
  Future<AuthResponse> register(String username, String password) async {
    final data = await _post('${AppConfig.apiAuth}/register', {
      'username': username,
      'password': password,
    });
    return AuthResponse.fromJson(data);
  }

  Future<AuthResponse> login(String username, String password) async {
    final data = await _post('${AppConfig.apiAuth}/login', {
      'username': username,
      'password': password,
    });
    return AuthResponse.fromJson(data);
  }

  Future<User> getMe() async {
    final data = await _get('${AppConfig.apiAuth}/me');
    return User.fromJson(data);
  }

  // ===== Sessions =====
  Future<List<Session>> getSessions() async {
    final data = await _get(AppConfig.apiSessions);
    final list = data['sessions'] as List;
    return list.map((e) => Session.fromJson(e)).toList();
  }

  Future<Session> createSession({String title = 'New Chat'}) async {
    final data = await _post(AppConfig.apiSessions, {'title': title});
    return Session.fromJson(data);
  }

  Future<Map<String, dynamic>> getSessionDetail(int sessionId) async {
    return await _get('${AppConfig.apiSessions}/$sessionId');
  }

  Future<Session> updateSession(int sessionId, String title) async {
    final data = await _put('${AppConfig.apiSessions}/$sessionId', {'title': title});
    return Session.fromJson(data);
  }

  Future<void> deleteSession(int sessionId) async {
    await _delete('${AppConfig.apiSessions}/$sessionId');
  }

  // ===== Chat SSE =====

  /// 正确解析 SSE 流：跨 TCP chunk 缓冲不完整的行
  Stream<Map<String, dynamic>> _parseSseStream(http.StreamedResponse response) async* {
    String buffer = '';
    await for (final chunk in response.stream.transform(utf8.decoder)) {
      buffer += chunk;
      // 按换行符分割，最后一段可能不完整需保留
      final lines = buffer.split('\n');
      buffer = lines.removeLast(); // 保留未以 \n 结尾的不完整部分
      for (final line in lines) {
        final trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          try {
            final data = jsonDecode(trimmed.substring(6));
            yield data;
          } catch (_) {}
        }
      }
    }
    // 处理 buffer 中最后剩余的数据
    if (buffer.trim().startsWith('data: ')) {
      try {
        final data = jsonDecode(buffer.trim().substring(6));
        yield data;
      } catch (_) {}
    }
  }

  Stream<Map<String, dynamic>> textChatStream(String message, {int? sessionId, bool enableTts = false}) async* {
    final request = http.Request(
      'POST',
      Uri.parse('${AppConfig.baseUrl}${AppConfig.apiChat}/text'),
    );
    request.headers.addAll(_headers);
    request.body = jsonEncode({
      'message': message,
      if (sessionId != null) 'session_id': sessionId,
      'enable_tts': enableTts,
    });

    final response = await http.Client().send(request);
    yield* _parseSseStream(response);
  }

  // Voice chat - upload audio file
  Future<Map<String, dynamic>> voiceChat(String audioPath, {int? sessionId}) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('${AppConfig.baseUrl}${AppConfig.apiChat}/voice'),
    );
    request.headers['Authorization'] = 'Bearer $_token';
    request.files.add(await http.MultipartFile.fromPath('audio', audioPath));
    if (sessionId != null) {
      request.fields['session_id'] = sessionId.toString();
    }

    final response = await request.send();
    final responseBody = await response.stream.bytesToString();
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(responseBody);
    }
    throw Exception('Voice chat failed (${response.statusCode})');
  }

  // Voice chat SSE stream
  Stream<Map<String, dynamic>> voiceChatStream(String audioPath, {int? sessionId, bool enableTts = false}) async* {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('${AppConfig.baseUrl}${AppConfig.apiChat}/voice/stream'),
    );
    request.headers['Authorization'] = 'Bearer $_token';
    request.files.add(await http.MultipartFile.fromPath('audio', audioPath));
    if (sessionId != null) {
      request.fields['session_id'] = sessionId.toString();
    }
    request.fields['enable_tts'] = enableTts.toString();

    final response = await request.send();
    yield* _parseSseStream(response);
  }

  // Deep Research SSE
  Stream<Map<String, dynamic>> deepResearchStream(String question, {int? sessionId}) async* {
    final request = http.Request(
      'POST',
      Uri.parse('${AppConfig.baseUrl}${AppConfig.apiChat}/deep-research'),
    );
    request.headers.addAll(_headers);
    request.body = jsonEncode({
      'question': question,
      if (sessionId != null) 'session_id': sessionId,
    });

    final response = await http.Client().send(request);
    yield* _parseSseStream(response);
  }

  // ===== Wake Word =====
  /// 发送短音频到后端进行唤醒词检测
  Future<Map<String, dynamic>> checkWakeWord(String audioPath, String wakeWord) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('${AppConfig.baseUrl}${AppConfig.apiChat}/wake-word'),
    );
    request.headers['Authorization'] = 'Bearer $_token';
    request.files.add(await http.MultipartFile.fromPath('audio', audioPath));
    request.fields['wake_word'] = wakeWord;

    final response = await request.send();
    final body = await response.stream.bytesToString();
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(body);
    }
    return {'detected': false, 'text': ''};
  }

  // ===== Settings =====
  Future<TTSSettings> getTTSSettings() async {
    final data = await _get('${AppConfig.apiSettings}/tts');
    return TTSSettings.fromJson(data);
  }

  Future<TTSSettings> updateTTSSettings(TTSSettings s) async {
    final data = await _put('${AppConfig.apiSettings}/tts', s.toJson());
    return TTSSettings.fromJson(data);
  }

  Future<Map<String, dynamic>> getModels() async {
    return await _get('${AppConfig.apiSettings}/models');
  }

  Future<void> updateModel(String model) async {
    await _put('${AppConfig.apiSettings}/models', {'llm_model': model});
  }
}
