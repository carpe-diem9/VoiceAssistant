import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../models/models.dart';

/// Message bubble widget - displays a single chat message.
/// - user 消息：纯文本展示（包含尖括号/符号也安全）
/// - assistant 消息：Markdown 渲染（支持 Deep Research / GPT / Gemini 返回的
///   标题、列表、引用、分隔线、表格、代码块等结构化内容）
class MessageBubble extends StatelessWidget {
  final Message message;

  const MessageBubble({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    final theme = Theme.of(context);

    final bgColor = isUser
        ? theme.colorScheme.primary
        : theme.colorScheme.surfaceContainerHighest;
    final fgColor = isUser ? Colors.white : theme.colorScheme.onSurface;

    final content =
        message.content.isEmpty && message.isStreaming ? '...' : message.content;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: EdgeInsets.only(
          top: 4,
          bottom: 4,
          left: isUser ? 48 : 0,
          right: isUser ? 0 : 48,
        ),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft:
                isUser ? const Radius.circular(16) : const Radius.circular(4),
            bottomRight:
                isUser ? const Radius.circular(4) : const Radius.circular(16),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Message content
            if (isUser)
              SelectableText(
                content,
                style: TextStyle(color: fgColor, fontSize: 15),
              )
            else
              MarkdownBody(
                data: content,
                selectable: true,
                styleSheet: _buildMarkdownStyle(theme, fgColor),
                softLineBreak: true,
              ),

            // Streaming indicator
            if (message.isStreaming)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: isUser ? Colors.white70 : theme.colorScheme.primary,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// 统一的 Markdown 样式：紧凑、与气泡配色协调
  MarkdownStyleSheet _buildMarkdownStyle(ThemeData theme, Color baseColor) {
    final base = TextStyle(color: baseColor, fontSize: 15, height: 1.45);
    return MarkdownStyleSheet(
      p: base,
      h1: base.copyWith(fontSize: 19, fontWeight: FontWeight.w700, height: 1.35),
      h2: base.copyWith(fontSize: 17.5, fontWeight: FontWeight.w700, height: 1.35),
      h3: base.copyWith(fontSize: 16.5, fontWeight: FontWeight.w600, height: 1.35),
      h4: base.copyWith(fontSize: 15.5, fontWeight: FontWeight.w600),
      strong: base.copyWith(fontWeight: FontWeight.w700),
      em: base.copyWith(fontStyle: FontStyle.italic),
      a: base.copyWith(
        color: theme.colorScheme.primary,
        decoration: TextDecoration.underline,
      ),
      listBullet: base,
      blockquote: base.copyWith(color: baseColor.withOpacity(0.85)),
      blockquoteDecoration: BoxDecoration(
        color: theme.colorScheme.primary.withOpacity(0.06),
        borderRadius: BorderRadius.circular(6),
        border: Border(
          left: BorderSide(
            color: theme.colorScheme.primary.withOpacity(0.6),
            width: 3,
          ),
        ),
      ),
      blockquotePadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      code: base.copyWith(
        fontFamily: 'monospace',
        fontSize: 13.5,
        backgroundColor: theme.colorScheme.surfaceContainerHigh.withOpacity(0.6),
      ),
      codeblockDecoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHigh.withOpacity(0.6),
        borderRadius: BorderRadius.circular(8),
      ),
      codeblockPadding: const EdgeInsets.all(10),
      horizontalRuleDecoration: BoxDecoration(
        border: Border(
          top: BorderSide(
            color: theme.colorScheme.outlineVariant,
            width: 1,
          ),
        ),
      ),
      tableBorder: TableBorder.all(
        color: theme.colorScheme.outlineVariant,
        width: 1,
      ),
      tableHead: base.copyWith(fontWeight: FontWeight.w600),
      tableBody: base,
      tableCellsPadding:
          const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    );
  }
}
