import 'notification_item_dto.dart';

class NotificationListResponseDto {
  final List<NotificationItemDto> notifications;
  final int? total;
  final int? unreadCount;
  final int? count;
  final String? nextCursor;
  final bool hasMore;
  final int? limit;

  const NotificationListResponseDto({
    required this.notifications,
    this.total,
    this.unreadCount,
    this.count,
    this.nextCursor,
    this.hasMore = false,
    this.limit,
  });

  factory NotificationListResponseDto.fromJson(Map<String, dynamic> json) {
    final rawList = json['notifications'];
    final items = <NotificationItemDto>[];
    if (rawList is List) {
      for (final item in rawList) {
        if (item is Map) {
          items.add(
              NotificationItemDto.fromJson(Map<String, dynamic>.from(item)));
        }
      }
    }
    return NotificationListResponseDto(
      notifications: items,
      total: json['total'] as int?,
      unreadCount: json['unread_count'] as int?,
      count: json['count'] as int?,
      nextCursor: json['next_cursor']?.toString(),
      hasMore: json['has_more'] == true,
      limit: json['limit'] as int?,
    );
  }
}
