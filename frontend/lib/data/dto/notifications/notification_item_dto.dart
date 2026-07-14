import 'gate4_notification_metadata.dart';

class NotificationItemDto {
  final int id;
  final String channel;
  final String title;
  final String body;
  final DateTime createdAt;
  final bool isRead;
  final String? priority;
  final String? status;
  final String? provider;
  final String? dedupeKey;
  final Gate4NotificationMetadata? gate4Metadata;

  const NotificationItemDto({
    required this.id,
    required this.channel,
    required this.title,
    required this.body,
    required this.createdAt,
    required this.isRead,
    this.priority,
    this.status,
    this.provider,
    this.dedupeKey,
    this.gate4Metadata,
  });

  factory NotificationItemDto.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    final id =
        rawId is int ? rawId : int.tryParse(rawId?.toString() ?? '') ?? 0;
    final type = json['type']?.toString() ?? '';
    final topChannel = json['channel']?.toString();
    final channel =
        (topChannel != null && topChannel.isNotEmpty) ? topChannel : type;
    final createdRaw = json['created_at']?.toString();
    final createdAt = DateTime.tryParse(createdRaw ?? '') ??
        DateTime.fromMillisecondsSinceEpoch(0);

    return NotificationItemDto(
      id: id,
      channel: channel.isEmpty ? 'general' : channel,
      title: json['title']?.toString() ?? '',
      body: json['body']?.toString() ?? '',
      createdAt: createdAt,
      isRead: json['is_read'] as bool? ?? false,
      priority: json['priority']?.toString(),
      status: json['status']?.toString(),
      provider: json['provider']?.toString(),
      dedupeKey: json['dedupe_key']?.toString(),
      gate4Metadata: Gate4NotificationMetadata.fromNotificationJson(
        json,
        topLevelNotificationId: id,
      ),
    );
  }
}
