/// Pure parser for FCM data, local-notification payload JSON, and Sedi deeplinks.
library;

import 'dart:convert';

import 'notification_launch_context.dart';

final RegExp _safeConversationId = RegExp(r'^[A-Za-z0-9._:\-]{1,128}$');

/// Maximum Dart-safe notification id (avoid platform int overflow).
const int kMaxNotificationId = 9007199254740991; // 2^53 - 1

/// Parse a positive int ID; reject non-positive / malformed / out-of-range.
int? parsePositiveNotificationId(Object? raw) {
  if (raw == null) return null;
  final n = raw is int ? raw : int.tryParse(raw.toString().trim());
  if (n == null || n <= 0 || n > kMaxNotificationId) return null;
  return n;
}

String? sanitizeConversationId(Object? raw) {
  if (raw == null) return null;
  final s = raw.toString().trim();
  if (s.isEmpty || s.length > 128) return null;
  if (!_safeConversationId.hasMatch(s)) return null;
  return s;
}

/// Parse approved `sedi://chat?...` deeplink into safe routing fields.
///
/// Accepted:
/// - sedi://chat?from=notif&source_notification_id=<positive-int>
/// - sedi://chat?from=notif&id=<positive-int> (legacy)
///
/// Rejects other schemes/hosts, userinfo, fragments, and malformed IDs.
({int? sourceNotificationId, int? legacyId, String? conversationId})?
    parseSediChatDeeplink(String? url) {
  if (url == null || url.trim().isEmpty) return null;
  final trimmed = url.trim();
  Uri uri;
  try {
    uri = Uri.parse(trimmed);
  } catch (_) {
    return null;
  }

  if (uri.scheme.toLowerCase() != 'sedi') return null;
  if (uri.host.toLowerCase() != 'chat') return null;
  if (uri.hasFragment) return null;
  if (uri.userInfo.isNotEmpty) return null;

  final from = uri.queryParameters['from']?.toLowerCase();
  if (from != null && from != 'notif') return null;

  final sourceId = parsePositiveNotificationId(
      uri.queryParameters['source_notification_id']);
  final legacyId = parsePositiveNotificationId(uri.queryParameters['id']);
  final conversationId =
      sanitizeConversationId(uri.queryParameters['conversation_id']);

  if (sourceId == null && legacyId == null) return null;
  return (
    sourceNotificationId: sourceId,
    legacyId: legacyId,
    conversationId: conversationId,
  );
}

/// Canonical precedence for source notification ID:
/// 1. explicit source_notification_id
/// 2. deeplink source_notification_id
/// 3. explicit notification_id
/// 4. deeplink legacy id
///
/// When explicit IDs conflict with deeplink IDs of the same kind, fail closed
/// (return null) rather than guess.
NotificationLaunchContext? parseNotificationLaunchContext({
  Map<String, dynamic>? data,
  String? payloadJson,
  String? deeplinkUrl,
  DateTime? receivedAt,
}) {
  Map<String, dynamic> merged = <String, dynamic>{};
  if (data != null) merged.addAll(data);
  if (payloadJson != null && payloadJson.trim().isNotEmpty) {
    try {
      final decoded = jsonDecode(payloadJson);
      if (decoded is Map) {
        merged.addAll(Map<String, dynamic>.from(decoded));
      }
    } catch (_) {
      // ignore malformed payload JSON
    }
  }

  final explicitSource =
      parsePositiveNotificationId(merged['source_notification_id']);
  final explicitNotif = parsePositiveNotificationId(merged['notification_id']);
  final conversationFromData =
      sanitizeConversationId(merged['conversation_id']);

  final link = parseSediChatDeeplink(
    deeplinkUrl ?? merged['deeplink_url']?.toString(),
  );

  // Conflict policy: fail closed when both sources provide different IDs.
  if (explicitSource != null &&
      link?.sourceNotificationId != null &&
      explicitSource != link!.sourceNotificationId) {
    return null;
  }
  if (explicitNotif != null &&
      link?.legacyId != null &&
      explicitSource == null &&
      link!.sourceNotificationId == null &&
      explicitNotif != link.legacyId) {
    return null;
  }

  final resolvedId = explicitSource ??
      link?.sourceNotificationId ??
      explicitNotif ??
      link?.legacyId;

  if (resolvedId == null) return null;

  final conversationId = conversationFromData ?? link?.conversationId;

  return NotificationLaunchContext(
    sourceNotificationId: resolvedId,
    conversationId: conversationId,
    receivedAt: (receivedAt ?? DateTime.now()).toUtc(),
    interactionSource: 'notification',
  );
}

/// Build a safe local-notification routing payload (no title/body).
Map<String, String> buildSafeLocalRoutingPayload({
  required int notificationId,
  int? sourceNotificationId,
  String? conversationId,
  String? deeplinkUrl,
  String? channelId,
}) {
  final payload = <String, String>{
    'notification_id': notificationId.toString(),
  };
  final source = sourceNotificationId ?? notificationId;
  if (source > 0) {
    payload['source_notification_id'] = source.toString();
  }
  final conversation = sanitizeConversationId(conversationId);
  if (conversation != null) {
    payload['conversation_id'] = conversation;
  }
  if (deeplinkUrl != null && deeplinkUrl.startsWith('sedi://')) {
    payload['deeplink_url'] = deeplinkUrl;
  }
  if (channelId != null && channelId.isNotEmpty) {
    payload['channel_id'] = channelId;
  }
  return payload;
}
