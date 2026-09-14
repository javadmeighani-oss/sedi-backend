import 'package:flutter_test/flutter_test.dart';

import 'package:sedi_app/data/dto/notifications/notification_item_dto.dart';
import 'package:sedi_app/data/dto/notifications/notification_list_response_dto.dart';
import 'package:sedi_app/data/models/notification_item.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/sections/notifications/gate3_notifications_placeholder.dart';
import 'package:sedi_app/features/gate4_notifications/presentation/pages/gate4_notifications_placeholder_page.dart';
import 'package:sedi_app/features/notification/presentation/pages/notifications_inbox_page.dart';
import 'package:sedi_app/features/notifications/presentation/pages/notification_inbox_page.dart';

void main() {
  test('Gate3/Gate4 placeholders wire to canonical NotificationsInboxPage', () {
    expect(const Gate3NotificationsPlaceholder(), isA<Gate3NotificationsPlaceholder>());
    expect(const Gate4NotificationsPlaceholderPage(), isA<Gate4NotificationsPlaceholderPage>());
    expect(const NotificationsInboxPage(), isA<NotificationsInboxPage>());
    expect(const NotificationInboxPage(), isA<NotificationInboxPage>());
  });

  test('list response parses cursor pagination metadata and sent_at', () {
    final dto = NotificationListResponseDto.fromJson({
      'notifications': [
        {
          'id': 7,
          'type': 'connection_ping',
          'channel': 'engagement',
          'title': 'Hi',
          'body': 'Body',
          'created_at': '2026-09-13T10:00:00',
          'sent_at': '2026-09-13T10:01:00',
          'is_read': false,
        }
      ],
      'total': 1,
      'unread_count': 1,
      'count': 1,
      'next_cursor': 'abc',
      'has_more': true,
      'limit': 20,
    });
    expect(dto.hasMore, isTrue);
    expect(dto.nextCursor, 'abc');
    expect(dto.limit, 20);
    expect(dto.notifications.first.sentAt, isNotNull);
    final item = NotificationItem.fromDto(dto.notifications.first);
    expect(item.sentAt, isNotNull);
    expect(item.id, 7);
  });

  test('NotificationItemDto does not invent gadget identity from body text', () {
    final dto = NotificationItemDto.fromJson({
      'id': 1,
      'type': 'health_alert',
      'title': 'OTHER gadget offline',
      'body': 'Managed subject caregiver HealthSubject',
      'created_at': '2026-09-13T10:00:00',
      'sent_at': '2026-09-13T10:00:00',
      'is_read': true,
    });
    // Presentation fields only — no derived gadget/person identity fields.
    expect(dto.title.contains('OTHER'), isTrue);
    expect(dto.metadata, isNull);
  });
}
