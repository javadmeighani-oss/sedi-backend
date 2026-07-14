class NotificationFeedbackDto {
  final String reaction;
  final String timestamp;
  final String? actionId;
  final String? feedback;
  final bool? liked;

  const NotificationFeedbackDto({
    required this.reaction,
    required this.timestamp,
    this.actionId,
    this.feedback,
    this.liked,
  });

  /// Canonical Gate 4 V1 feedback: reaction=interact + action_id.
  factory NotificationFeedbackDto.canonical({
    required String actionId,
    required DateTime timestamp,
  }) {
    return NotificationFeedbackDto(
      reaction: 'interact',
      actionId: actionId,
      timestamp: timestamp.toUtc().toIso8601String(),
    );
  }

  /// Legacy like/dislike feedback used by non-inbox surfaces.
  factory NotificationFeedbackDto.legacyLiked({
    required bool liked,
    required DateTime timestamp,
  }) {
    return NotificationFeedbackDto(
      reaction: liked ? 'positive' : 'negative',
      liked: liked,
      actionId: liked ? 'tap_like' : 'tap_dislike',
      timestamp: timestamp.toUtc().toIso8601String(),
    );
  }

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{
      'reaction': reaction,
      'timestamp': timestamp,
    };
    if (actionId != null && actionId!.isNotEmpty) {
      map['action_id'] = actionId;
    }
    if (feedback != null && feedback!.isNotEmpty) {
      map['feedback'] = feedback;
    }
    if (liked != null) {
      map['liked'] = liked;
    }
    return map;
  }
}
