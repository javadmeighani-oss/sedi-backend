/// Safe notification-origin launch context for Gate 4 → Gate 3 continuity.
///
/// Never stores title, body, diagnosis, dosage, raw metadata, or tokens.
library;

/// Immutable allowlisted launch context for notification → chat continuation.
class NotificationLaunchContext {
  final int sourceNotificationId;
  final String? conversationId;
  final DateTime receivedAt;
  final String interactionSource;

  const NotificationLaunchContext({
    required this.sourceNotificationId,
    required this.receivedAt,
    this.conversationId,
    this.interactionSource = 'notification',
  });

  bool get isValid =>
      sourceNotificationId > 0 && interactionSource == 'notification';

  Map<String, dynamic> toJson() => {
        'source_notification_id': sourceNotificationId,
        if (conversationId != null && conversationId!.isNotEmpty)
          'conversation_id': conversationId,
        'received_at': receivedAt.toUtc().toIso8601String(),
        'interaction_source': interactionSource,
      };

  factory NotificationLaunchContext.fromJson(Map<String, dynamic> json) {
    final rawId =
        json['source_notification_id'] ?? json['sourceNotificationId'];
    final id =
        rawId is int ? rawId : int.tryParse(rawId?.toString() ?? '') ?? 0;
    final conversationRaw = json['conversation_id']?.toString() ??
        json['conversationId']?.toString();
    String? conversation;
    if (conversationRaw != null &&
        conversationRaw.isNotEmpty &&
        conversationRaw.length <= 128 &&
        RegExp(r'^[A-Za-z0-9._:\-]{1,128}$').hasMatch(conversationRaw)) {
      conversation = conversationRaw;
    }
    final receivedRaw =
        json['received_at']?.toString() ?? json['receivedAt']?.toString();
    final received =
        DateTime.tryParse(receivedRaw ?? '')?.toUtc() ?? DateTime.now().toUtc();
    return NotificationLaunchContext(
      sourceNotificationId: id,
      conversationId: conversation,
      receivedAt: received,
      interactionSource: 'notification',
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is NotificationLaunchContext &&
          sourceNotificationId == other.sourceNotificationId &&
          conversationId == other.conversationId &&
          interactionSource == other.interactionSource;

  @override
  int get hashCode =>
      Object.hash(sourceNotificationId, conversationId, interactionSource);
}
