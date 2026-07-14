import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:sedi_app/core/notifications/gate4_notification_contract.dart';
import 'package:sedi_app/core/notifications/notification_launch_context.dart';
import 'package:sedi_app/core/notifications/notification_launch_parser.dart';
import 'package:sedi_app/core/notifications/pending_notification_launch_store.dart';
import 'package:sedi_app/data/dto/chat/chat_send_request.dart';
import 'package:sedi_app/data/dto/chat/chat_send_response.dart';
import 'package:sedi_app/data/dto/history_response.dart';
import 'package:sedi_app/data/dto/notifications/gate4_notification_metadata.dart';
import 'package:sedi_app/data/dto/notifications/notification_feedback_dto.dart';
import 'package:sedi_app/data/dto/notifications/notification_item_dto.dart';
import 'package:sedi_app/features/chat/state/same_day_history_mapper.dart';
import 'package:sedi_app/services/notifications/notifications_service.dart';

void main() {
  group('HistoryResponse (WP-A)', () {
    test('parses timezone and current_group_key', () {
      final json = {
        'group': 'daily',
        'timezone': 'Asia/Tehran',
        'current_group_key': '2026-07-13',
        'items': [
          {
            'key': '2026-07-13',
            'turns': [
              {
                'id': 1,
                'created_at': '2026-07-13T10:00:00Z',
                'user_message': 'hi',
                'sedi_response': 'hello',
              }
            ],
          },
          {
            'key': '2026-07-12',
            'turns': [
              {
                'id': 2,
                'created_at': '2026-07-12T10:00:00Z',
                'user_message': 'yesterday',
                'sedi_response': 'ok',
              }
            ],
          },
        ],
      };
      final res = HistoryResponse.fromJson(json);
      expect(res.timezone, 'Asia/Tehran');
      expect(res.currentGroupKey, '2026-07-13');
      expect(res.items.length, 2);
    });

    test('missing new fields stays nullable for legacy fallback', () {
      final res = HistoryResponse.fromJson({
        'group': 'daily',
        'items': [],
      });
      expect(res.timezone, isNull);
      expect(res.currentGroupKey, isNull);
    });

    test('same-day selection by current_group_key ignores other days', () {
      final res = HistoryResponse.fromJson({
        'group': 'daily',
        'current_group_key': '2026-07-13',
        'items': [
          {
            'key': '2026-07-13',
            'turns': [
              {
                'id': 10,
                'created_at': '2026-07-13T08:00:00Z',
                'user_message': 'a',
                'sedi_response': 'b',
              },
              {
                'id': 11,
                'created_at': '2026-07-13T09:00:00Z',
                'user_message': 'c',
                'sedi_response': 'd',
              },
              {
                'id': 10,
                'created_at': '2026-07-13T08:00:00Z',
                'user_message': 'a',
                'sedi_response': 'b',
              },
            ],
          },
          {
            'key': '2026-07-12',
            'turns': [
              {
                'id': 9,
                'created_at': '2026-07-12T08:00:00Z',
                'user_message': 'old',
                'sedi_response': 'old-r',
              }
            ],
          },
        ],
      });
      final turns = mapSameDayHistoryTurns(res);
      expect(turns.where((t) => t.text == 'old').isEmpty, isTrue);
      expect(turns.map((t) => t.text).toList(), ['a', 'b', 'c', 'd']);
      expect(turns.map((t) => t.localId).toSet().length, turns.length);
    });

    test('empty current day yields no restored turns (intro path)', () {
      final res = HistoryResponse.fromJson({
        'group': 'daily',
        'current_group_key': '2026-07-13',
        'items': [
          {
            'key': '2026-07-12',
            'turns': [
              {
                'id': 1,
                'created_at': '2026-07-12T08:00:00Z',
                'user_message': 'old',
                'sedi_response': 'old-r',
              }
            ],
          },
        ],
      });
      expect(mapSameDayHistoryTurns(res), isEmpty);
    });
  });

  group('ChatSendRequest / Response (WP-D)', () {
    test('normal request omits notification fields', () {
      final json = const ChatSendRequest(userId: 1, message: 'hello').toJson();
      expect(json.containsKey('source_notification_id'), isFalse);
      expect(json.containsKey('conversation_id'), isFalse);
      expect(json.containsKey('interaction_source'), isFalse);
      expect(json['message'], 'hello');
    });

    test('notification request includes snake_case keys', () {
      final json = const ChatSendRequest(
        userId: 1,
        message: 'from notif',
        sourceNotificationId: 42,
        conversationId: 'conv-1',
        interactionSource: 'notification',
      ).toJson();
      expect(json['source_notification_id'], 42);
      expect(json['conversation_id'], 'conv-1');
      expect(json['interaction_source'], 'notification');
    });

    test('response additive fields parse safely', () {
      final res = ChatSendResponse.fromJson({
        'message': 'ok',
        'language': 'en',
        'continued_from_notification': true,
        'source_notification_id': 7,
        'conversation_id': 'c1',
      });
      expect(res.continuedFromNotification, isTrue);
      expect(res.sourceNotificationId, 7);
      expect(res.conversationId, 'c1');
    });
  });

  group('NotificationLaunchParser (WP-B)', () {
    test('accepted deeplink source_notification_id', () {
      final ctx = parseNotificationLaunchContext(
        deeplinkUrl: 'sedi://chat?from=notif&source_notification_id=12',
      );
      expect(ctx?.sourceNotificationId, 12);
      expect(ctx?.interactionSource, 'notification');
    });

    test('legacy deeplink id fallback', () {
      final ctx = parseNotificationLaunchContext(
        deeplinkUrl: 'sedi://chat?from=notif&id=99',
      );
      expect(ctx?.sourceNotificationId, 99);
    });

    test('rejects http scheme and wrong host', () {
      expect(
        parseNotificationLaunchContext(deeplinkUrl: 'https://chat?id=1'),
        isNull,
      );
      expect(
        parseNotificationLaunchContext(deeplinkUrl: 'sedi://evil?id=1'),
        isNull,
      );
    });

    test('rejects userinfo and fragment', () {
      expect(
        parseNotificationLaunchContext(
          deeplinkUrl: 'sedi://user:pass@chat?id=1',
        ),
        isNull,
      );
      expect(
        parseNotificationLaunchContext(
          deeplinkUrl: 'sedi://chat?id=1#frag',
        ),
        isNull,
      );
    });

    test('source ID precedence prefers explicit source_notification_id', () {
      final ctx = parseNotificationLaunchContext(data: {
        'source_notification_id': 5,
        'notification_id': 9,
        'deeplink_url': 'sedi://chat?from=notif&id=3',
      });
      expect(ctx?.sourceNotificationId, 5);
    });

    test('conflict between explicit and deeplink fails closed', () {
      final ctx = parseNotificationLaunchContext(data: {
        'source_notification_id': 5,
        'deeplink_url':
            'sedi://chat?from=notif&source_notification_id=6',
      });
      expect(ctx, isNull);
    });

    test('safe local payload never includes title/body', () {
      final payload = buildSafeLocalRoutingPayload(
        notificationId: 10,
        sourceNotificationId: 11,
        conversationId: 'abc',
        deeplinkUrl: 'sedi://chat?from=notif&id=11',
      );
      expect(payload.containsKey('title'), isFalse);
      expect(payload.containsKey('body'), isFalse);
      expect(payload['source_notification_id'], '11');
    });

    test('never uses body/title as chat context', () {
      final ctx = parseNotificationLaunchContext(data: {
        'title': 'High heart rate',
        'body': 'Your vitals...',
      });
      expect(ctx, isNull);
    });
  });

  group('PendingNotificationLaunchStore (WP-C)', () {
    test('save/load/clear and expiry', () async {
      SharedPreferences.setMockInitialValues({});
      final store = PendingNotificationLaunchStore();
      final now = DateTime.utc(2026, 7, 13, 12);
      final ctx = NotificationLaunchContext(
        sourceNotificationId: 44,
        conversationId: 'c-1',
        receivedAt: now,
      );
      await store.save(ctx);
      final loaded = await store.load(now: now);
      expect(loaded?.sourceNotificationId, 44);
      expect(loaded?.conversationId, 'c-1');

      final expired = await store.load(now: now.add(const Duration(hours: 25)));
      expect(expired, isNull);

      await store.save(ctx);
      await store.clear();
      expect(await store.load(now: now), isNull);
    });

    test('invalid stored JSON is discarded', () async {
      SharedPreferences.setMockInitialValues({
        'sedi_pending_notification_launch_v1': '{not-json',
      });
      final store = PendingNotificationLaunchStore();
      expect(await store.load(), isNull);
    });

    test('no body or metadata persisted', () async {
      SharedPreferences.setMockInitialValues({});
      final store = PendingNotificationLaunchStore();
      await store.save(
        NotificationLaunchContext(
          sourceNotificationId: 1,
          receivedAt: DateTime.utc(2026, 7, 13),
        ),
      );
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString('sedi_pending_notification_launch_v1')!;
      expect(raw.contains('body'), isFalse);
      expect(raw.contains('title'), isFalse);
      expect(raw.contains('metadata'), isFalse);
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      expect(decoded.keys.toSet(), containsAll(['source_notification_id']));
      expect(decoded.containsKey('body'), isFalse);
    });

    test('latest valid launch replaces older', () async {
      SharedPreferences.setMockInitialValues({});
      final store = PendingNotificationLaunchStore();
      final t0 = DateTime.utc(2026, 7, 13, 10);
      await store.save(NotificationLaunchContext(
        sourceNotificationId: 1,
        receivedAt: t0,
      ));
      await store.save(NotificationLaunchContext(
        sourceNotificationId: 2,
        receivedAt: t0.add(const Duration(minutes: 1)),
      ));
      final loaded = await store.load(now: t0.add(const Duration(minutes: 2)));
      expect(loaded?.sourceNotificationId, 2);
    });
  });

  group('Gate4 metadata / feedback (WP-E/F)', () {
    test('gate4_metadata parses and unknown actions ignored', () {
      final meta = Gate4NotificationMetadata.fromNotificationJson({
        'id': 7,
        'gate4_metadata': {
          'contract_version': '1',
          'notification_id': 7,
          'source_notification_id': 7,
          'category': 'health',
          'risk': 'low',
          'language': 'fa',
          'deeplink_url': 'sedi://chat?from=notif&source_notification_id=7',
          'actions': [
            {'action_id': 'ACK_THANKS', 'label': 'ممنون'},
            {'action_id': 'OPEN_CHAT', 'label': 'گفتگو'},
            {'action_id': 'HACK_ME', 'label': 'bad'},
          ],
        },
      }, topLevelNotificationId: 7);
      expect(meta, isNotNull);
      expect(meta!.actions.map((a) => a.actionId).toList(),
          ['ACK_THANKS', 'OPEN_CHAT']);
      expect(meta.language, 'fa');
    });

    test('legacy metadata fallback', () {
      final meta = Gate4NotificationMetadata.fromNotificationJson({
        'id': 3,
        'metadata': {
          'notification_id': 3,
          'source_notification_id': 3,
          'actions': [
            {'action_id': 'NOT_NOW', 'label': 'Not now'},
          ],
        },
      }, topLevelNotificationId: 3);
      expect(meta?.actions.single.actionId, 'NOT_NOW');
    });

    test('NotificationItemDto exposes single gate4Metadata property', () {
      final dto = NotificationItemDto.fromJson({
        'id': 5,
        'channel': 'sedi_health',
        'title': 't',
        'body': 'b',
        'created_at': '2026-07-13T10:00:00Z',
        'is_read': false,
        'gate4_metadata': {
          'notification_id': 5,
          'source_notification_id': 5,
          'actions': [
            {'action_id': 'OPEN_CHAT', 'label': 'Open'},
          ],
        },
      });
      expect(dto.channel, 'sedi_health');
      expect(dto.gate4Metadata?.sourceNotificationId, 5);
      expect(dto.body, 'b'); // display only
    });

    test('canonical feedback body', () {
      final dto = NotificationFeedbackDto.canonical(
        actionId: 'ACK_THANKS',
        timestamp: DateTime.utc(2026, 7, 13),
      );
      expect(dto.toJson(), {
        'reaction': 'interact',
        'timestamp': '2026-07-13T00:00:00.000Z',
        'action_id': 'ACK_THANKS',
      });
    });

    test('feedback dedupe prevents duplicates', () {
      final dedupe = NotificationFeedbackDedupe(maxSize: 2);
      expect(dedupe.alreadySent(1, 'OPEN_CHAT'), isFalse);
      dedupe.mark(1, 'OPEN_CHAT');
      expect(dedupe.alreadySent(1, 'OPEN_CHAT'), isTrue);
      dedupe.mark(2, 'NOT_NOW');
      dedupe.mark(3, 'ACK_THANKS');
      expect(dedupe.alreadySent(1, 'OPEN_CHAT'), isFalse); // evicted
    });
  });

  group('FCM / channel contract (WP-G)', () {
    test('FCM action parsing and legacy mapping', () {
      final actions = parseFcmGate4Actions({
        'language': 'en',
        'gate4_actions': ['like', 'OPEN_CHAT', 'evil'],
        'action_labels': {'OPEN_CHAT': 'Chat now'},
      });
      expect(actions.any((a) => a.actionId == 'ACK_THANKS'), isTrue);
      expect(
        actions.firstWhere((a) => a.actionId == 'OPEN_CHAT').label,
        'Chat now',
      );
      expect(actions.any((a) => a.actionId == 'evil'), isFalse);
    });

    test('Android channel allowlist and legacy fallback', () {
      expect(resolveSediAndroidChannelId('sedi_critical'), 'sedi_critical');
      expect(resolveSediAndroidChannelId('health_alert'), 'sedi_health');
      expect(resolveSediAndroidChannelId('morning'), 'sedi_reminder');
      expect(resolveSediAndroidChannelId('arbitrary_server_channel'),
          'sedi_default');
      expect(isCriticalChannel('critical'), isTrue);
    });

    test('canonical action normalization', () {
      expect(normalizeCanonicalActionId('like'), 'ACK_THANKS');
      expect(normalizeCanonicalActionId('open_chat'), 'OPEN_CHAT');
      expect(normalizeCanonicalActionId('nope'), isNull);
      expect(normalizeCanonicalActionId(null), 'OPEN_CHAT');
    });
  });
}
