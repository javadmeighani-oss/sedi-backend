import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import 'gate3_attachment_menu.dart';
import 'gate3_composer_action_button.dart';

class Gate3Composer extends StatefulWidget {
  final ValueChanged<String> onSendText;
  final VoidCallback onStartRecording;
  final VoidCallback onStopRecordingAndSend;
  final bool isRecording;
  final String recordingTime;
  final String placeholder;
  final String lang;
  final bool isRtl;
  final ValueChanged<bool>? onListeningChanged;

  /// Prior Gate 3 composer body font size before the 20% reduction.
  static const double baseFontSize = 16;

  /// Gate 3 composer body font size (exactly 80% of [baseFontSize]).
  static const double fontSize = baseFontSize * 0.8;

  const Gate3Composer({
    super.key,
    required this.onSendText,
    required this.onStartRecording,
    required this.onStopRecordingAndSend,
    required this.isRecording,
    required this.recordingTime,
    required this.placeholder,
    required this.lang,
    required this.isRtl,
    this.onListeningChanged,
  });

  @override
  State<Gate3Composer> createState() => _Gate3ComposerState();
}

class _Gate3ComposerState extends State<Gate3Composer> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();

  static const double _maxTextHeight = 168;

  static const TextStyle _composerTextStyle = TextStyle(
    color: AppTheme.textPrimary,
    fontSize: Gate3Composer.fontSize,
    height: 1.35,
  );

  static const TextStyle _composerHintStyle = TextStyle(
    color: AppTheme.textSecondary,
    fontSize: Gate3Composer.fontSize,
    height: 1.35,
  );

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onTextChanged);
    _focusNode.addListener(_notifyListening);
    _onTextChanged();
  }

  @override
  void didUpdateWidget(covariant Gate3Composer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.isRecording != widget.isRecording) {
      _notifyListening();
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_onTextChanged);
    _focusNode.removeListener(_notifyListening);
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _onTextChanged() {
    if (mounted) setState(() {});
    _notifyListening();
  }

  void _notifyListening() {
    final listening = widget.isRecording ||
        _focusNode.hasFocus ||
        _controller.text.trim().isNotEmpty;
    widget.onListeningChanged?.call(listening);
  }

  void _send() {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    widget.onSendText(text);
    _controller.clear();
    _focusNode.unfocus();
    _notifyListening();
  }

  void _handleMic() {
    if (widget.isRecording) {
      widget.onStopRecordingAndSend();
    } else {
      widget.onStartRecording();
    }
  }

  void _openAttachmentMenu() {
    _focusNode.unfocus();
    Gate3AttachmentMenu.show(context, widget.lang);
  }

  Widget _buildTextField({
    required TextDirection textDirection,
    required TextAlign textAlign,
  }) {
    return ConstrainedBox(
      constraints: const BoxConstraints(
        minHeight: 28,
        maxHeight: _maxTextHeight,
      ),
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
        scrollPhysics: const BouncingScrollPhysics(),
        decoration: InputDecoration(
          isCollapsed: true,
          contentPadding: const EdgeInsets.symmetric(vertical: 2),
          border: InputBorder.none,
          hintText: widget.placeholder,
          hintStyle: _composerHintStyle,
          alignLabelWithHint: true,
        ),
        style: _composerTextStyle,
        onSubmitted: (_) => _send(),
      ),
    );
  }

  Widget _buildRecordingBody() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
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
    );
  }

  Widget _buildToolbar(bool hasText) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 2, 8, 8),
        child: Row(
          children: [
            Gate3ComposerActionButton(
              icon: Icons.add_rounded,
              onTap: widget.isRecording ? null : _openAttachmentMenu,
            ),
            const Spacer(),
            if (widget.isRecording)
              Gate3ComposerActionButton(
                icon: Icons.stop_rounded,
                size: 40,
                iconSize: 22,
                backgroundColor: AppTheme.gate2ButtonOlive,
                iconColor: Colors.white,
                onTap: _handleMic,
              )
            else if (hasText)
              Gate3ComposerActionButton(
                icon: Icons.arrow_upward_rounded,
                size: 40,
                iconSize: 22,
                backgroundColor: AppTheme.gate2ButtonOlive,
                iconColor: Colors.white,
                onTap: _send,
              )
            else
              Gate3ComposerActionButton(
                icon: Icons.mic_rounded,
                size: 40,
                iconSize: 24,
                onTap: _handleMic,
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hasText = _controller.text.trim().isNotEmpty;
    final textDirection =
        widget.isRtl ? TextDirection.rtl : TextDirection.ltr;
    final textAlign = widget.isRtl ? TextAlign.right : TextAlign.left;

    return Container(
      margin: const EdgeInsets.fromLTRB(10, 6, 10, 10),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.88),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: AppTheme.borderInactive.withOpacity(0.18),
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x12000000),
            blurRadius: 18,
            offset: Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 0),
            child: widget.isRecording
                ? _buildRecordingBody()
                : _buildTextField(
                    textDirection: textDirection,
                    textAlign: textAlign,
                  ),
          ),
          _buildToolbar(hasText),
        ],
      ),
    );
  }
}
