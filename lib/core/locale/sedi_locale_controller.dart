import 'package:flutter/foundation.dart';

import '../utils/user_preferences.dart';
import 'sedi_locale_descriptor.dart';
import 'sedi_locale_registry.dart';

/// Single global runtime locale authority for the Sedi experience.
///
/// Authority model:
/// - Pre-auth: runtime locale is immediate UI authority; local keys are bootstrap cache.
/// - Post-auth: backend Account `preferred_language` is persisted account authority;
///   runtime is reconciled from backend-confirmed profile only.
///
/// Legacy SharedPreferences keys `user_language` + `language_pref` remain as
/// compatibility bootstrap cache writes — not independent authorities.
class SediLocaleController extends ChangeNotifier {
  SediLocaleController._();

  static final SediLocaleController instance = SediLocaleController._();

  /// Test-only constructor.
  @visibleForTesting
  factory SediLocaleController.forTest({
    SediLocaleDescriptor? initial,
  }) {
    final c = SediLocaleController._();
    if (initial != null) {
      c._current = initial;
    }
    return c;
  }

  SediLocaleDescriptor _current = SediLocaleRegistry.en;
  bool _bootstrapped = false;

  SediLocaleDescriptor get current => _current;
  String get languageCode => _current.code;
  bool get isRtl => _current.isRtl;
  String get defaultCalendar => _current.defaultCalendar;

  /// Load bootstrap cache into runtime (cold start). Safe default = en.
  Future<void> bootstrapFromCache() async {
    if (_bootstrapped) return;
    final cached = await UserPreferences.getUserLanguage();
    final pref = await UserPreferences.getLanguagePref();
    final candidate = (cached.trim().isNotEmpty && cached != 'auto')
        ? cached
        : (pref != 'auto' ? pref : SediLocaleRegistry.fallbackCode);
    _current = SediLocaleRegistry.resolve(candidate);
    _bootstrapped = true;
    notifyListeners();
  }

  /// Immediate UI locale change (A2 selection / pre-auth). Optionally caches.
  Future<void> setRuntimeLocale(
    String code, {
    bool persistBootstrapCache = true,
  }) async {
    final next = SediLocaleRegistry.resolve(code);
    if (_current.code == next.code) {
      if (persistBootstrapCache) {
        await _writeBootstrapCache(next.code);
      }
      return;
    }
    _current = next;
    notifyListeners();
    if (persistBootstrapCache) {
      await _writeBootstrapCache(next.code);
    }
  }

  /// Apply backend-confirmed preferred_language after successful auth reconcile.
  Future<void> reconcileFromBackendConfirmed(String? preferredLanguage) async {
    final next = SediLocaleRegistry.resolve(preferredLanguage);
    _current = next;
    notifyListeners();
    await _writeBootstrapCache(next.code);
  }

  /// Compatibility storage only — dual-write legacy keys through one path.
  Future<void> _writeBootstrapCache(String code) async {
    final normalized = SediLocaleRegistry.resolve(code).code;
    await UserPreferences.saveUserLanguage(normalized);
    await UserPreferences.saveLanguagePref(normalized);
  }

  @visibleForTesting
  void debugResetForTest({SediLocaleDescriptor? to}) {
    _current = to ?? SediLocaleRegistry.en;
    _bootstrapped = false;
  }
}
