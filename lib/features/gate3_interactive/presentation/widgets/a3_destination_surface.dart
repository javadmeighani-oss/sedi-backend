import 'package:flutter/material.dart';

import '../../../../core/locale/calendar_date_math.dart';
import '../../../../core/theme/app_theme.dart';

/// Shared presentation surface for A3 destinations reused by Lifestyle,
/// Gadgets, Notifications, and Profile. Pure UI — no API or authority.
class A3DestinationSurface {
  A3DestinationSurface._();

  static const Color canvas = Color(0xFFFFFFFF);

  static const List<BoxShadow> cardShadow = [
    BoxShadow(
      color: Color(0x0F000000),
      blurRadius: 16,
      offset: Offset(0, 6),
    ),
  ];

  static BoxDecoration cardDecoration({Color? borderColor}) {
    return BoxDecoration(
      color: AppTheme.gate2CardWhite,
      borderRadius: BorderRadius.circular(AppTheme.radiusLarge),
      border: Border.all(
        color: borderColor ?? AppTheme.gate2BorderSubtle,
        width: 0.8,
      ),
      boxShadow: cardShadow,
    );
  }

  /// Formats an ISO date or timestamp for display.
  /// Unparseable values are returned unchanged — never invented.
  static String formatIsoTimestamp(String? raw, String languageCode) {
    if (raw == null || raw.trim().isEmpty) return '—';
    final s = raw.trim();
    final m = RegExp(r'^(\d{4}-\d{2}-\d{2})').firstMatch(s);
    if (m == null) return s;
    final date = CalendarDateMath.formatIsoForLanguage(m.group(1)!, languageCode);
    final time = RegExp(r'T(\d{2}:\d{2})').firstMatch(s);
    if (time != null) return '$date  ${time.group(1)}';
    return date;
  }
}

class A3DestinationCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? borderColor;
  final VoidCallback? onTap;

  const A3DestinationCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.fromLTRB(16, 16, 16, 16),
    this.borderColor,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final body = Padding(padding: padding, child: child);
    if (onTap == null) {
      return DecoratedBox(
        decoration: A3DestinationSurface.cardDecoration(borderColor: borderColor),
        child: body,
      );
    }
    return Material(
      color: AppTheme.gate2CardWhite,
      borderRadius: BorderRadius.circular(AppTheme.radiusLarge),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppTheme.radiusLarge),
        onTap: onTap,
        child: Ink(
          decoration: A3DestinationSurface.cardDecoration(borderColor: borderColor),
          child: body,
        ),
      ),
    );
  }
}

class A3DestinationChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const A3DestinationChip({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected
          ? AppTheme.gate2ButtonOlive.withOpacity(0.14)
          : AppTheme.gate2CardWhite,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            border: Border.all(
              color: selected
                  ? AppTheme.gate2ButtonOlive
                  : AppTheme.gate2BorderSubtle,
            ),
          ),
          child: Text(
            label,
            style: TextStyle(
              color: selected
                  ? AppTheme.gate2ButtonOlive
                  : AppTheme.textPrimary,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
        ),
      ),
    );
  }
}

class A3DestinationFact extends StatelessWidget {
  final String label;
  final String value;
  final TextDirection? valueDirection;
  final Color? valueColor;

  const A3DestinationFact({
    super.key,
    required this.label,
    required this.value,
    this.valueDirection,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: AppTheme.textSecondary,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 4),
          Directionality(
            textDirection: valueDirection ?? Directionality.of(context),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: Text(
                value,
                style: TextStyle(
                  color: valueColor ?? AppTheme.textPrimary,
                  fontSize: 15,
                  height: 1.35,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
