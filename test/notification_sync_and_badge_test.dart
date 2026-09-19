import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/notifications/notification_seen_window.dart';
import 'package:sedi_app/services/notifications/notifications_service.dart';

void main() {
  group('mergeSeenIdsRollingWindow', () {
    test('keeps newest first and caps at max', () {
      final existing = ['a', 'b', 'c'];
      final newIds = ['d', 'e'];
      final result = mergeSeenIdsRollingWindow(existing, newIds, 5);
      expect(result, ['d', 'e', 'a', 'b', 'c']);
    });

    test('rolling window: over 200 ids stored as 200 newest', () {
      final existing = List.generate(200, (i) => 'id_$i');
      final newIds = ['new1', 'new2', 'new3'];
      final result = mergeSeenIdsRollingWindow(existing, newIds, 200);
      expect(result.length, 200);
      expect(result.take(3).toList(), ['new1', 'new2', 'new3']);
      // Newest-first: early existing ids remain; oldest tail is dropped.
      expect(result.contains('id_0'), true);
      expect(result.contains('id_199'), false);
    });

    test('no duplicate new ids in merged list', () {
      final existing = ['a', 'b'];
      final newIds = ['c', 'a'];
      final result = mergeSeenIdsRollingWindow(existing, newIds, 10);
      expect(result, ['c', 'a', 'b']);
    });
  });

  group('NotificationsService.parseUnreadCount', () {
    test('prefers unread_count over page count', () {
      final resp = {
        'ok': true,
        'data': {
          'count': 20,
          'unread_count': 42,
          'total': 42,
          'notifications': [],
        },
      };
      expect(NotificationsService.parseUnreadCount(resp), 42);
    });

    test('ignores total and count when unread_count missing', () {
      expect(
        NotificationsService.parseUnreadCount({
          'ok': true,
          'data': {'total': 7, 'count': 3, 'notifications': []},
        }),
        0,
      );
      expect(
        NotificationsService.parseUnreadCount({
          'ok': true,
          'data': {'count': 5, 'notifications': []},
        }),
        0,
      );
    });

    test('does not derive badge from notifications length', () {
      final resp = {
        'ok': true,
        'data': {
          'notifications': [
            {'id': '1'},
            {'id': '2'},
          ],
        },
      };
      expect(NotificationsService.parseUnreadCount(resp), 0);
    });

    test('returns 0 when not ok', () {
      expect(NotificationsService.parseUnreadCount({'ok': false}), 0);
    });

    test('returns 0 when data null', () {
      expect(
        NotificationsService.parseUnreadCount({'ok': true, 'data': null}),
        0,
      );
    });
  });
}
