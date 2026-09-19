import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Compact circular action control for the Gate 3 composer toolbar.
class Gate3ComposerActionButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;
  final Color? iconColor;
  final Color? backgroundColor;
  final double size;
  final double iconSize;

  const Gate3ComposerActionButton({
    super.key,
    required this.icon,
    this.onTap,
    this.iconColor,
    this.backgroundColor,
    this.size = 36,
    this.iconSize = 22,
  });

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(size / 2),
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: backgroundColor ??
                (enabled
                    ? const Color(0xFFF0F2EA)
                    : const Color(0xFFE8EAE4)),
          ),
          child: Icon(
            icon,
            size: iconSize,
            color: iconColor ??
                (enabled ? AppTheme.primaryBlack : AppTheme.iconInactive),
          ),
        ),
      ),
    );
  }
}
