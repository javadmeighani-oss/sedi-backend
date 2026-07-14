/// Gate 4 notification metadata DTOs (inbox / push contract).
library;

/// Canonical V1 action IDs.
const Set<String> kGate4V1ActionIds = {
  'ACK_THANKS',
  'NOT_NOW',
  'TALK_LATER',
  'OPEN_CHAT',
};

class Gate4NotificationAction {
  final String actionId;
  final String label;

  const Gate4NotificationAction({
    required this.actionId,
    required this.label,
  });

  factory Gate4NotificationAction.fromJson(Map<String, dynamic> json) {
    return Gate4NotificationAction(
      actionId: (json['action_id'] ?? json['actionId'] ?? '').toString(),
      label: (json['label'] ?? '').toString(),
    );
  }

  bool get isCanonical => kGate4V1ActionIds.contains(actionId);
}

class Gate4NotificationMetadata {
  final String contractVersion;
  final int notificationId;
  final int sourceNotificationId;
  final String category;
  final String risk;
  final String language;
  final String deeplinkUrl;
  final List<Gate4NotificationAction> actions;

  const Gate4NotificationMetadata({
    required this.contractVersion,
    required this.notificationId,
    required this.sourceNotificationId,
    required this.category,
    required this.risk,
    required this.language,
    required this.deeplinkUrl,
    required this.actions,
  });

  /// Parse `gate4_metadata` first; fall back to legacy `metadata` map shape.
  static Gate4NotificationMetadata? fromNotificationJson(
    Map<String, dynamic> json, {
    int? topLevelNotificationId,
  }) {
    Map<String, dynamic>? raw;
    if (json['gate4_metadata'] is Map) {
      raw = Map<String, dynamic>.from(json['gate4_metadata'] as Map);
    } else if (json['metadata'] is Map) {
      raw = Map<String, dynamic>.from(json['metadata'] as Map);
    }
    if (raw == null) return null;
    return fromJson(raw, topLevelNotificationId: topLevelNotificationId);
  }

  static Gate4NotificationMetadata? fromJson(
    Map<String, dynamic> json, {
    int? topLevelNotificationId,
  }) {
    try {
      final notificationId = _positiveInt(
            json['notification_id'] ?? json['notificationId'],
          ) ??
          topLevelNotificationId;
      final sourceId = _positiveInt(
            json['source_notification_id'] ?? json['sourceNotificationId'],
          ) ??
          notificationId;
      if (notificationId == null || sourceId == null) return null;
      if (topLevelNotificationId != null &&
          topLevelNotificationId > 0 &&
          notificationId != topLevelNotificationId) {
        // Soft mismatch: keep only when source matches top-level.
        if (sourceId != topLevelNotificationId) return null;
      }

      final actionsRaw = json['actions'];
      final actions = <Gate4NotificationAction>[];
      if (actionsRaw is List) {
        for (final item in actionsRaw) {
          if (item is! Map) continue;
          final action = Gate4NotificationAction.fromJson(
            Map<String, dynamic>.from(item),
          );
          if (!action.isCanonical) continue;
          if (action.label.trim().isEmpty) continue;
          actions.add(action);
        }
      }

      final language = _normalizeLanguage(json['language']?.toString());
      final deeplink = json['deeplink_url']?.toString() ??
          json['deeplinkUrl']?.toString() ??
          '';

      return Gate4NotificationMetadata(
        contractVersion: json['contract_version']?.toString() ??
            json['contractVersion']?.toString() ??
            '',
        notificationId: notificationId,
        sourceNotificationId: sourceId,
        category: json['category']?.toString() ?? '',
        risk: json['risk']?.toString() ?? '',
        language: language,
        deeplinkUrl: deeplink,
        actions: actions,
      );
    } catch (_) {
      return null;
    }
  }

  static int? _positiveInt(Object? raw) {
    if (raw == null) return null;
    final n = raw is int ? raw : int.tryParse(raw.toString());
    if (n == null || n <= 0) return null;
    return n;
  }

  static String normalizeLanguagePublic(String? raw) => _normalizeLanguage(raw);

  static String _normalizeLanguage(String? raw) {
    if (raw == null || raw.trim().isEmpty) return 'en';
    final lang = raw.trim().toLowerCase().split('-').first;
    if (lang == 'fa' || lang == 'en' || lang == 'ar') return lang;
    return 'en';
  }
}
