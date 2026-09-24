import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// Shared A2 width / type scale. Pages must not hard-code control widths.
class A2Layout {
  A2Layout._();

  static const double compactControlMax = AppTheme.a2CompactControlMax;
  static const double primaryCtaMax = AppTheme.a2PrimaryCtaMax;
  static const double readableContentMax = AppTheme.a2ReadableContentMax;
  static const double primaryCtaHeight = AppTheme.a2PrimaryCtaHeight;
  static const double primaryCtaFontSize = AppTheme.a2PrimaryCtaFontSize;
  static const double controlFontSize = AppTheme.a2ControlFontSize;

  /// Center [child] at [maxWidth], shrinking to the available width on narrow screens.
  static Widget band({
    required Widget child,
    double maxWidth = compactControlMax,
  }) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final available = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : MediaQuery.sizeOf(context).width;
        final width = available < maxWidth ? available : maxWidth;
        return Align(
          alignment: Alignment.center,
          child: SizedBox(width: width, child: child),
        );
      },
    );
  }
}
