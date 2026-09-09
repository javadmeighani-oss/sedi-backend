import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_theme.dart';

/// Pure helpers for a single-source OTP code field.
class OtpInputHelper {
  OtpInputHelper._();

  static const int codeLength = 6;

  static String sanitize(String raw) {
    final digits = raw.replaceAll(RegExp(r'\D'), '');
    if (digits.length <= codeLength) return digits;
    return digits.substring(0, codeLength);
  }

  static bool isComplete(String code) => sanitize(code).length == codeLength;

  static String digitAt(String code, int index) {
    final sanitized = sanitize(code);
    if (index < 0 || index >= sanitized.length) return '';
    return sanitized[index];
  }
}

/// Autofill-friendly OTP entry with a six-box visual layout.
///
/// Uses one [TextEditingController] as the source of truth so OS one-time-code
/// autofill, paste, and manual typing all populate every box consistently.
class Gate2OtpInput extends StatefulWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final bool enabled;
  final ValueChanged<String>? onChanged;

  const Gate2OtpInput({
    super.key,
    required this.controller,
    required this.focusNode,
    this.enabled = true,
    this.onChanged,
  });

  @override
  State<Gate2OtpInput> createState() => _Gate2OtpInputState();
}

class _Gate2OtpInputState extends State<Gate2OtpInput> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_handleControllerChanged);
  }

  @override
  void didUpdateWidget(covariant Gate2OtpInput oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller.removeListener(_handleControllerChanged);
      widget.controller.addListener(_handleControllerChanged);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_handleControllerChanged);
    super.dispose();
  }

  void _handleControllerChanged() {
    if (mounted) setState(() {});
    widget.onChanged?.call(widget.controller.text);
  }

  void _applyInput(String raw) {
    final sanitized = OtpInputHelper.sanitize(raw);
    if (sanitized == widget.controller.text) return;
    widget.controller.value = TextEditingValue(
      text: sanitized,
      selection: TextSelection.collapsed(offset: sanitized.length),
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final maxWidth = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : MediaQuery.sizeOf(context).width;
        final layout = _OtpBoxLayout.compute(maxWidth);
        final code = OtpInputHelper.sanitize(widget.controller.text);

        return AutofillGroup(
          child: Directionality(
            textDirection: TextDirection.ltr,
            child: SizedBox(
              width: maxWidth,
              height: layout.boxSize + 8,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  IgnorePointer(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      mainAxisSize: MainAxisSize.min,
                      children: List.generate(
                        OtpInputHelper.codeLength,
                        (index) => _OtpDigitBox(
                          digit: OtpInputHelper.digitAt(code, index),
                          size: layout.boxSize,
                          gap: layout.gap,
                          isLast: index == OtpInputHelper.codeLength - 1,
                          active: widget.enabled &&
                              widget.focusNode.hasFocus &&
                              (code.length == index ||
                                  (code.length == OtpInputHelper.codeLength &&
                                      index == OtpInputHelper.codeLength - 1)),
                        ),
                      ),
                    ),
                  ),
                  Positioned.fill(
                    child: TextField(
                      controller: widget.controller,
                      focusNode: widget.focusNode,
                      enabled: widget.enabled,
                      keyboardType: TextInputType.number,
                      textInputAction: TextInputAction.done,
                      autofillHints: const [AutofillHints.oneTimeCode],
                      enableSuggestions: false,
                      autocorrect: false,
                      maxLength: OtpInputHelper.codeLength,
                      showCursor: true,
                      cursorColor: AppTheme.gate2ButtonOlive,
                      style: const TextStyle(
                        color: Colors.transparent,
                        fontSize: 1,
                        height: 1,
                      ),
                      strutStyle: const StrutStyle(height: 1, fontSize: 1),
                      inputFormatters: [
                        FilteringTextInputFormatter.digitsOnly,
                        LengthLimitingTextInputFormatter(OtpInputHelper.codeLength),
                      ],
                      decoration: const InputDecoration(
                        counterText: '',
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        contentPadding: EdgeInsets.zero,
                        isDense: true,
                      ),
                      onChanged: _applyInput,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _OtpBoxLayout {
  final double boxSize;
  final double gap;

  const _OtpBoxLayout({required this.boxSize, required this.gap});

  static _OtpBoxLayout compute(double maxWidth) {
    const count = OtpInputHelper.codeLength;
    const minBox = 32.0;
    const maxBox = 46.0;
    const minGap = 4.0;
    const maxGap = 8.0;

    var gap = maxGap;
    var boxSize = ((maxWidth - gap * (count - 1)) / count)
        .clamp(minBox, maxBox)
        .toDouble();
    var total = boxSize * count + gap * (count - 1);

    while (total > maxWidth && gap > minGap) {
      gap -= 1;
      boxSize = ((maxWidth - gap * (count - 1)) / count)
          .clamp(minBox, maxBox)
          .toDouble();
      total = boxSize * count + gap * (count - 1);
    }

    while (total > maxWidth && boxSize > minBox) {
      boxSize -= 1;
      total = boxSize * count + gap * (count - 1);
    }

    return _OtpBoxLayout(boxSize: boxSize, gap: gap);
  }
}

class _OtpDigitBox extends StatelessWidget {
  final String digit;
  final double size;
  final double gap;
  final bool isLast;
  final bool active;

  const _OtpDigitBox({
    required this.digit,
    required this.size,
    required this.gap,
    required this.isLast,
    required this.active,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size + 4,
      margin: EdgeInsets.only(right: isLast ? 0 : gap),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppTheme.gate2InputFill,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: active ? AppTheme.gate2ButtonOlive : AppTheme.gate2BorderSubtle,
          width: active ? 1.2 : 0.8,
        ),
      ),
      child: Text(
        digit,
        style: TextStyle(
          color: AppTheme.gate2TextPrimary,
          fontSize: (size * 0.42).clamp(14, 20),
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
