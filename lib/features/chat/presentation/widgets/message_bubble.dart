import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';

class MessageBubble extends StatefulWidget {
  final String message;
  final bool isSedi;
  final bool isFailed;
  final VoidCallback? onRetry;
  final bool showTyping;

  const MessageBubble({
    super.key,
    required this.message,
    required this.isSedi,
    this.isFailed = false,
    this.onRetry,
    this.showTyping = false,
  });

  @override
  State<MessageBubble> createState() => _MessageBubbleState();
}

class _MessageBubbleState extends State<MessageBubble> {
  bool _expanded = false;

  bool get _canCollapseUserMessage {
    if (widget.isSedi || widget.showTyping) return false;
    return widget.message.split('\n').length > 2 || widget.message.length > 120;
  }

  @override
  Widget build(BuildContext context) {
    final alignment = widget.isSedi
        ? AlignmentDirectional.centerStart
        : AlignmentDirectional.centerEnd;
    final shouldCollapse = _canCollapseUserMessage && !_expanded;

    final text = widget.showTyping
        ? const _TypingDots()
        : Text(
            widget.message,
            maxLines: shouldCollapse ? 2 : null,
            overflow: shouldCollapse ? TextOverflow.ellipsis : null,
            textAlign: TextAlign.start,
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontSize: 15,
              height: 1.45,
            ),
          );

    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        text,
        if (_canCollapseUserMessage) ...[
          const SizedBox(height: 6),
          GestureDetector(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Text(
              _expanded ? 'Read less' : 'Read more',
              style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
        if (widget.isFailed && widget.onRetry != null) ...[
          const SizedBox(height: 6),
          GestureDetector(
            onTap: widget.onRetry,
            child: const Text(
              'Tap to retry',
              style: TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ],
    );

    // Assistant: plain text in chat space — no bubble/card/container.
    if (widget.isSedi) {
      return Align(
        alignment: alignment,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 320),
            child: body,
          ),
        ),
      );
    }

    // User only: visual container/bubble with collapse + retry.
    return Align(
      alignment: alignment,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
        padding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 10,
        ),
        constraints: const BoxConstraints(
          maxWidth: 300,
        ),
        decoration: BoxDecoration(
          color: AppTheme.metalGrey.withOpacity(0.15),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(AppTheme.radiusLarge),
            topRight: Radius.circular(AppTheme.radiusLarge),
            bottomLeft: Radius.circular(AppTheme.radiusLarge),
            bottomRight: Radius.circular(AppTheme.radiusSmall),
          ),
          border: Border.all(
            color: AppTheme.metalGrey.withOpacity(0.35),
            width: 1,
          ),
          boxShadow: AppTheme.softShadow,
        ),
        child: body,
      ),
    );
  }
}

class _TypingDots extends StatelessWidget {
  const _TypingDots();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _dot(),
        const SizedBox(width: 4),
        _dot(),
        const SizedBox(width: 4),
        _dot(),
      ],
    );
  }

  Widget _dot() {
    return Container(
      width: 6,
      height: 6,
      decoration: const BoxDecoration(
        color: AppTheme.iconInactive,
        shape: BoxShape.circle,
      ),
    );
  }
}
