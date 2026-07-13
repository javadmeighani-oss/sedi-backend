import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Layout-aware inline expand/collapse for long chat message bodies.
class ExpandableMessageContent extends StatefulWidget {
  /// Stable per-message identity (e.g. [ChatMessage.localId]).
  final String messageKey;
  final String text;
  final TextStyle style;
  final String expandLabel;
  final String collapseLabel;
  final Color fadeBaseColor;
  final int collapsedMaxLines;
  final double maxContentWidth;

  static const int defaultCollapsedMaxLines = 2;

  const ExpandableMessageContent({
    super.key,
    required this.messageKey,
    required this.text,
    required this.style,
    required this.expandLabel,
    required this.collapseLabel,
    required this.fadeBaseColor,
    this.collapsedMaxLines = defaultCollapsedMaxLines,
    required this.maxContentWidth,
  });

  @override
  State<ExpandableMessageContent> createState() =>
      _ExpandableMessageContentState();
}

class _ExpandableMessageContentState extends State<ExpandableMessageContent> {
  bool _expanded = false;
  bool _hasOverflow = false;
  double? _measuredWidth;

  @override
  void initState() {
    super.initState();
    _scheduleMeasure();
  }

  @override
  void didUpdateWidget(covariant ExpandableMessageContent oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.messageKey != widget.messageKey ||
        oldWidget.text != widget.text ||
        oldWidget.maxContentWidth != widget.maxContentWidth ||
        oldWidget.collapsedMaxLines != widget.collapsedMaxLines) {
      _expanded = false;
      _hasOverflow = false;
      _scheduleMeasure();
    }
  }

  void _scheduleMeasure() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _measureOverflow();
    });
  }

  void _measureOverflow() {
    final maxWidth = _measuredWidth ?? widget.maxContentWidth;
    if (maxWidth <= 0) return;

    final textScaler = MediaQuery.textScalerOf(context);
    final textDirection = Directionality.of(context);
    final painter = TextPainter(
      text: TextSpan(text: widget.text, style: widget.style),
      textDirection: textDirection,
      textScaler: textScaler,
      maxLines: widget.collapsedMaxLines,
    )..layout(maxWidth: maxWidth);

    final nextOverflow = painter.didExceedMaxLines;
    if (nextOverflow != _hasOverflow) {
      setState(() => _hasOverflow = nextOverflow);
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : widget.maxContentWidth;
        if (_measuredWidth != width) {
          _measuredWidth = width;
          _scheduleMeasure();
        }

        final showToggle = _hasOverflow;

        return AnimatedSize(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeInOut,
          alignment: Alignment.topCenter,
          clipBehavior: Clip.none,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                widget.text,
                textAlign: TextAlign.start,
                style: widget.style,
                maxLines: _expanded ? null : widget.collapsedMaxLines,
                overflow: _expanded
                    ? TextOverflow.visible
                    : TextOverflow.ellipsis,
              ),
              if (showToggle) ...[
                const SizedBox(height: 4),
                Semantics(
                  button: true,
                  label: _expanded ? widget.collapseLabel : widget.expandLabel,
                  child: TextButton(
                    style: TextButton.styleFrom(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(44, 32),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      foregroundColor: AppTheme.gate2ButtonOlive,
                    ),
                    onPressed: () => setState(() => _expanded = !_expanded),
                    child: Text(
                      _expanded ? widget.collapseLabel : widget.expandLabel,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}
