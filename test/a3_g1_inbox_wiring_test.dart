import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:sedi_app/data/dto/notifications/notification_item_dto.dart';
import 'package:sedi_app/data/dto/notifications/notification_list_response_dto.dart';
import 'package:sedi_app/data/models/notification_item.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/sections/notifications/gate3_notifications_placeholder.dart';
import 'package:sedi_app/features/gate4_notifications/presentation/pages/gate4_notifications_placeholder_page.dart';
import 'package:sedi_app/features/notification/presentation/pages/notifications_inbox_page.dart';
import 'package:sedi_app/features/notifications/presentation/notification_inbox_l10n.dart';
import 'package:sedi_app/features/notifications/presentation/pages/notification_inbox_page.dart';

String _read(String relativePath) => File(relativePath).readAsStringSync();

void main() {
  test('Gate3/Gate4 placeholders wire to canonical NotificationsInboxPage', () {
    expect(
      const Gate3NotificationsPlaceholder(),
      isA<Gate3NotificationsPlaceholder>(),
    );
    expect(
      const Gate4NotificationsPlaceholderPage(),
      isA<Gate4NotificationsPlaceholderPage>(),
    );
    expect(const NotificationsInboxPage(), isA<NotificationsInboxPage>());
    expect(const NotificationInboxPage(), isA<NotificationInboxPage>());

    final gate3 = _read(
      'lib/features/gate3_interactive/presentation/sections/notifications/gate3_notifications_placeholder.dart',
    );
    expect(gate3.contains('NotificationsInboxPage'), isTrue);
    expect(gate3.contains('Scaffold'), isFalse);
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
    expect(dto.title.contains('OTHER'), isTrue);
    expect(dto.metadata, isNull);
  });

  test('inbox UI strings localize EN/FA/AR with RTL FA/AR and LTR EN', () {
    final en = NotificationInboxL10n('en');
    final fa = NotificationInboxL10n('fa');
    final ar = NotificationInboxL10n('ar');

    expect(en.title, 'Notifications');
    expect(fa.title, 'اعلان‌ها');
    expect(ar.title, 'الإشعارات');

    expect(en.filterAll, 'All');
    expect(fa.filterAll, 'همه');
    expect(ar.filterAll, 'الكل');

    expect(en.filterUnread, 'Unread');
    expect(fa.filterUnread, 'خوانده‌نشده');
    expect(ar.filterUnread, 'غير مقروء');

    expect(en.emptyTitle, contains('sent notifications'));
    expect(fa.emptyTitle, isNot(en.emptyTitle));
    expect(ar.emptyTitle, isNot(en.emptyTitle));
    expect(en.emptySubtitle, contains('Scheduled or failed'));
    expect(fa.emptySubtitle, isNot(en.emptySubtitle));
    expect(ar.emptySubtitle, isNot(en.emptySubtitle));

    expect(en.like, 'Like');
    expect(fa.like, isNot(en.like));
    expect(ar.like, isNot(en.like));
    expect(en.dislike, 'Dislike');
    expect(en.markAsRead, 'Mark as read');
    expect(en.loading, contains('Loading'));

    expect(en.isRtl, isFalse);
    expect(fa.isRtl, isTrue);
    expect(ar.isRtl, isTrue);

    const serverBody = 'Managed subject caregiver HealthSubject';
    expect(en.emptySubtitle.contains(serverBody), isFalse);
    expect(fa.emptySubtitle.contains(serverBody), isFalse);
  });

  test('NotificationInboxPage preserves A3 Back + Directionality + no inference',
      () {
    final src = _read(
      'lib/features/notifications/presentation/pages/notification_inbox_page.dart',
    );
    expect(src.contains('A3PageAppBar'), isTrue);
    expect(src.contains('a3_page_app_bar.dart'), isTrue);
    expect(src.contains('NotificationInboxL10n'), isTrue);
    expect(src.contains('Directionality'), isTrue);
    expect(src.contains('TextDirection.rtl'), isTrue);
    expect(src.contains('TextDirection.ltr'), isTrue);
    expect(src.contains('listInboxPage'), isTrue);
    expect(src.contains('_loadMore'), isTrue);
    expect(src.contains('_reload'), isTrue);
    expect(src.contains('_dedupeById'), isTrue);
    expect(src.contains('sendFeedback'), isTrue);
    expect(src.contains('HealthSubject'), isFalse);
    expect(src.contains('MANAGED_SUBJECT'), isFalse);
    expect(src.contains('caregiver'), isFalse);
  });
}
