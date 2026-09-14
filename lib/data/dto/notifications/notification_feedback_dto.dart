class NotificationFeedbackDto {
  final bool liked;
  final String timestamp;
  /// Optional V1 dislike reason: too_frequent | irrelevant | unclear.
  final String? reason;

  const NotificationFeedbackDto({
    required this.liked,
    required this.timestamp,
    this.reason,
  });

  Map<String, dynamic> toJson() {
    return {
      'reaction': liked ? 'like' : 'dislike',
      'timestamp': timestamp,
      'feedback': liked ? 'positive' : 'negative',
      if (!liked && reason != null && reason!.isNotEmpty) 'reason': reason,
    };
  }
}
