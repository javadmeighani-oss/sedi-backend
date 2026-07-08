import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

class Gate3Composer extends StatefulWidget {
  final ValueChanged<String> onSendText;
  final VoidCallback onStartRecording;
  final VoidCallback onStopRecordingAndSend;
  final bool isRecording;
  final String recordingTime;

  const Gate3Composer({
    super.key,
    required this.onSendText,
    required this.onStartRecording,
    required this.onStopRecordingAndSend,
    required this.isRecording,
    required this.recordingTime,
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

  @override
  Widget build(BuildContext context) {
    final hasText = _controller.text.trim().isNotEmpty;

    return Container(
      margin: const EdgeInsets.fromLTRB(14, 10, 14, 12),
      padding: const EdgeInsets.fromLTRB(12, 12, 10, 12),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.75),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: AppTheme.borderInactive.withOpacity(0.25),
          width: 1,
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 16,
            offset: Offset(0, 6),
          ),
        ],
      ),
      // Keep icon sides physically stable (expand left / mic+send right)
      // even when the Gate 3 page is RTL Persian.
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            // Expand icon (lower-left, ~20% larger than 24≈28.8)
            InkResponse(
              onTap: () {
                if (kDebugMode) debugPrint('[Gate3Composer] expand tapped');
              },
              radius: 26,
              child: const SizedBox(
                width: 48,
                height: 48,
                child: Icon(
                  Icons.open_in_full_rounded,
                  size: 28.8,
                  color: AppTheme.primaryBlack,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: widget.isRecording
                  ? Padding(
                      padding: const EdgeInsets.only(bottom: 8),
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
                    )
                  : ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 140),
                      child: TextField(
                        controller: _controller,
                        focusNode: _focusNode,
                        enabled: !widget.isRecording,
                        minLines: 1,
                        maxLines: null,
                        keyboardType: TextInputType.multiline,
                        textInputAction: TextInputAction.newline,
                        decoration: const InputDecoration(
                          isCollapsed: true,
                          border: InputBorder.none,
                          hintText: 'صحبت با صدی',
                          hintStyle: TextStyle(
                            color: AppTheme.textSecondary,
                            fontSize: 16,
                            height: 1.2,
                          ),
                        ),
                        style: const TextStyle(
                          color: AppTheme.textPrimary,
                          fontSize: 16,
                          height: 1.35,
                        ),
                        textDirection: TextDirection.rtl,
                        textAlign: TextAlign.right,
                        onSubmitted: (_) => _send(),
                      ),
                    ),
            ),
            const SizedBox(width: 10),
            // Bottom-right: mic + send
            Row(
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
            ),
          ],
        ),
      ),
    );
  }
}

