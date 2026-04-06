import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:record/record.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';
import 'api_service.dart';

/// 唤醒词监听服务 - 录制短音频 + 后端 ASR 检测唤醒词
class WakeWordService {
  final AudioRecorder _recorder = AudioRecorder();
  ApiService? _api;
  bool _isInitialized = false;
  bool _isListening = false;
  bool _enabled = false;
  bool _paused = false;
  String _wakeWord = '你好助手';
  bool _stopRequested = false;

  /// 检测到唤醒词时的回调
  VoidCallback? onWakeWordDetected;

  /// 内部状态变更时的回调（用于驱动 UI 刷新）
  VoidCallback? onStateChanged;

  bool get isListening => _isListening;
  bool get enabled => _enabled;
  bool get isPaused => _paused;
  String get wakeWord => _wakeWord;

  /// 功能是否处于活跃状态（已启用且未被暂停）
  bool get isActive => _enabled && !_paused && _isInitialized;

  void _notifyState() => onStateChanged?.call();

  /// 初始化服务并加载设置
  Future<void> initialize(ApiService api) async {
    _api = api;
    await _loadSettings();

    // 检查麦克风权限
    final hasPerm = await _recorder.hasPermission();
    _isInitialized = hasPerm;
    debugPrint('WakeWord: initialized=$_isInitialized (mic permission=$hasPerm)');

    if (_isInitialized && _enabled && !_paused) {
      _startListeningLoop();
    }
    _notifyState();
  }

  /// 加载唤醒词设置
  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _enabled = prefs.getBool('wake_word_enabled') ?? false;
    _wakeWord = prefs.getString('wake_word') ?? '你好助手';
  }

  /// 设置唤醒词启用状态
  Future<void> setEnabled(bool value) async {
    _enabled = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('wake_word_enabled', value);
    if (value && _isInitialized && !_paused) {
      _startListeningLoop();
    } else if (!value) {
      _stopListening();
    }
    _notifyState();
  }

  /// 设置唤醒词内容
  Future<void> setWakeWord(String word) async {
    if (word.trim().isEmpty) return;
    _wakeWord = word.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('wake_word', _wakeWord);
  }

  /// 启动监听循环
  void _startListeningLoop() {
    if (_isListening) return;
    _stopRequested = false;
    _isListening = true;
    _notifyState();
    _listenLoop();
  }

  /// 核心监听循环：录制短音频 → 发送后端 ASR → 检查唤醒词 → 重复
  Future<void> _listenLoop() async {
    debugPrint('WakeWord: listen loop started');

    while (_enabled && !_paused && !_stopRequested && _isInitialized) {
      String? recordPath;
      try {
        // 1. 检查权限
        if (!await _recorder.hasPermission()) {
          debugPrint('WakeWord: no mic permission, stopping');
          break;
        }

        // 2. 录制 3 秒音频
        final dir = await getTemporaryDirectory();
        recordPath = p.join(dir.path, 'wake_${DateTime.now().millisecondsSinceEpoch}.wav');

        await _recorder.start(
          const RecordConfig(
            encoder: AudioEncoder.wav,
            sampleRate: 16000,
            numChannels: 1,
            bitRate: 256000,
          ),
          path: recordPath,
        );

        // 等待 3 秒录制
        for (int i = 0; i < 30; i++) {
          await Future.delayed(const Duration(milliseconds: 100));
          if (_stopRequested || _paused || !_enabled) break;
        }

        // 停止录音
        final resultPath = await _recorder.stop();
        final filePath = resultPath ?? recordPath;

        // 如果被中断，清理退出
        if (_stopRequested || _paused || !_enabled) {
          _cleanupFile(filePath);
          break;
        }

        // 3. 发送到后端检测唤醒词
        if (_api != null && filePath != null) {
          final file = File(filePath);
          if (await file.exists() && await file.length() > 100) {
            debugPrint('WakeWord: sending audio for ASR check...');
            final result = await _api!.checkWakeWord(filePath, _wakeWord);
            final detected = result['detected'] == true;
            final text = result['text'] ?? '';
            debugPrint('WakeWord: ASR="$text", detected=$detected');

            if (detected && !_stopRequested && !_paused && _enabled) {
              _isListening = false;
              _cleanupFile(filePath);
              debugPrint('WakeWord: DETECTED! Releasing mic before callback...');
              // 等待麦克风资源彻底释放（华为设备需要较长时间）
              await Future.delayed(const Duration(milliseconds: 800));
              _notifyState();
              debugPrint('WakeWord: Triggering callback...');
              onWakeWordDetected?.call();
              return; // 检测到唤醒词，退出循环
            }
          } else {
            debugPrint('WakeWord: audio file too small, skipping');
          }
        }

        // 4. 清理临时文件
        _cleanupFile(filePath);

      } catch (e) {
        debugPrint('WakeWord: loop error: $e');
        _cleanupFile(recordPath);
        // 出错后短暂等待再重试
        await Future.delayed(const Duration(seconds: 1));
      }
    }

    _isListening = false;
    _notifyState();
    debugPrint('WakeWord: listen loop ended');
  }

  /// 停止监听
  void _stopListening() {
    _stopRequested = true;
    try {
      _recorder.stop();
    } catch (_) {}
    _isListening = false;
    _notifyState();
    debugPrint('WakeWord: stopped');
  }

  /// 公开的启动方法（供外部调用如设置页修改唤醒词后重启）
  void startListening() {
    if (_enabled && !_paused && _isInitialized && !_isListening) {
      _startListeningLoop();
    }
  }

  /// 公开的停止方法
  void stopListening() {
    _stopListening();
  }

  /// 暂停监听（录音或发送时调用，避免麦克风冲突）
  void pause() {
    _paused = true;
    _stopListening();
    debugPrint('WakeWord: paused');
    _notifyState();
  }

  /// 恢复监听（录音/发送结束后调用）
  void resume() {
    _paused = false;
    debugPrint('WakeWord: resumed');
    _notifyState();
    if (_enabled && _isInitialized) {
      // 延迟恢复，确保录音资源完全释放
      Future.delayed(const Duration(milliseconds: 800), () {
        if (!_paused && _enabled && !_isListening) {
          _startListeningLoop();
        }
      });
    }
  }

  /// 清理临时文件
  void _cleanupFile(String? path) {
    if (path == null) return;
    try {
      final file = File(path);
      if (file.existsSync()) file.deleteSync();
    } catch (_) {}
  }

  void dispose() {
    _stopListening();
    _recorder.dispose();
  }
}
