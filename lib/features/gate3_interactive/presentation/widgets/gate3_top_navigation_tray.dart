import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Presentation-only collapsible tray around the A3 destination icon row.
class Gate3TopNavigationTray extends StatelessWidget {
  final bool expanded;
  final VoidCallback onToggle;
  final Widget child;
  final String expandLabel;
  final String collapseLabel;

  static const Duration toggleDuration = Duration(milliseconds: 240);
  static const Curve toggleCurve = Curves.easeInOutCubic;
  static const double handleHeight = 44;

  const Gate3TopNavigationTray({
    super.key,
    required this.expanded,
    required this.onToggle,
    required this.child,
    required this.expandLabel,
    required this.collapseLabel,
  });

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: Color(0xFFFFFFFF),
        border: Border(
          bottom: BorderSide(color: AppTheme.gate2BorderSubtle, width: 0.8),
        ),
        borderRadius: BorderRadius.vertical(
          bottom: Radius.circular(18),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ClipRect(
            child: AnimatedSize(
              duration: toggleDuration,
              curve: toggleCurve,
              alignment: Alignment.topCenter,
              child: expanded
                  ? Padding(
                      padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                      child: child,
                    )
                  : const SizedBox(width: double.infinity, height: 0),
            ),
          ),
          Semantics(
            button: true,
            label: expanded ? collapseLabel : expandLabel,
            child: Material(
              color: const Color(0x00000000),
              child: InkWell(
                onTap: onToggle,
                child: SizedBox(
                  width: double.infinity,
                  height: handleHeight,
                  child: Center(
                    child: Icon(
                      expanded
                          ? Icons.keyboard_arrow_up
                          : Icons.keyboard_arrow_down,
                      size: 18,
                      color: AppTheme.textSecondary,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
