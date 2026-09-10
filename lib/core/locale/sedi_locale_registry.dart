import 'package:flutter/material.dart';

import 'sedi_locale_descriptor.dart';

/// Central V1 locale registry (en/fa/ar). Extensible without feature rewrites.
///
/// Future language enablement requires:
/// 1) registry entry
/// 2) translation resources
/// 3) certified backend/chat/notification support
/// 4) tests
/// — not A1/A2/A3/A4 logic forks.
class SediLocaleRegistry {
  SediLocaleRegistry._();

  static const String fallbackCode = 'en';

  static const SediLocaleDescriptor en = SediLocaleDescriptor(
    code: 'en',
    locale: Locale('en'),
    displayName: 'English',
    textDirection: TextDirection.ltr,
    defaultCalendar: 'gregorian',
    enabled: true,
    fallbackLocale: fallbackCode,
  );

  static const SediLocaleDescriptor fa = SediLocaleDescriptor(
    code: 'fa',
    locale: Locale('fa'),
    displayName: 'فارسی',
    textDirection: TextDirection.rtl,
    defaultCalendar: 'jalali',
    enabled: true,
    fallbackLocale: fallbackCode,
  );

  static const SediLocaleDescriptor ar = SediLocaleDescriptor(
    code: 'ar',
    locale: Locale('ar'),
    displayName: 'العربية',
    textDirection: TextDirection.rtl,
    defaultCalendar: 'hijri',
    enabled: true,
    fallbackLocale: fallbackCode,
  );

  static const List<SediLocaleDescriptor> all = [en, fa, ar];

  static List<SediLocaleDescriptor> get enabledLocales =>
      all.where((d) => d.enabled).toList(growable: false);

  static List<Locale> get supportedLocales =>
      enabledLocales.map((d) => d.locale).toList(growable: false);

  /// Resolve any code to an enabled descriptor; unknown → fallback.
  static SediLocaleDescriptor resolve(String? code) {
    final normalized = (code ?? '').trim().toLowerCase();
    if (normalized.isEmpty) return en;
    for (final d in all) {
      if (d.code == normalized) {
        return d.enabled ? d : en;
      }
    }
    return en;
  }

  static bool isSupported(String? code) {
    final normalized = (code ?? '').trim().toLowerCase();
    return all.any((d) => d.enabled && d.code == normalized);
  }
}
