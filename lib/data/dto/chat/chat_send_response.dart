class ChatSendResponse {
  final String message;
  final String language;
  final int? userId;
  final DateTime? timestamp;
  final bool requiresSecurityCheck;
  final String? detectedName;
  final int? sourceNotificationId;
  final bool? firstIntro;
  final bool? introCompleted;
  final String? proactiveOpener;

  const ChatSendResponse({
    required this.message,
    required this.language,
    this.userId,
    this.timestamp,
    this.requiresSecurityCheck = false,
    this.detectedName,
    this.sourceNotificationId,
    this.firstIntro,
    this.introCompleted,
    this.proactiveOpener,
  });

  factory ChatSendResponse.fromJson(Map<String, dynamic> json) {
    final rawUserId = json['user_id'];
    return ChatSendResponse(
      message: json['message']?.toString() ?? '',
      language: json['language']?.toString() ?? 'en',
      userId: rawUserId is int
          ? rawUserId
          : int.tryParse(rawUserId?.toString() ?? ''),
      timestamp: DateTime.tryParse(json['timestamp']?.toString() ?? ''),
      requiresSecurityCheck: json['requires_security_check'] as bool? ?? false,
      detectedName: json['detected_name']?.toString(),
      sourceNotificationId: json['source_notification_id'] is int
          ? json['source_notification_id'] as int
          : int.tryParse(json['source_notification_id']?.toString() ?? ''),
      firstIntro: json['first_intro'] as bool?,
      introCompleted: json['intro_completed'] as bool?,
      proactiveOpener: json['proactive_opener']?.toString(),
    );
  }
}
