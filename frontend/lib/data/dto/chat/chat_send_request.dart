class ChatSendRequest {
  final int userId;
  final String message;
  final int? sourceNotificationId;
  final String? conversationId;
  final String? interactionSource;

  const ChatSendRequest({
    required this.userId,
    required this.message,
    this.sourceNotificationId,
    this.conversationId,
    this.interactionSource,
  });

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{
      'user_id': userId,
      'message': message,
    };
    if (sourceNotificationId != null && sourceNotificationId! > 0) {
      map['source_notification_id'] = sourceNotificationId;
    }
    if (conversationId != null && conversationId!.trim().isNotEmpty) {
      map['conversation_id'] = conversationId!.trim();
    }
    if (interactionSource != null && interactionSource!.trim().isNotEmpty) {
      map['interaction_source'] = interactionSource!.trim();
    }
    return map;
  }
}
