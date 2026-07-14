class ChatSendResponse {
  final String message;
  final String language;
  final int? userId;
  final DateTime? timestamp;
  final bool requiresSecurityCheck;
  final String? detectedName;
  final bool? continuedFromNotification;
  final int? sourceNotificationId;
  final String? conversationId;

  const ChatSendResponse({
    required this.message,
    required this.language,
    this.userId,
    this.timestamp,
    this.requiresSecurityCheck = false,
    this.detectedName,
    this.continuedFromNotification,
    this.sourceNotificationId,
    this.conversationId,
  });

  factory ChatSendResponse.fromJson(Map<String, dynamic> json) {
    final rawUserId = json['user_id'];
    final rawSource = json['source_notification_id'];
    return ChatSendResponse(
      message: json['message']?.toString() ?? '',
      language: json['language']?.toString() ?? 'en',
      userId: rawUserId is int
          ? rawUserId
          : int.tryParse(rawUserId?.toString() ?? ''),
      timestamp: DateTime.tryParse(json['timestamp']?.toString() ?? ''),
      requiresSecurityCheck: json['requires_security_check'] as bool? ?? false,
      detectedName: json['detected_name']?.toString(),
      continuedFromNotification: json['continued_from_notification'] as bool?,
      sourceNotificationId: rawSource is int
          ? rawSource
          : int.tryParse(rawSource?.toString() ?? ''),
      conversationId: json['conversation_id']?.toString(),
    );
  }
}
