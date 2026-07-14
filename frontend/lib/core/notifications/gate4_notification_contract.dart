/// Canonical Gate 4 action labels and Android channel allowlist helpers.
library;

import 'dart:convert';

import '../../data/dto/notifications/gate4_notification_metadata.dart';

/// Allowlisted Android notification channels (Gate 4 delivery).
const Set<String> kSediAndroidChannelIds = {
  'sedi_default',
  'sedi_reminder',
  'sedi_health',
  'sedi_critical',
};

/// Legacy channel ids still accepted as input and mapped to allowlisted channels.
const Set<String> kLegacyAndroidChannelIds = {
  'sedi_alerts',
  'morning',
  'engagement',
  'health_alert',
  'health_status',
};

/// Resolve an allowlisted channel. Never returns an arbitrary server channel.
String resolveSediAndroidChannelId(String? raw) {
  final value = (raw ?? '').trim().toLowerCase();
  if (kSediAndroidChannelIds.contains(value)) return value;

  switch (value) {
    case 'morning':
    case 'sedi_reminder':
      return 'sedi_reminder';
    case 'health_alert':
    case 'health_status':
    case 'sedi_health':
      return 'sedi_health';
    case 'critical':
    case 'sedi_critical':
      return 'sedi_critical';
    case 'engagement':
    case 'sedi_alerts':
    case 'sedi_default':
    default:
      return 'sedi_default';
  }
}

bool isCriticalChannel(String channelId) =>
    resolveSediAndroidChannelId(channelId) == 'sedi_critical';

/// Fallback localization for canonical actions (fa / en / ar).
String fallbackGate4ActionLabel(String actionId, String language) {
  final lang = Gate4NotificationMetadata.normalizeLanguagePublic(language);
  const en = {
    'ACK_THANKS': 'Thanks',
    'NOT_NOW': 'Not now',
    'TALK_LATER': 'Talk later',
    'OPEN_CHAT': 'Open chat',
  };
  const fa = {
    'ACK_THANKS': 'ممنون',
    'NOT_NOW': 'الان نه',
    'TALK_LATER': 'بعداً حرف بزنیم',
    'OPEN_CHAT': 'باز کردن گفتگو',
  };
  const ar = {
    'ACK_THANKS': 'شكرًا',
    'NOT_NOW': 'ليس الآن',
    'TALK_LATER': 'نتحدث لاحقًا',
    'OPEN_CHAT': 'فتح المحادثة',
  };
  final table = switch (lang) {
    'fa' => fa,
    'ar' => ar,
    _ => en,
  };
  return table[actionId] ?? en[actionId] ?? actionId;
}

/// Normalize legacy local-notification / FCM action ids to canonical V1.
String? normalizeCanonicalActionId(String? raw) {
  if (raw == null || raw.trim().isEmpty) return 'OPEN_CHAT';
  final value = raw.trim().toUpperCase();
  if (kGate4V1ActionIds.contains(value)) return value;
  switch (raw.trim().toLowerCase()) {
    case 'like':
    case 'tap_like':
      return 'ACK_THANKS';
    case 'dislike':
    case 'tap_dislike':
      return 'NOT_NOW';
    case 'open_chat':
    case 'open-chat':
      return 'OPEN_CHAT';
    case 'dismissed':
    case 'not_now':
      return 'NOT_NOW';
    case 'talk_later':
      return 'TALK_LATER';
    case 'ack_thanks':
    case 'thanks':
      return 'ACK_THANKS';
    default:
      return null;
  }
}

/// Parse gate4_actions / action_labels from FCM data into canonical actions.
List<Gate4NotificationAction> parseFcmGate4Actions(Map<String, dynamic> data) {
  final language = Gate4NotificationMetadata.normalizeLanguagePublic(
    data['language']?.toString(),
  );
  final result = <Gate4NotificationAction>[];
  final seen = <String>{};

  void addAction(String actionId, String? label) {
    if (!kGate4V1ActionIds.contains(actionId)) return;
    if (!seen.add(actionId)) return;
    final resolved = (label != null && label.trim().isNotEmpty)
        ? label.trim()
        : fallbackGate4ActionLabel(actionId, language);
    result.add(Gate4NotificationAction(actionId: actionId, label: resolved));
  }

  Object? actionsRaw = data['gate4_actions'] ?? data['actions'];
  if (actionsRaw is String && actionsRaw.trim().isNotEmpty) {
    final trimmed = actionsRaw.trim();
    if (trimmed.startsWith('[')) {
      try {
        actionsRaw = jsonDecode(trimmed);
      } catch (_) {
        // fall through
      }
    }
    if (actionsRaw is String) {
      for (final part in trimmed.split(',')) {
        final id = normalizeCanonicalActionId(part.trim());
        if (id != null) addAction(id, null);
      }
      actionsRaw = null;
    }
  }

  if (actionsRaw is List) {
    for (final item in actionsRaw) {
      if (item is Map) {
        final id = normalizeCanonicalActionId(
          (item['action_id'] ?? item['actionId'] ?? item['id'])?.toString(),
        );
        if (id == null) continue;
        addAction(id, (item['label'] ?? item['title'])?.toString());
      } else if (item is String) {
        final id = normalizeCanonicalActionId(item);
        if (id != null) addAction(id, null);
      }
    }
  }

  Object? labelsRaw = data['action_labels'];
  if (labelsRaw is String && labelsRaw.trim().startsWith('{')) {
    try {
      labelsRaw = jsonDecode(labelsRaw);
    } catch (_) {
      labelsRaw = null;
    }
  }
  if (labelsRaw is Map) {
    for (final entry in labelsRaw.entries) {
      final id = normalizeCanonicalActionId(entry.key.toString());
      if (id == null) continue;
      final label = entry.value?.toString();
      if (label == null || label.trim().isEmpty) continue;
      final idx = result.indexWhere((a) => a.actionId == id);
      if (idx >= 0) {
        result[idx] =
            Gate4NotificationAction(actionId: id, label: label.trim());
      } else {
        addAction(id, label);
      }
    }
  }

  if (result.isEmpty) {
    for (final id in kGate4V1ActionIds) {
      addAction(id, null);
    }
  }
  return result;
}
