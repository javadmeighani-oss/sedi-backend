import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

class Gate3Composer extends StatefulWidget {
  final ValueChanged<String> onSendText;
  final VoidCallback onStartRecording;
  final VoidCallback onStopRecordingAndSend;
  final bool isRecording;
  final String recordingTime;
  final String placeholder;
  final bool isRtl;

  const Gate3Composer({
    super.key,
    required this.onSendText,
    required this.onStartRecording,
    required this.onStopRecordingAndSend,
    required this.isRecording,
    required this.recordingTime,
    required this.placeholder,
    required this.isRtl,
  });

  @override
  State<Gate3Composer> createState() => _Gate3ComposerState();
}

class _Gate3ComposerState extends State<Gate3Composer> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();

  @override
  void initState() {
    super.initState();
    _controller.addListener(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _send() {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    widget.onSendText(text);
    _controller.clear();
    _focusNode.unfocus();
  }

  void _handleMic() {
    if (widget.isRecording) {
      widget.onStopRecordingAndSend();
    } else {
      widget.onStartRecording();
    }
  }

  Widget _actionIcons(bool hasText) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        InkResponse(
          onTap: _handleMic,
          radius: 24,
          child: SizedBox(
            width: 44,
            height: 44,
            child: Icon(
              Icons.mic_rounded,
              size: 26,
              color: widget.isRecording
                  ? AppTheme.iconInactive
                  : AppTheme.primaryBlack,
            ),
          ),
        ),
        const SizedBox(width: 4),
        InkResponse(
          onTap: hasText ? _send : null,
          radius: 24,
          child: SizedBox(
            width: 48,
            height: 48,
            child: Center(
              child: Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: hasText
                      ? AppTheme.gate2ButtonOlive
                      : AppTheme.iconInactive,
                ),
                child: const Icon(
                  Icons.arrow_upward_rounded,
                  size: 22,
                  color: Colors.white,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final hasText = _controller.text.trim().isNotEmpty;
    final textDirection =
        widget.isRtl ? TextDirection.rtl : TextDirection.ltr;
    final textAlign = widget.isRtl ? TextAlign.right : TextAlign.left;

    return Container(
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.78),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: AppTheme.borderInactive.withOpacity(0.25),
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 16,
            offset: Offset(0, 6),
          ),
        ],
      ),
      child: widget.isRecording
          ? Row(
              children: [
                Expanded(
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 10,
                        height: 10,
                        decoration: const BoxDecoration(
                          shape: BoxShape.circle,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        widget.recordingTime,
                        style: const TextStyle(
                          color: AppTheme.textPrimary,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
                _actionIcons(hasText),
              ],
            )
          : Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: widget.isRtl
                  ? [
                      _actionIcons(hasText),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _buildTextField(
                          textDirection: textDirection,
                          textAlign: textAlign,
                        ),
                      ),
                    ]
                  : [
                      Expanded(
                        child: _buildTextField(
                          textDirection: textDirection,
                          textAlign: textAlign,
                        ),
                      ),
                      const SizedBox(width: 8),
                      _actionIcons(hasText),
                    ],
            ),
    );
  }

  Widget _buildTextField({
    required TextDirection textDirection,
    required TextAlign textAlign,
  }) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 44, maxHeight: 156),
      child: TextField(
        controller: _controller,
        focusNode: _focusNode,
        enabled: !widget.isRecording,
        minLines: 1,
        maxLines: null,
        keyboardType: TextInputType.multiline,
        textInputAction: TextInputAction.newline,
        textDirection: textDirection,
        textAlign: textAlign,
        textAlignVertical: TextAlignVertical.top,
        decoration: InputDecoration(
          isCollapsed: true,
          border: InputBorder.none,
          hintText: widget.placeholder,
          hintStyle: const TextStyle(
            color: AppTheme.textSecondary,
            fontSize: 16,
            height: 1.2,
          ),
          alignLabelWithHint: true,
        ),
        style: const TextStyle(
          color: AppTheme.textPrimary,
          fontSize: 16,
          height: 1.35,
        ),
        onSubmitted: (_) => _send(),
      ),
    );
  }
}
