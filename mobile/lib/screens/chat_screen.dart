import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../providers/chat_provider.dart';
import '../models/models.dart';
import '../widgets/message_bubble.dart';
import '../widgets/voice_button.dart';
import 'settings_screen.dart';
import 'login_screen.dart';

/// Chat main screen - text input + voice recording + message list
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();
  bool _hasText = false;

  @override
  void initState() {
    super.initState();
    _textController.addListener(() {
      final hasText = _textController.text.trim().isNotEmpty;
      if (hasText != _hasText) {
        setState(() => _hasText = hasText);
      }
    });
    // 加载侧边栏会话列表
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final chat = Provider.of<ChatProvider>(context, listen: false);
      chat.loadSessions();
      // 设置唤醒词检测回调：自动开始录音
      chat.wakeWord.onWakeWordDetected = () {
        if (!chat.isRecording && !chat.isSending) {
          _toggleRecording();
        }
      };
    });
  }

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _sendTextMessage() {
    final text = _textController.text.trim();
    if (text.isEmpty) return;
    _textController.clear();
    final chat = Provider.of<ChatProvider>(context, listen: false);
    chat.sendTextMessage(text);
    _scrollToBottom();
  }

  void _startNewChat() {
    final chat = Provider.of<ChatProvider>(context, listen: false);
    chat.clearMessages();
  }

  void _toggleRecording() {
    final chat = Provider.of<ChatProvider>(context, listen: false);
    if (chat.isRecording) {
      chat.stopRecordingAndSend();
      _scrollToBottom();
    } else {
      chat.startRecording();
    }
  }

  void _cancelRecording() {
    final chat = Provider.of<ChatProvider>(context, listen: false);
    chat.cancelRecording();
  }

  void _openSession(Session session) {
    final chat = Provider.of<ChatProvider>(context, listen: false);
    chat.loadSessionMessages(session.id);
    Navigator.of(context).pop(); // 关闭侧边栏
    _scrollToBottom();
  }

  @override
  Widget build(BuildContext context) {
    final auth = Provider.of<AuthProvider>(context);
    final chat = Provider.of<ChatProvider>(context);
    final theme = Theme.of(context);

    // Auto-scroll when messages change
    if (chat.messages.isNotEmpty) {
      _scrollToBottom();
    }

    return Stack(
      children: [
        Scaffold(
          appBar: AppBar(
            title: const Text('AI 语音助理'),
            leading: Builder(
              builder: (context) => IconButton(
                icon: const Icon(Icons.menu),
                onPressed: () {
                  // 打开侧边栏前刷新会话列表
                  chat.loadSessions();
                  Scaffold.of(context).openDrawer();
                },
              ),
            ),
            actions: [
              IconButton(
                icon: const Icon(Icons.add_comment_outlined),
                onPressed: _startNewChat,
                tooltip: '新建对话',
              ),
              IconButton(
                icon: const Icon(Icons.settings_outlined),
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const SettingsScreen()),
                  );
                },
              ),
            ],
          ),

          // Drawer - 直接显示历史会话列表
          drawer: _buildDrawer(context, auth, chat, theme),

          body: Column(
            children: [
              // Message list
              Expanded(
                child: chat.messages.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.chat_bubble_outline, size: 64, color: Colors.grey[300]),
                            const SizedBox(height: 16),
                            Text(
                              '开始对话',
                              style: TextStyle(color: Colors.grey[500], fontSize: 16),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '输入文字或点击麦克风按钮语音对话',
                              style: TextStyle(color: Colors.grey[400], fontSize: 13),
                            ),
                            if (chat.wakeWord.enabled) ...[
                              const SizedBox(height: 12),
                              Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(
                                    chat.wakeWord.isActive ? Icons.hearing : Icons.hearing_disabled,
                                    size: 16,
                                    color: chat.wakeWord.isActive ? Colors.green : Colors.grey[400],
                                  ),
                                  const SizedBox(width: 6),
                                  Text(
                                    chat.wakeWord.isActive
                                        ? '语音唤醒已开启，说"${chat.wakeWord.wakeWord}"开始对话'
                                        : '语音唤醒已暂停',
                                    style: TextStyle(
                                      color: chat.wakeWord.isActive ? Colors.green : Colors.grey[400],
                                      fontSize: 12,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      )
                    : ListView.builder(
                        controller: _scrollController,
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        itemCount: chat.messages.length,
                        itemBuilder: (context, index) {
                          return MessageBubble(message: chat.messages[index]);
                        },
                      ),
              ),

              // Input area
              _buildInputArea(context, chat, theme),
            ],
          ),
        ),

        // 录音波形叠加层
        if (chat.isRecording)
          Positioned.fill(
            child: VoiceRecordingOverlay(
              onStop: _toggleRecording,
              onCancel: _cancelRecording,
            ),
          ),
      ],
    );
  }

  /// 构建侧边栏 - 直接显示历史会话列表
  Widget _buildDrawer(BuildContext context, AuthProvider auth, ChatProvider chat, ThemeData theme) {
    return Drawer(
      child: Column(
        children: [
          // 顶部：新建对话按钮
          Container(
            padding: EdgeInsets.only(
              top: MediaQuery.of(context).padding.top + 16,
              left: 16,
              right: 16,
              bottom: 12,
            ),
            decoration: BoxDecoration(
              color: theme.colorScheme.primaryContainer.withOpacity(0.3),
            ),
            child: Row(
              children: [
                Icon(Icons.chat, color: theme.colorScheme.primary),
                const SizedBox(width: 12),
                Text('对话记录', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                const Spacer(),
                // 新建对话按钮
                FilledButton.icon(
                  onPressed: () {
                    _startNewChat();
                    Navigator.of(context).pop();
                  },
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('新对话'),
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    textStyle: const TextStyle(fontSize: 13),
                  ),
                ),
              ],
            ),
          ),

          const Divider(height: 1),

          // 会话列表
          Expanded(
            child: chat.isLoadingSessions && chat.sessions.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : chat.sessions.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.chat_bubble_outline, size: 48, color: Colors.grey[300]),
                            const SizedBox(height: 12),
                            Text('暂无对话记录', style: TextStyle(color: Colors.grey[500], fontSize: 14)),
                          ],
                        ),
                      )
                    : RefreshIndicator(
                        onRefresh: () => chat.loadSessions(),
                        child: ListView.builder(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          itemCount: chat.sessions.length,
                          itemBuilder: (context, index) {
                            final session = chat.sessions[index];
                            final isActive = chat.currentSessionId == session.id;
                            return _buildSessionTile(context, session, isActive, chat, theme);
                          },
                        ),
                      ),
          ),

          const Divider(height: 1),

          // 底部：用户信息 + 退出登录
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 18,
                  backgroundColor: theme.colorScheme.primaryContainer,
                  child: Text(
                    auth.user?.username.substring(0, 1).toUpperCase() ?? 'U',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    auth.user?.username ?? '用户',
                    style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w500),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                TextButton.icon(
                  onPressed: () async {
                    await auth.logout();
                    if (mounted) {
                      Navigator.of(context).pushAndRemoveUntil(
                        MaterialPageRoute(builder: (_) => const LoginScreen()),
                        (route) => false,
                      );
                    }
                  },
                  icon: const Icon(Icons.logout, size: 18, color: Colors.red),
                  label: const Text('退出', style: TextStyle(color: Colors.red, fontSize: 13)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// 构建单个会话条目（支持左滑删除）
  Widget _buildSessionTile(
    BuildContext context, Session session, bool isActive, ChatProvider chat, ThemeData theme,
  ) {
    return Dismissible(
      key: Key('session_${session.id}'),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        color: Colors.red,
        child: const Icon(Icons.delete, color: Colors.white),
      ),
      confirmDismiss: (direction) async {
        return await showDialog(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('删除对话'),
            content: const Text('确定要删除这个对话吗？'),
            actions: [
              TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('取消')),
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(true),
                child: const Text('删除', style: TextStyle(color: Colors.red)),
              ),
            ],
          ),
        );
      },
      onDismissed: (_) => chat.deleteSession(session.id),
      child: ListTile(
        dense: true,
        selected: isActive,
        selectedTileColor: theme.colorScheme.primaryContainer.withOpacity(0.3),
        leading: Icon(
          Icons.chat_bubble_outline,
          size: 20,
          color: isActive ? theme.colorScheme.primary : Colors.grey[600],
        ),
        title: Text(
          session.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: 14,
            fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
        subtitle: Text(
          _formatTime(session.updatedAt),
          style: TextStyle(color: Colors.grey[500], fontSize: 11),
        ),
        trailing: IconButton(
          icon: Icon(Icons.delete_outline, size: 18, color: Colors.grey[400]),
          onPressed: () async {
            final confirm = await showDialog<bool>(
              context: context,
              builder: (ctx) => AlertDialog(
                title: const Text('删除对话'),
                content: const Text('确定要删除这个对话吗？'),
                actions: [
                  TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('取消')),
                  TextButton(
                    onPressed: () => Navigator.of(ctx).pop(true),
                    child: const Text('删除', style: TextStyle(color: Colors.red)),
                  ),
                ],
              ),
            );
            if (confirm == true) {
              chat.deleteSession(session.id);
            }
          },
        ),
        onTap: () => _openSession(session),
      ),
    );
  }

  String _formatTime(String timeStr) {
    if (timeStr.length > 16) {
      return timeStr.substring(0, 16).replaceFirst('T', ' ');
    }
    return timeStr;
  }

  /// 显示语音输出设置底部弹窗
  void _showTtsSettingsSheet(BuildContext context, ChatProvider chat) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setSheetState) {
            // 监听 chat 变化来更新弹窗内的选中状态
            final ttsOn = chat.ttsEnabled;
            return SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // 标题
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      child: Row(
                        children: [
                          Icon(Icons.record_voice_over, color: Theme.of(context).colorScheme.primary),
                          const SizedBox(width: 8),
                          Text('回答方式', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                        ],
                      ),
                    ),
                    const Divider(),
                    // 文本回答
                    RadioListTile<bool>(
                      value: false,
                      groupValue: ttsOn,
                      title: const Text('文本回答'),
                      subtitle: const Text('仅显示文字，不播放语音', style: TextStyle(fontSize: 12)),
                      secondary: const Icon(Icons.text_fields),
                      onChanged: (v) {
                        chat.setTtsEnabled(false);
                        setSheetState(() {});
                        Navigator.of(ctx).pop();
                      },
                    ),
                    // 语音回答
                    RadioListTile<bool>(
                      value: true,
                      groupValue: ttsOn,
                      title: const Text('语音回答'),
                      subtitle: const Text('自动语音合成并播放', style: TextStyle(fontSize: 12)),
                      secondary: const Icon(Icons.record_voice_over),
                      onChanged: (v) {
                        chat.setTtsEnabled(true);
                        setSheetState(() {});
                        Navigator.of(ctx).pop();
                      },
                    ),
                    const SizedBox(height: 8),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  /// 构建输入区域
  Widget _buildInputArea(BuildContext context, ChatProvider chat, ThemeData theme) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        child: Row(
          children: [
            // 语音输出设置按钮
            IconButton(
              icon: Icon(
                chat.ttsEnabled ? Icons.record_voice_over : Icons.text_fields,
                size: 22,
              ),
              color: chat.ttsEnabled ? theme.colorScheme.primary : Colors.grey,
              tooltip: chat.ttsEnabled ? '语音回答' : '文本回答',
              onPressed: () => _showTtsSettingsSheet(context, chat),
            ),

            // 文本输入框
            Expanded(
              child: TextField(
                controller: _textController,
                decoration: InputDecoration(
                  hintText: '输入消息...',
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none,
                  ),
                  filled: true,
                  fillColor: theme.colorScheme.surfaceContainerHighest.withOpacity(0.5),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _sendTextMessage(),
                maxLines: null,
              ),
            ),
            const SizedBox(width: 4),

            // 发送按钮（始终显示，无 spinner）
            IconButton(
              onPressed: (!_hasText || chat.isSending) ? null : _sendTextMessage,
              icon: const Icon(Icons.send),
              color: theme.colorScheme.primary,
            ),

            // 语音按钮（等待回复时灰色禁用，无 spinner）
            VoiceButton(
              isRecording: chat.isRecording,
              isSending: chat.isSending,
              onToggle: _toggleRecording,
            ),
          ],
        ),
      ),
    );
  }
}
