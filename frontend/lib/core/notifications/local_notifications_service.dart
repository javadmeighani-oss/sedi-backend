/// Local notifications: init, allowlisted Sedi channels, canonical V1 actions.
///
/// Channels: sedi_default, sedi_reminder, sedi_health, sedi_critical (+ legacy map).
/// Actions: ACK_THANKS, NOT_NOW, TALK_LATER, OPEN_CHAT.
/// Routing payload never includes title/body.
library;

import 'dart:convert';
import 'dart:io';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../utils/brand_name.dart';
import 'gate4_notification_contract.dart';
import 'notification_launch_parser.dart';

/// Expected Android raw resource name (file without extension): sedi_alarm.
const String _androidSoundResource = 'sedi_alarm';

/// iOS sound file name (as in Runner bundle): sedi_alarm.wav
const String _iosSoundFile = 'sedi_alarm.wav';

const String _darwinCategoryId = 'SEDI_GATE4_V1';

class LocalNotificationsService {
  /// Callback when user taps notification or action.
  /// [actionId]: canonical or legacy action id; null/body tap => OPEN_CHAT.
  /// [payloadJson]: safe routing JSON only (no title/body).
  static void Function(String? actionId, String? payloadJson)?
      onNotificationResponse;
  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static bool _initialized = false;

  static Future<bool> init({
    void Function(String? actionId, String? payloadJson)? onResponse,
  }) async {
    if (_initialized) return true;
    onNotificationResponse = onResponse;

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    final darwin = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestSoundPermission: true,
      requestBadgePermission: true,
      notificationCategories: [
        DarwinNotificationCategory(
          _darwinCategoryId,
          actions: [
            DarwinNotificationAction.plain('ACK_THANKS', 'Thanks'),
            DarwinNotificationAction.plain('NOT_NOW', 'Not now'),
            DarwinNotificationAction.plain('TALK_LATER', 'Talk later'),
            DarwinNotificationAction.plain(
              'OPEN_CHAT',
              'Open chat',
              options: {DarwinNotificationActionOption.foreground},
            ),
          ],
        ),
      ],
    );
    final settings = InitializationSettings(android: android, iOS: darwin);

    final ok = await _plugin.initialize(
      settings,
      onDidReceiveNotificationResponse: _handleNotificationResponse,
    );
    if (ok != true) return false;

