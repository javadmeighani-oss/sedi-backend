import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Physical bottom-right return-to-latest control inside the reserved lane.
class Gate3ReturnToLatestButton extends StatefulWidget {
  final VoidCallback onTap;
  final String tooltip;

  static const double size = 40;

  const Gate3ReturnToLatestButton({
    super.key,
    required this.onTap,
    required this.tooltip,
  });

  @override
  State<Gate3ReturnToLatestButton> createState() =>
      _Gate3ReturnToLatestButtonState();
}

class _Gate3ReturnToLatestButtonState extends State<Gate3ReturnToLatestButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: widget.tooltip,
      child: GestureDetector(
        onTapDown: (_) => setState(() => _pressed = true),
        onTapUp: (_) {
          setState(() => _pressed = false);
          widget.onTap();
        },
        onTapCancel: () => setState(() => _pressed = false),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          width: Gate3ReturnToLatestButton.size,
          height: Gate3ReturnToLatestButton.size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: _pressed ? AppTheme.metalGrey : AppTheme.gate2ButtonOlive,
            boxShadow: const [
              BoxShadow(
                color: Color(0x22000000),
                blurRadius: 10,
                offset: Offset(0, 4),
              ),
            ],
          ),
          child: const Icon(
            Icons.keyboard_arrow_down_rounded,
            color: AppTheme.backgroundWhite,
            size: 24,
          ),
        ),
      ),
    );
  }
}
