import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../providers/chat_provider.dart';

/// Settings screen - TTS voice/speed/pitch, model selection
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  TTSSettings? _ttsSettings;
  bool _isLoading = true;
  bool _isSaving = false;
  final _wakeWordController = TextEditingController();
  bool _wakeWordControllerInited = false;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  @override
  void dispose() {
    _wakeWordController.dispose();
    super.dispose();
  }

  Future<void> _loadSettings() async {
    try {
      final api = Provider.of<ApiService>(context, listen: false);
      _ttsSettings = await api.getTTSSettings();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('加载设置失败: $e')),
        );
      }
    }
    if (mounted) setState(() => _isLoading = false);
  }

  void _saveWakeWord(dynamic wakeWord) {
    final value = _wakeWordController.text.trim();
    if (value.isEmpty) return;
    wakeWord.setWakeWord(value);
    // 重启监听以使用新唤醒词
    if (wakeWord.enabled) {
      wakeWord.stopListening();
      wakeWord.startListening();
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('唤醒词已设置为："$value"')),
    );
  }

  Future<void> _saveSettings() async {
    if (_ttsSettings == null) return;
    setState(() => _isSaving = true);
    try {
      final api = Provider.of<ApiService>(context, listen: false);
      await api.updateTTSSettings(_ttsSettings!);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('设置已保存')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: $e')),
        );
      }
    }
    if (mounted) setState(() => _isSaving = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('设置'),
        actions: [
          TextButton(
            onPressed: _isSaving ? null : _saveSettings,
            child: _isSaving
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('保存'),
          ),
        ],
      ),
      body: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // 语音设置
                Text('语音设置', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                const SizedBox(height: 16),

                if (_isLoading)
                  const Card(
                    child: Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                  )
                else if (_ttsSettings == null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Center(
                        child: Column(
                          children: [
                            const Text('加载语音设置失败'),
                            const SizedBox(height: 8),
                            TextButton(onPressed: () { setState(() => _isLoading = true); _loadSettings(); }, child: const Text('重试')),
                          ],
                        ),
                      ),
                    ),
                  )
                else ...[
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('音色', style: TextStyle(fontWeight: FontWeight.w500)),
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: (_ttsSettings!.availableVoices.isEmpty
                                      ? ['Cherry', 'Serena', 'Ethan', 'Chelsie', 'Aura', 'Breeze', 'Ember', 'Luna']
                                      : _ttsSettings!.availableVoices)
                                  .map((voice) => ChoiceChip(
                                        label: Text(voice),
                                        selected: _ttsSettings!.voice == voice,
                                        onSelected: (selected) {
                                          if (selected) {
                                            setState(() => _ttsSettings!.voice = voice);
                                          }
                                        },
                                      ))
                                  .toList(),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // 语速
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('语速', style: TextStyle(fontWeight: FontWeight.w500)),
                                Text('${_ttsSettings!.speed.toStringAsFixed(1)}x'),
                              ],
                            ),
                            Slider(
                              value: _ttsSettings!.speed,
                              min: 0.5,
                              max: 2.0,
                              divisions: 15,
                              label: '${_ttsSettings!.speed.toStringAsFixed(1)}x',
                              onChanged: (v) => setState(() => _ttsSettings!.speed = v),
                            ),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text('0.5x', style: TextStyle(fontSize: 12, color: Colors.grey[500])),
                                Text('1.0x', style: TextStyle(fontSize: 12, color: Colors.grey[500])),
                                Text('2.0x', style: TextStyle(fontSize: 12, color: Colors.grey[500])),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // 音调
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('音调', style: TextStyle(fontWeight: FontWeight.w500)),
                                Text(_ttsSettings!.pitch.toStringAsFixed(1)),
                              ],
                            ),
                            Slider(
                              value: _ttsSettings!.pitch,
                              min: 0.5,
                              max: 2.0,
                              divisions: 15,
                              label: _ttsSettings!.pitch.toStringAsFixed(1),
                              onChanged: (v) => setState(() => _ttsSettings!.pitch = v),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // 音量
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('音量', style: TextStyle(fontWeight: FontWeight.w500)),
                                Text('${_ttsSettings!.volume}'),
                              ],
                            ),
                            Slider(
                              value: _ttsSettings!.volume.toDouble(),
                              min: 0,
                              max: 100,
                              divisions: 20,
                              label: '${_ttsSettings!.volume}',
                              onChanged: (v) => setState(() => _ttsSettings!.volume = v.round()),
                            ),
                          ],
                        ),
                      ),
                    ),
                    ], // end else (TTS settings loaded)
                    const SizedBox(height: 24),

                    // 模型设置
                    Text('模型设置', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                    const SizedBox(height: 16),
                    Card(
                      child: ListTile(
                        leading: const Icon(Icons.smart_toy_outlined),
                        title: const Text('语言模型'),
                        subtitle: const Text('qwen3.5-plus'),
                        trailing: const Icon(Icons.chevron_right),
                      ),
                    ),
                    const SizedBox(height: 24),

                    // 语音唤醒设置
                    Text('语音唤醒', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                    const SizedBox(height: 16),
                    _buildWakeWordSettings(context, theme),
                  ],
                ),
    );
  }

  Widget _buildWakeWordSettings(BuildContext context, ThemeData theme) {
    final chat = Provider.of<ChatProvider>(context);
    final wakeWord = chat.wakeWord;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 启用开关
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('启用语音唤醒', style: TextStyle(fontWeight: FontWeight.w500)),
              subtitle: Text(
                wakeWord.enabled
                    ? (wakeWord.isActive
                        ? '正在监听唤醒词...'
                        : '已启用（暂停中）')
                    : '关闭后需手动点击麦克风录音',
                style: TextStyle(fontSize: 12, color: Colors.grey[600]),
              ),
              secondary: Icon(
                wakeWord.enabled ? Icons.hearing : Icons.hearing_disabled,
                color: wakeWord.isActive ? theme.colorScheme.primary : Colors.grey,
              ),
              value: wakeWord.enabled,
              onChanged: (v) async {
                await wakeWord.setEnabled(v);
              },
            ),

            if (wakeWord.enabled) ...[
              const Divider(),
              const SizedBox(height: 8),
              const Text('唤醒词', style: TextStyle(fontWeight: FontWeight.w500)),
              const SizedBox(height: 4),
              Text(
                '说出此词语即可自动开始录音',
                style: TextStyle(fontSize: 12, color: Colors.grey[600]),
              ),
              const SizedBox(height: 8),
              Builder(builder: (context) {
                // 仅首次或唤醒词被外部改变时同步 controller
                if (!_wakeWordControllerInited || _wakeWordController.text.isEmpty) {
                  _wakeWordController.text = wakeWord.wakeWord;
                  _wakeWordControllerInited = true;
                }
                return Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _wakeWordController,
                        decoration: InputDecoration(
                          hintText: '输入唤醒词',
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                          isDense: true,
                        ),
                        onSubmitted: (_) => _saveWakeWord(wakeWord),
                      ),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton(
                      onPressed: () => _saveWakeWord(wakeWord),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                        minimumSize: Size.zero,
                      ),
                      child: const Text('保存'),
                    ),
                  ],
                );
              }),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primaryContainer.withOpacity(0.3),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Icon(Icons.info_outline, size: 16, color: theme.colorScheme.primary),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '提示：唤醒词建议使用2-4个字的简短词语，如"你好助手"、"开始录音"等。在安静环境下效果更佳。',
                        style: TextStyle(fontSize: 11, color: theme.colorScheme.primary),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
