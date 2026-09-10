import 'package:flutter/material.dart';

/// Immutable metadata for one Sedi language.
///
/// Dial/country codes are intentionally absent — phone country is independent.
class SediLocaleDescriptor {
  final String code;
  final Locale locale;
  final String displayName;
  final TextDirection textDirection;
  final String defaultCalendar;
  final bool enabled;
  final String fallbackLocale;

  const SediLocaleDescriptor({
    required this.code,
    required this.locale,
    required this.displayName,
    required this.textDirection,
    required this.defaultCalendar,
    required this.enabled,
    required this.fallbackLocale,
  });

  bool get isRtl => textDirection == TextDirection.rtl;
}
