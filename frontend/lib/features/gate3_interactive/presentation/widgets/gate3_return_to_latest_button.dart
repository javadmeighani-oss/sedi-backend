import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Shown when the chat list is scrolled away from the latest messages.
class Gate3ReturnToLatestButton extends StatefulWidget {
  final ScrollController scrollController;
  final VoidCallback onTap;
  final String tooltip;

  const Gate3ReturnToLatestButton({
    super.key,
    required this.scrollController,
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
  void initState() {
    super.initState();
    widget.scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    widget.scrollController.removeListener(_onScroll);
    super.dispose();
  }

  void _onScroll() {
    if (mounted) setState(() {});
  }

  bool get _visible =>
      widget.scrollController.hasClients && widget.scrollController.offset > 72;

  @override
  Widget build(BuildContext context) {
    if (!_visible) return const SizedBox.shrink();

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
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: _pressed ? AppTheme.metalGrey : AppTheme.primaryBlack,
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
