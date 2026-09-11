class ChatSendRequest {
  final String message;
  final int? sourceNotificationId;
  final String? conversationId;
  final int? healthSubjectId;

  const ChatSendRequest({
    required this.message,
    this.sourceNotificationId,
    this.conversationId,
    this.healthSubjectId,
  });

  Map<String, dynamic> toJson() {
    return {
      'message': message,
      if (sourceNotificationId != null)
        'source_notification_id': sourceNotificationId,
      if (conversationId != null && conversationId!.isNotEmpty)
        'conversation_id': conversationId,
      if (healthSubjectId != null) 'health_subject_id': healthSubjectId,
      // JWT is identity authority — do not send body user_id.
    };
  }
}
