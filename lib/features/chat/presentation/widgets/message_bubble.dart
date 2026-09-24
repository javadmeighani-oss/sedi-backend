import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';

class MessageBubble extends StatefulWidget {
  final String message;
  final bool isSedi;
  final bool isFailed;
  final VoidCallback? onRetry;
  final VoidCallback? onEdit;
  final String? editLabel;
  final bool showTyping;

  const MessageBubble({
    super.key,
    required this.message,
    required this.isSedi,
    this.isFailed = false,
    this.onRetry,
    this.onEdit,
    this.editLabel,
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

    final showEdit = !widget.isSedi &&
        !widget.showTyping &&
        widget.onEdit != null &&
        widget.message.trim().isNotEmpty;

    Widget? editAction;
    if (showEdit) {
      editAction = Tooltip(
        message: widget.editLabel ?? 'Edit',
        child: GestureDetector(
          onTap: widget.onEdit,
          child: SizedBox(
            width: 44,
            height: 44,
            child: Center(
              child: Icon(
                Icons.edit_outlined,
                size: 16,
                color: AppTheme.textSecondary.withOpacity(0.9),
              ),
            ),
          ),
        ),
      );
    }

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
    // Edit icon sits outside/below the decorated bubble.
    return Align(
      alignment: alignment,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 300),
          child: IntrinsicWidth(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
                decoration: BoxDecoration(
                  color: AppTheme.metalGrey.withOpacity(0.15),
                  borderRadius: const BorderRadius.only(
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
              if (editAction != null)
                Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: editAction,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _dot(0),
            const SizedBox(width: 4),
            _dot(1),
            const SizedBox(width: 4),
            _dot(2),
          ],
        );
      },
    );
  }

  Widget _dot(int index) {
    final phase = (_controller.value + (index * 0.2)) % 1.0;
    final pulse = 1 - ((phase - 0.5).abs() * 2);
    final opacity = 0.35 + (0.65 * pulse.clamp(0.0, 1.0));
    return Opacity(
      opacity: opacity,
      child: Container(
        width: 6,
        height: 6,
        decoration: const BoxDecoration(
          color: AppTheme.iconInactive,
          shape: BoxShape.circle,
        ),
      ),
    );
  }
}
