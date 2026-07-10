import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Subtle right-edge scroll affordance for Gate 3 chat history.
///
/// One-day visibility filtering is planned for a later pass; this control only
/// helps the user scroll through the currently loaded transcript.
class Gate3ScrollDayControl extends StatelessWidget {
  final ScrollController scrollController;

  const Gate3ScrollDayControl({
    super.key,
    required this.scrollController,
  });

  void _nudgeUp() {
    if (!scrollController.hasClients) return;
    final target = (scrollController.offset + 120).clamp(
      0.0,
      scrollController.position.maxScrollExtent,
    );
    scrollController.animateTo(
      target,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
    );
  }

  void _nudgeDown() {
    if (!scrollController.hasClients) return;
    final target = (scrollController.offset - 120).clamp(
      0.0,
      scrollController.position.maxScrollExtent,
    );
    scrollController.animateTo(
      target,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 30,
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.32),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppTheme.borderInactive.withOpacity(0.18),
        ),
      ),
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _ScrollChip(
            icon: Icons.keyboard_arrow_up_rounded,
            onTap: _nudgeUp,
          ),
          Expanded(
            child: Center(
              child: Container(
                width: 3,
                decoration: BoxDecoration(
                  color: AppTheme.borderInactive.withOpacity(0.35),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
          ),
          _ScrollChip(
            icon: Icons.keyboard_arrow_down_rounded,
            onTap: _nudgeDown,
          ),
        ],
      ),
    );
  }
}

class _ScrollChip extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _ScrollChip({
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: SizedBox(
          width: 26,
          height: 26,
          child: Icon(
            icon,
            size: 18,
            color: AppTheme.primaryBlack.withOpacity(0.75),
          ),
        ),
      ),
    );
  }
}