    if (Platform.isAndroid) {
      final impl = _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
      for (final ch in _sediChannels) {
        await impl?.createNotificationChannel(ch);
      }
      // Preserve legacy channel ids for older OS-stored notifications.
      for (final ch in _legacyCompatChannels) {
        await impl?.createNotificationChannel(ch);
      }
    }
    _initialized = true;
    return true;
  }

  static List<AndroidNotificationChannel> get _sediChannels => [
        AndroidNotificationChannel(
          'sedi_default',
          '${sediBrandName('en')} Default',
          description: 'General ${sediBrandName('en')} notifications',
          importance: Importance.defaultImportance,
          playSound: true,
          enableVibration: false,
        ),
        AndroidNotificationChannel(
          'sedi_reminder',
          '${sediBrandName('en')} Reminders',
          description: 'Reminder notifications',
          importance: Importance.low,
          playSound: false,
          enableVibration: false,
        ),
        AndroidNotificationChannel(
          'sedi_health',
          '${sediBrandName('en')} Health',
          description: 'Health notifications',
          importance: Importance.high,
          playSound: true,
          sound: RawResourceAndroidNotificationSound(_androidSoundResource),
          enableVibration: true,
        ),
        AndroidNotificationChannel(
          'sedi_critical',
          '${sediBrandName('en')} Critical',
          description: 'Critical alerts',
          importance: Importance.max,
          playSound: true,
          sound: RawResourceAndroidNotificationSound(_androidSoundResource),
          enableVibration: true,
        ),
      ];

  static List<AndroidNotificationChannel> get _legacyCompatChannels => [
        AndroidNotificationChannel(
          'sedi_alerts',
          '${sediBrandName('en')} Alerts',
          description: 'Legacy alerts channel',
          importance: Importance.high,
          playSound: true,
          sound: RawResourceAndroidNotificationSound(_androidSoundResource),
          enableVibration: true,
        ),
        const AndroidNotificationChannel(
          'morning',
          'Morning Brief',
          description: 'Legacy morning channel',
          importance: Importance.low,
          playSound: false,
          enableVibration: false,
        ),
        const AndroidNotificationChannel(
          'engagement',
          'Engagement',
          description: 'Legacy engagement channel',
          importance: Importance.defaultImportance,
          playSound: true,
          enableVibration: false,
        ),
        AndroidNotificationChannel(
          'health_alert',
          'Health Alerts',
          description: 'Legacy health alerts',
          importance: Importance.high,
          playSound: true,
          sound: RawResourceAndroidNotificationSound(_androidSoundResource),
          enableVibration: true,
        ),
      ];

  static void _handleNotificationResponse(NotificationResponse? response) {
    if (response == null) return;
    onNotificationResponse?.call(response.actionId, response.payload);
  }

  /// Whether the OS will already display an FCM notification payload.
  /// When true, background/quit delivery should not show a second local notif.
  static bool osWillDisplayRemoteNotification(RemoteMessage message) {
    final n = message.notification;
    if (n == null) return false;
    final hasTitle = (n.title ?? '').trim().isNotEmpty;
    final hasBody = (n.body ?? '').trim().isNotEmpty;
    return hasTitle || hasBody;
  }

  /// Show notification from FCM. Safe routing payload only (no title/body).
  static Future<void> showRemoteNotification(
    RemoteMessage message, {
    bool forceLocalDisplay = false,
  }) async {
    if (!_initialized) await init();

    // Avoid duplicate local display when OS already shows the notification
    // payload, unless caller forces foreground local display.
    if (!forceLocalDisplay && osWillDisplayRemoteNotification(message)) {
      return;
    }

    final notif = message.notification;
    final data = Map<String, dynamic>.from(message.data);
    final title = notif?.title ?? data['title']?.toString() ?? 'Notification';
    final body = notif?.body ?? data['body']?.toString() ?? '';

    final notificationId =
        parsePositiveNotificationId(data['notification_id']) ?? 0;
    if (notificationId <= 0) {
      // Require a positive notification id for local display + routing.
      return;
    }
    final sourceId = parsePositiveNotificationId(data['source_notification_id']);
    final conversationId = sanitizeConversationId(data['conversation_id']);
    final deeplinkUrl = data['deeplink_url']?.toString();
    final rawChannel = data['channel_id']?.toString() ??
        data['channel']?.toString() ??
        data['type']?.toString();
    final channelId = resolveSediAndroidChannelId(rawChannel);

    final payloadMap = buildSafeLocalRoutingPayload(
      notificationId: notificationId,
      sourceNotificationId: sourceId,
      conversationId: conversationId,
      deeplinkUrl: deeplinkUrl,
      channelId: channelId,
    );
    final payloadStr = jsonEncode(payloadMap);
    final notifId = _notificationIdToInt('$notificationId');

    final actionsParsed = parseFcmGate4Actions(data);
    final androidActions = actionsParsed
        .map(
          (a) => AndroidNotificationAction(
            a.actionId,
            a.label,
            showsUserInterface: a.actionId == 'OPEN_CHAT',
            cancelNotification: true,
          ),
        )
        .toList(growable: false);

    final critical = isCriticalChannel(channelId);
    final (importance, priority, playSound, enableVibration) =
        _channelImportance(channelId);

    if (Platform.isAndroid) {
      final android = AndroidNotificationDetails(
        channelId,
        _channelDisplayName(channelId),
        channelDescription: '${sediBrandName('en')} notifications',
        importance: importance,
        priority: priority,
        playSound: playSound,
        enableVibration: enableVibration,
        sound: (critical || channelId == 'sedi_health')
            ? RawResourceAndroidNotificationSound(_androidSoundResource)
            : null,
        actions: androidActions,
        category: AndroidNotificationCategory.message,
      );
      final darwin = DarwinNotificationDetails(
        presentAlert: true,
        presentSound: true,
        sound: critical ? _iosSoundFile : null,
        categoryIdentifier: _darwinCategoryId,
      );
      final details = NotificationDetails(android: android, iOS: darwin);
      await _plugin.show(
        notifId,
        title,
        body,
        details,
        payload: payloadStr,
      );
    } else {
      final darwin = DarwinNotificationDetails(
        presentAlert: true,
        presentSound: true,
        sound: _iosSoundFile,
        categoryIdentifier: _darwinCategoryId,
      );
      final details = NotificationDetails(iOS: darwin);
      await _plugin.show(
        notifId,
        title,
        body,
        details,
        payload: payloadStr,
      );
    }
  }

  static String _channelDisplayName(String channelId) {
    switch (resolveSediAndroidChannelId(channelId)) {
      case 'sedi_reminder':
        return '${sediBrandName('en')} Reminders';
      case 'sedi_health':
        return '${sediBrandName('en')} Health';
      case 'sedi_critical':
        return '${sediBrandName('en')} Critical';
      case 'sedi_default':
      default:
        return '${sediBrandName('en')} Default';
    }
  }

  static (Importance, Priority, bool, bool) _channelImportance(
    String channelId,
  ) {
    switch (resolveSediAndroidChannelId(channelId)) {
      case 'sedi_critical':
        return (Importance.max, Priority.max, true, true);
      case 'sedi_health':
        return (Importance.high, Priority.high, true, true);
      case 'sedi_reminder':
        return (Importance.low, Priority.low, false, false);
      case 'sedi_default':
      default:
        return (
          Importance.defaultImportance,
          Priority.defaultPriority,
          true,
          false
        );
    }
  }

  static int _notificationIdToInt(String id) {
    final n = int.tryParse(id);
    if (n != null && n > 0 && n < 2147483647) return n;
    return id.hashCode.abs() % 2147483647;
  }

  /// Show a local notification with title, body, optional payload.
  static Future<void> showNotification({
    required int id,
    required String title,
    required String body,
    String? payload,
  }) async {
    if (!_initialized) await init();
    final android = AndroidNotificationDetails(
      'sedi_default',
      _channelDisplayName('sedi_default'),
      channelDescription: '${sediBrandName('en')} health and reminder alerts',
      importance: Importance.high,
      priority: Priority.high,
      playSound: true,
      sound: RawResourceAndroidNotificationSound(_androidSoundResource),
    );
    const darwin = DarwinNotificationDetails(
      presentAlert: true,
      presentSound: true,
      sound: _iosSoundFile,
      categoryIdentifier: _darwinCategoryId,
    );
    final details = NotificationDetails(android: android, iOS: darwin);
    await _plugin.show(id, title, body, details, payload: payload);
  }
}
