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

  // 模型选项
  List<String> _availableModels = ['qwen3.5-plus', 'deepseek_v4_flash'];
  String _currentModel = 'qwen3.5-plus';
  bool _isUpdatingModel = false;

  List<String> _availableASRModels = ['qwen3-asr-flash', 'SenseVoiceSmall', 'whisper-large-v3'];
  String _currentASRModel = 'qwen3-asr-flash';
  bool _isUpdatingASR = false;

  List<String> _availableTTSModels = ['qwen3-tts-instruct-flash', 'CosyVoice2', 'gemini-2.5-flash-preview-tts'];
  String _currentTTSModel = 'qwen3-tts-instruct-flash';
  bool _isUpdatingTTS = false;

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

  /// 音色名→描述（只保留一男一女）
  static const Map<String, String> _kVoiceLabels = {
    'Cherry': '温柔女声',
    'Ethan': '沉稳男声',
  };
  String _voiceLabel(String v) => _kVoiceLabels[v] ?? v;

  Future<void> _loadSettings() async {
    try {
      final api = Provider.of<ApiService>(context, listen: false);
      _ttsSettings = await api.getTTSSettings();
      try {
        final m = await api.getModels();
        final List<dynamic> av = (m['available_models'] ?? []) as List<dynamic>;
        if (av.isNotEmpty) {
          _availableModels = av.map((e) => e.toString()).toList();
        }
        final cur = m['current_model'];
        if (cur is String && cur.isNotEmpty) _currentModel = cur;
        // 确保 _currentModel 在列表中
        if (!_availableModels.contains(_currentModel)) {
          _availableModels = [_currentModel, ..._availableModels];
        }
        // 解析新版分类返回 llm/asr/tts
        final llm = m['llm'];
        if (llm is Map) {
          final av2 = (llm['available'] ?? []) as List<dynamic>;
          if (av2.isNotEmpty) _availableModels = av2.map((e) => e.toString()).toList();
          final cur2 = llm['current'];
          if (cur2 is String && cur2.isNotEmpty) _currentModel = cur2;
          if (!_availableModels.contains(_currentModel)) {
            _availableModels = [_currentModel, ..._availableModels];
          }
        }
        final asr = m['asr'];
        if (asr is Map) {
          final av3 = (asr['available'] ?? []) as List<dynamic>;
          if (av3.isNotEmpty) _availableASRModels = av3.map((e) => e.toString()).toList();
          final cur3 = asr['current'];
          if (cur3 is String && cur3.isNotEmpty) _currentASRModel = cur3;
          if (!_availableASRModels.contains(_currentASRModel)) {
            _availableASRModels = [_currentASRModel, ..._availableASRModels];
          }
        }
        final tts = m['tts'];
        if (tts is Map) {
          final av4 = (tts['available'] ?? []) as List<dynamic>;
          if (av4.isNotEmpty) _availableTTSModels = av4.map((e) => e.toString()).toList();
          final cur4 = tts['current'];
          if (cur4 is String && cur4.isNotEmpty) _currentTTSModel = cur4;
          if (!_availableTTSModels.contains(_currentTTSModel)) {
            _availableTTSModels = [_currentTTSModel, ..._availableTTSModels];
          }
        }
      } catch (e) {
        // 忽略模型加载失败，保留默认倒备项
        debugPrint('load models failed: $e');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('加载设置失败: $e')),
        );
      }
    }
    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _changeModel(String model) async {
    if (model == _currentModel || _isUpdatingModel) return;
    setState(() => _isUpdatingModel = true);
    try {
      final api = Provider.of<ApiService>(context, listen: false);
      await api.updateModel(model);
      if (mounted) {
        setState(() => _currentModel = model);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('语言模型已切换为 $model')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('切换模型失败: $e')),
        );
      }
    }
    if (mounted) setState(() => _isUpdatingModel = false);
  }

  Future<void> _changeASRModel(String model) async {
    if (model == _currentASRModel || _isUpdatingASR) return;
    setState(() => _isUpdatingASR = true);
    try {
      final api = Provider.of<ApiService>(context, listen: false);
      await api.updateASRModel(model);
      if (mounted) {
        setState(() => _currentASRModel = model);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('ASR 模型已切换为 $model')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('切换 ASR 模型失败: $e')),
        );
      }
    }
    if (mounted) setState(() => _isUpdatingASR = false);
  }

  Future<void> _changeTTSModel(String model) async {
    if (model == _currentTTSModel || _isUpdatingTTS) return;
    setState(() => _isUpdatingTTS = true);
    try {
      final api = Provider.of<ApiService>(context, listen: false);
      await api.updateTTSModel(model);
      if (mounted) {
        setState(() => _currentTTSModel = model);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('TTS 模型已切换为 $model')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('切换 TTS 模型失败: $e')),
        );
      }
    }
    if (mounted) setState(() => _isUpdatingTTS = false);
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
                                      ? const ['Cherry', 'Ethan']
                                      : _ttsSettings!.availableVoices)
                                  .map((voice) => ChoiceChip(
                                        label: Text(_voiceLabel(voice)),
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
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        child: Row(
                          children: [
                            const Icon(Icons.smart_toy_outlined),
                            const SizedBox(width: 16),
                            const Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('语言模型', style: TextStyle(fontWeight: FontWeight.w500)),
                                  SizedBox(height: 2),
                                  Text('切换后会在后端持久化并立即生效',
                                      style: TextStyle(fontSize: 11, color: Colors.grey)),
                                ],
                              ),
                            ),
                            if (_isUpdatingModel)
                              const SizedBox(
                                width: 18, height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            else
                              DropdownButton<String>(
                                value: _availableModels.contains(_currentModel)
                                    ? _currentModel
                                    : _availableModels.first,
                                underline: const SizedBox.shrink(),
                                alignment: AlignmentDirectional.centerEnd,
                                isDense: true,
                                items: _availableModels
                                    .map((m) => DropdownMenuItem<String>(
                                          value: m,
                                          alignment: AlignmentDirectional.centerEnd,
                                          child: Text(m,
                                              textAlign: TextAlign.right,
                                              style: const TextStyle(fontSize: 13)),
                                        ))
                                    .toList(),
                                onChanged: (v) {
                                  if (v != null) _changeModel(v);
                                },
                              ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        child: Row(
                          children: [
                            const Icon(Icons.mic_none),
                            const SizedBox(width: 16),
                            const Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('ASR 语音识别', style: TextStyle(fontWeight: FontWeight.w500)),
                                  SizedBox(height: 2),
                                  Text('whisper / SenseVoice 走 gpt.ge 网关',
                                      style: TextStyle(fontSize: 11, color: Colors.grey)),
                                ],
                              ),
                            ),
                            if (_isUpdatingASR)
                              const SizedBox(
                                width: 18, height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            else
                              DropdownButton<String>(
                                value: _availableASRModels.contains(_currentASRModel)
                                    ? _currentASRModel
                                    : _availableASRModels.first,
                                underline: const SizedBox.shrink(),
                                alignment: AlignmentDirectional.centerEnd,
                                isDense: true,
                                items: _availableASRModels
                                    .map((m) => DropdownMenuItem<String>(
                                          value: m,
                                          alignment: AlignmentDirectional.centerEnd,
                                          child: Text(m,
                                              textAlign: TextAlign.right,
                                              style: const TextStyle(fontSize: 13)),
                                        ))
                                    .toList(),
                                onChanged: (v) {
                                  if (v != null) _changeASRModel(v);
                                },
                              ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        child: Row(
                          children: [
                            const Icon(Icons.record_voice_over_outlined),
                            const SizedBox(width: 16),
                            const Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('TTS 语音合成', style: TextStyle(fontWeight: FontWeight.w500)),
                                  SizedBox(height: 2),
                                  Text('CosyVoice / Gemini-TTS 走 gpt.ge 网关',
                                      style: TextStyle(fontSize: 11, color: Colors.grey)),
                                ],
                              ),
                            ),
                            if (_isUpdatingTTS)
                              const SizedBox(
                                width: 18, height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            else
                              DropdownButton<String>(
                                value: _availableTTSModels.contains(_currentTTSModel)
                                    ? _currentTTSModel
                                    : _availableTTSModels.first,
                                underline: const SizedBox.shrink(),
                                alignment: AlignmentDirectional.centerEnd,
                                isDense: true,
                                items: _availableTTSModels
                                    .map((m) => DropdownMenuItem<String>(
                                          value: m,
                                          alignment: AlignmentDirectional.centerEnd,
                                          child: Text(m,
                                              textAlign: TextAlign.right,
                                              style: const TextStyle(fontSize: 13)),
                                        ))
                                    .toList(),
                                onChanged: (v) {
                                  if (v != null) _changeTTSModel(v);
                                },
                              ),
                          ],
                        ),
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
