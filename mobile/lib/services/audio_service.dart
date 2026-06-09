import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:record/record.dart';
import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;

/// 音频服务 - 录音和播放控制
class AudioService {
  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();
  bool _isRecording = false;
  String? _currentRecordingPath;
  String? _lastPlaybackPath;

  bool get isRecording => _isRecording;
  bool get isPlaying => _player.playing;

  /// 开始录音
  Future<void> startRecording() async {
    if (_isRecording) return;

    // 检查权限
    if (!await _recorder.hasPermission()) {
      throw Exception('No microphone permission');
    }

    // 获取临时目录
    final dir = await getTemporaryDirectory();
    _currentRecordingPath = p.join(dir.path, 'recording_${DateTime.now().millisecondsSinceEpoch}.wav');

    // 开始录音 - WAV 格式, 16kHz, 单声道
    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: 16000,
        numChannels: 1,
        bitRate: 256000,
      ),
      path: _currentRecordingPath!,
    );
    _isRecording = true;
  }

  /// 停止录音并返回文件路径
  Future<String?> stopRecording() async {
    if (!_isRecording) return null;

    final path = await _recorder.stop();
    _isRecording = false;
    return path ?? _currentRecordingPath;
  }

  /// 播放 base64 编码的音频数据
  Future<void> playBase64Audio(String base64Audio, {String format = 'wav'}) async {
    try {
      final bytes = base64Decode(base64Audio);
      await playBytes(bytes, format: format);
    } catch (e) {
      throw Exception('Audio playback failed: $e');
    }
  }

  /// 播放音频字节数据
  Future<void> playBytes(Uint8List bytes, {String format = 'wav'}) async {
    try {
      // 先停止并重置播放器状态，避免 completed 状态下无法重新播放
      try {
        await _player.stop();
      } catch (_) {}

      // 清理上次的临时播放文件
      if (_lastPlaybackPath != null) {
        try {
          final old = File(_lastPlaybackPath!);
          if (await old.exists()) await old.delete();
        } catch (_) {}
      }

      final dir = await getTemporaryDirectory();
      final filePath = p.join(dir.path, 'playback_${DateTime.now().millisecondsSinceEpoch}.$format');
      final file = File(filePath);
      await file.writeAsBytes(bytes);
      _lastPlaybackPath = filePath;

      // setAudioSource 比 setFilePath 更可靠
      await _player.setFilePath(filePath);
      await _player.seek(Duration.zero);
      await _player.play();
    } catch (e) {
      throw Exception('Audio playback failed: $e');
    }
  }

  /// 停止播放
  Future<void> stopPlaying() async {
    try {
      await _player.stop();
    } catch (_) {}
  }

  /// 获取录音文件的 base64 编码
  Future<String?> getRecordingBase64() async {
    if (_currentRecordingPath == null) return null;
    final file = File(_currentRecordingPath!);
    if (!await file.exists()) return null;
    final bytes = await file.readAsBytes();
    return base64Encode(bytes);
  }

  /// 释放资源
  void dispose() {
    _recorder.dispose();
    _player.dispose();
  }
}
