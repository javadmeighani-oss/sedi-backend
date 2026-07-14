/// SharedPreferences-backed pending NotificationLaunchContext store.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'notification_launch_context.dart';
import 'notification_launch_parser.dart';

const String _prefsKey = 'sedi_pending_notification_launch_v1';
const Duration kPendingNotificationLaunchTtl = Duration(hours: 24);

/// Persists only the safe [NotificationLaunchContext] across Gate 1 / Gate 2.
class PendingNotificationLaunchStore {
  PendingNotificationLaunchStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ensurePrefs() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  /// Save [context], replacing any older pending launch.
  Future<void> save(NotificationLaunchContext context) async {
    if (!context.isValid) return;
    final prefs = await _ensurePrefs();
    await prefs.setString(_prefsKey, jsonEncode(context.toJson()));
  }

  /// Load a non-expired valid context, or null.
  Future<NotificationLaunchContext?> load({DateTime? now}) async {
    final prefs = await _ensurePrefs();
    final raw = prefs.getString(_prefsKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) {
        await clear();
        return null;
      }
      final ctx = NotificationLaunchContext.fromJson(
        Map<String, dynamic>.from(decoded),
      );
      if (!ctx.isValid ||
          parsePositiveNotificationId(ctx.sourceNotificationId) == null) {
        await clear();
        return null;
      }
      final effectiveNow = (now ?? DateTime.now()).toUtc();
      if (effectiveNow.difference(ctx.receivedAt.toUtc()) >
          kPendingNotificationLaunchTtl) {
        await clear();
        return null;
      }
      return ctx;
    } catch (_) {
      await clear();
      return null;
    }
  }

  Future<void> clear() async {
    final prefs = await _ensurePrefs();
    await prefs.remove(_prefsKey);
  }
}
