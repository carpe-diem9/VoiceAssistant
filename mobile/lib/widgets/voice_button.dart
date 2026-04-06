import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';

/// 语音录制按钮 - 点击开始/结束录音，带波形动画
class VoiceButton extends StatelessWidget {
  final bool isRecording;
  final bool isSending;
  final VoidCallback onToggle;

  const VoiceButton({
    super.key,
    required this.isRecording,
    required this.isSending,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final bool disabled = isSending;

    return GestureDetector(
      onTap: disabled ? null : onToggle,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: isRecording ? 56 : 48,
        height: isRecording ? 56 : 48,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: disabled
              ? Colors.grey[400]
              : isRecording
                  ? Colors.red
                  : theme.colorScheme.primary,
          boxShadow: isRecording && !disabled
              ? [
                  BoxShadow(
                    color: Colors.red.withOpacity(0.4),
                    blurRadius: 16,
                    spreadRadius: 4,
                  )
                ]
              : null,
        ),
        child: Icon(
          isRecording ? Icons.stop : Icons.mic,
          color: disabled ? Colors.white60 : Colors.white,
          size: isRecording ? 26 : 24,
        ),
      ),
    );
  }
}

/// 录音波形叠加层 - 全屏半透明，显示波形动画和录音时长
class VoiceRecordingOverlay extends StatefulWidget {
  final VoidCallback onStop;
  final VoidCallback onCancel;

  const VoiceRecordingOverlay({
    super.key,
    required this.onStop,
    required this.onCancel,
  });

  @override
  State<VoiceRecordingOverlay> createState() => _VoiceRecordingOverlayState();
}

class _VoiceRecordingOverlayState extends State<VoiceRecordingOverlay>
    with TickerProviderStateMixin {
  late Timer _durationTimer;
  late AnimationController _waveController;
  int _seconds = 0;
  final List<double> _waveHeights = List.generate(30, (_) => 0.1);
  final _random = Random();

  @override
  void initState() {
    super.initState();
    // 录音计时器
    _durationTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _seconds++);
    });
    // 波形动画控制器
    _waveController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 100),
    )..addListener(_updateWave);
    _waveController.repeat();
  }

  void _updateWave() {
    if (!mounted) return;
    setState(() {
      for (int i = 0; i < _waveHeights.length; i++) {
        // 模拟音量波形
        _waveHeights[i] = 0.1 + _random.nextDouble() * 0.8;
      }
    });
  }

  @override
  void dispose() {
    _durationTimer.cancel();
    _waveController.removeListener(_updateWave);
    _waveController.dispose();
    super.dispose();
  }

  String _formatDuration(int seconds) {
    final m = (seconds ~/ 60).toString().padLeft(2, '0');
    final s = (seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;

    return Material(
      color: Colors.black54,
      child: SafeArea(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Spacer(flex: 2),
            // 录音状态文字
            Text(
              '正在录音...',
              style: TextStyle(
                color: Colors.white,
                fontSize: 20,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 16),
            // 录音时长
            Text(
              _formatDuration(_seconds),
              style: const TextStyle(
                color: Colors.white70,
                fontSize: 48,
                fontWeight: FontWeight.w300,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
            ),
            const SizedBox(height: 40),
            // 波形动画
            SizedBox(
              height: 80,
              width: screenWidth * 0.8,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: List.generate(_waveHeights.length, (i) {
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 80),
                    margin: const EdgeInsets.symmetric(horizontal: 1.5),
                    width: (screenWidth * 0.8 - _waveHeights.length * 3) / _waveHeights.length,
                    height: 8 + _waveHeights[i] * 64,
                    decoration: BoxDecoration(
                      color: Colors.red.withOpacity(0.6 + _waveHeights[i] * 0.4),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  );
                }),
              ),
            ),
            const Spacer(flex: 2),
            // 操作按钮区
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                // 取消按钮
                Column(
                  children: [
                    GestureDetector(
                      onTap: widget.onCancel,
                      child: Container(
                        width: 60,
                        height: 60,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: Colors.white.withOpacity(0.2),
                        ),
                        child: const Icon(Icons.close, color: Colors.white, size: 28),
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text('取消', style: TextStyle(color: Colors.white70, fontSize: 13)),
                  ],
                ),
                // 结束录音按钮
                Column(
                  children: [
                    GestureDetector(
                      onTap: widget.onStop,
                      child: Container(
                        width: 72,
                        height: 72,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: Colors.red,
                          boxShadow: [
                            BoxShadow(
                              color: Colors.red.withOpacity(0.5),
                              blurRadius: 20,
                              spreadRadius: 4,
                            ),
                          ],
                        ),
                        child: const Icon(Icons.stop, color: Colors.white, size: 36),
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text('完成', style: TextStyle(color: Colors.white70, fontSize: 13)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 48),
          ],
        ),
      ),
    );
  }
}
