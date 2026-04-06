import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../services/audio_service.dart';
import '../services/wake_word_service.dart';

/// 对话状态管理
class ChatProvider extends ChangeNotifier {
  final ApiService _api;
  final AudioService _audio = AudioService();
  final WakeWordService _wakeWord = WakeWordService();

  List<Message> _messages = [];
  int? _currentSessionId;
  bool _isLoading = false;
  bool _isRecording = false;
  bool _isSending = false;
  String? _error;

  // TTS 语音输出开关（默认：文本回答）
  bool _ttsEnabled = false;

  // 会话列表（侧边栏用）
  List<Session> _sessions = [];
  bool _isLoadingSessions = false;

  ChatProvider(this._api) {
    _loadTtsPreference();
    _initWakeWord();
  }

  List<Message> get messages => _messages;
  int? get currentSessionId => _currentSessionId;
  bool get isLoading => _isLoading;
  bool get isRecording => _isRecording;
  bool get isSending => _isSending;
  String? get error => _error;
  AudioService get audio => _audio;
  bool get ttsEnabled => _ttsEnabled;
  List<Session> get sessions => _sessions;
  bool get isLoadingSessions => _isLoadingSessions;
  WakeWordService get wakeWord => _wakeWord;

  /// 加载 TTS 偏好设置
  Future<void> _loadTtsPreference() async {
    final prefs = await SharedPreferences.getInstance();
    _ttsEnabled = prefs.getBool('tts_enabled') ?? false;
    notifyListeners();
  }

  /// 切换 TTS 开关
  Future<void> toggleTts() async {
    _ttsEnabled = !_ttsEnabled;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('tts_enabled', _ttsEnabled);
    notifyListeners();
  }

  /// 设置 TTS 模式
  Future<void> setTtsEnabled(bool value) async {
    if (_ttsEnabled == value) return;
    _ttsEnabled = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('tts_enabled', _ttsEnabled);
    notifyListeners();
  }

  /// 初始化唤醒词服务
  Future<void> _initWakeWord() async {
    _wakeWord.onStateChanged = () => notifyListeners();
    await _wakeWord.initialize(_api);
    notifyListeners();
  }

  /// 加载会话列表
  Future<void> loadSessions() async {
    _isLoadingSessions = true;
    notifyListeners();
    try {
      _sessions = await _api.getSessions();
    } catch (e) {
      _error = e.toString();
    }
    _isLoadingSessions = false;
    notifyListeners();
  }

  /// 删除会话
  Future<void> deleteSession(int sessionId) async {
    try {
      await _api.deleteSession(sessionId);
      _sessions.removeWhere((s) => s.id == sessionId);
      // 如果删除的是当前会话，清空消息
      if (_currentSessionId == sessionId) {
        _messages = [];
        _currentSessionId = null;
      }
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
    }
  }

  /// 设置当前会话
  void setSession(int? sessionId) {
    _currentSessionId = sessionId;
    _messages = [];
    notifyListeners();
  }

  /// 加载会话消息
  Future<void> loadSessionMessages(int sessionId) async {
    _isLoading = true;
    _currentSessionId = sessionId;
    notifyListeners();

    try {
      final detail = await _api.getSessionDetail(sessionId);
      final msgList = detail['messages'] as List? ?? [];
      _messages = msgList.map((m) => Message.fromJson(m)).toList();
    } catch (e) {
      _error = e.toString();
    }

    _isLoading = false;
    notifyListeners();
  }

  /// 发送文本消息（SSE 流式）
  Future<void> sendTextMessage(String text) async {
    if (text.trim().isEmpty || _isSending) return;

    _isSending = true;
    _error = null;
    _wakeWord.pause(); // 暂停唤醒词监听

    // 添加用户消息
    _messages.add(Message(role: 'user', content: text));

    // 添加助手占位消息（用于流式更新）
    final assistantMsg = Message(role: 'assistant', content: '', isStreaming: true);
    _messages.add(assistantMsg);
    notifyListeners();

    try {
      await for (final data in _api.textChatStream(text, sessionId: _currentSessionId, enableTts: _ttsEnabled)) {
        final type = data['type'];
        if (type == 'session_id') {
          _currentSessionId = data['session_id'];
        } else if (type == 'text') {
          assistantMsg.content += data['content'] ?? '';
          notifyListeners();
        } else if (type == 'audio') {
          // TTS 音频播放（失败不中断聊天流）
          if (_ttsEnabled) {
            final audioB64 = data['audio_base64'] ?? '';
            if (audioB64.isNotEmpty) {
              try {
                await _audio.playBase64Audio(audioB64, format: data['format'] ?? 'wav');
              } catch (e) {
                debugPrint('TTS playback failed: $e');
              }
            }
          }
        } else if (type == 'done') {
          assistantMsg.isStreaming = false;
          notifyListeners();
        } else if (type == 'error') {
          _error = data['message'];
          assistantMsg.content = 'Error: ${data["message"]}';
          assistantMsg.isStreaming = false;
          notifyListeners();
        }
      }
    } catch (e) {
      _error = e.toString();
      if (assistantMsg.content.isEmpty) {
        assistantMsg.content = 'Error: $e';
      }
      assistantMsg.isStreaming = false;
      notifyListeners();
    }

    _isSending = false;
    notifyListeners();
    _wakeWord.resume(); // 发送完成，恢复唤醒词监听
  }

  /// 开始录音
  Future<void> startRecording() async {
    try {
      _wakeWord.pause(); // 暂停唤醒词监听，释放麦克风
      // 等待麦克风资源完全释放（唤醒词 recorder 释放需要时间）
      await Future.delayed(const Duration(milliseconds: 500));
      await _audio.startRecording();
      _isRecording = true;
      notifyListeners();
    } catch (e) {
      _error = 'Recording failed: $e';
      debugPrint('Recording start failed: $e');
      // 录音失败时不立即 resume 唤醒词，避免无限循环
      notifyListeners();
    }
  }

  /// 停止录音并发送语音消息
  Future<void> stopRecordingAndSend() async {
    if (!_isRecording) return;

    try {
      final path = await _audio.stopRecording();
      _isRecording = false;
      notifyListeners();

      if (path == null) return;

      _isSending = true;
      notifyListeners();

      // 添加用户语音占位（等待 ASR 结果）
      final userMsg = Message(role: 'user', content: '语音识别中...');
      _messages.add(userMsg);
      notifyListeners();

      // 助手占位消息延后到收到 ASR 结果后再添加
      Message? assistantMsg;

      // 使用语音流式接口
      await for (final data in _api.voiceChatStream(path, sessionId: _currentSessionId, enableTts: _ttsEnabled)) {
        final type = data['type'];
        if (type == 'asr') {
          // 更新用户消息为识别结果
          userMsg.content = data['content'] ?? '';
          _currentSessionId = data['session_id'] ?? _currentSessionId;
          // ASR 结果到达后，添加助手占位消息
          assistantMsg = Message(role: 'assistant', content: '', isStreaming: true);
          _messages.add(assistantMsg);
          notifyListeners();
        } else if (type == 'text') {
          if (assistantMsg != null) {
            assistantMsg.content += data['content'] ?? '';
          }
          notifyListeners();
        } else if (type == 'audio') {
          // 仅在 TTS 开关打开时播放（失败不中断聊天流）
          if (_ttsEnabled) {
            final audioB64 = data['audio_base64'] ?? '';
            if (audioB64.isNotEmpty) {
              try {
                await _audio.playBase64Audio(audioB64, format: data['format'] ?? 'wav');
              } catch (e) {
                debugPrint('TTS playback failed: $e');
              }
            }
          }
        } else if (type == 'done') {
          assistantMsg?.isStreaming = false;
          notifyListeners();
        } else if (type == 'error') {
          assistantMsg?.content = 'Error: ${data["message"]}';
          assistantMsg?.isStreaming = false;
          notifyListeners();
        }
      }
    } catch (e) {
      _error = e.toString();
    }

    _isSending = false;
    notifyListeners();
    _wakeWord.resume(); // 发送完成，恢复唤醒词监听
  }

  /// 取消录音（不发送）
  Future<void> cancelRecording() async {
    if (!_isRecording) return;
    await _audio.stopRecording();
    _isRecording = false;
    notifyListeners();
    _wakeWord.resume(); // 取消录音后恢复监听
  }

  /// 停止音频播放
  Future<void> stopAudio() async {
    await _audio.stopPlaying();
    notifyListeners();
  }

  /// 清空消息
  void clearMessages() {
    _messages = [];
    _currentSessionId = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _wakeWord.dispose();
    _audio.dispose();
    super.dispose();
  }
}
