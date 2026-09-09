import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../navigation/app_gate_router.dart';
import '../navigation/session_gate_resolver.dart';
import '../navigation/app_navigator.dart';
import 'fcm_setup.dart';
import 'local_notifications_service.dart';
import '../../data/repositories/notification_repository.dart';
import '../../services/notifications/inbox_refresh_bus.dart';
import '../../services/push/push_service.dart';

/// A4 notification / FCM bootstrap — kept separate from A1 startup.
///
/// Does not redesign A4 UI; structural isolation only.
class NotificationBootstrap {
  NotificationBootstrap._();

  /// Dedupe: avoid sending open_chat feedback twice for same notification.
  static final _feedbackSentIds = <int>{};
  static const int _maxFeedbackDedupSize = 50;

  static Future<void> setup() async {
    debugPrint('[FCM] setup start');
    final permission = await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );
    debugPrint('[FCM] permission status: ${permission.authorizationStatus}');

    await LocalNotificationsService.init(
      onResponse: _handleNotificationResponse,
    );

    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      LocalNotificationsService.showRemoteNotification(message);
      InboxRefreshBus.instance.triggerDebounced();
    });

    FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
      InboxRefreshBus.instance.triggerDebounced();
      _navigateToChatFromMessage(message);
    });

    final initialMessage = await FirebaseMessaging.instance.getInitialMessage();
    if (initialMessage != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        InboxRefreshBus.instance.triggerDebounced();
        _navigateToChatFromMessage(initialMessage);
      });
    }

    _registerTokenOnStart();
    FirebaseMessaging.instance.onTokenRefresh.listen((String newToken) {
      debugPrint('[FCM] onTokenRefresh fired: ${_maskToken(newToken)}');
      _registerTokenOnStart();
    });
  }

  static void _handleNotificationResponse(
    String? actionId,
    String? payloadJson,
  ) {
    final payload = parseNotificationPayload(payloadJson);
    if (payload == null) return;

    final notificationIdStr = payload['notification_id']?.toString();
    if (notificationIdStr == null || notificationIdStr.isEmpty) return;

    final notificationId = int.tryParse(notificationIdStr);
    if (notificationId == null) return;

    final action = actionId ?? 'open_chat';
    final repo = NotificationRepository();

    if (action == 'open_chat') {
      _feedbackSentIds.add(notificationId);
      if (_feedbackSentIds.length > _maxFeedbackDedupSize) {
        _feedbackSentIds.remove(_feedbackSentIds.first);
      }
    }

    repo.sendFeedback(
      notificationId: notificationId,
      action: action,
      clientTs: DateTime.now().toIso8601String(),
    );
    InboxRefreshBus.instance.triggerDebounced();

    if (action == 'open_chat') {
      _navigateToChat(notificationId: notificationId);
    }
  }

  static void _sendOpenChatFeedbackIfNeeded(int? notificationId) {
    if (notificationId == null || notificationId <= 0) return;
    if (_feedbackSentIds.contains(notificationId)) return;
    _feedbackSentIds.add(notificationId);
    if (_feedbackSentIds.length > _maxFeedbackDedupSize) {
      final first = _feedbackSentIds.first;
      _feedbackSentIds.remove(first);
    }
    NotificationRepository().sendFeedback(
      notificationId: notificationId,
      action: 'open_chat',
      clientTs: DateTime.now().toIso8601String(),
    );
  }

  static void _navigateToChatFromMessage(RemoteMessage message) {
    final data = message.data;
    final notificationIdStr = data['notification_id']?.toString();
    final notificationId = int.tryParse(notificationIdStr ?? '');
    final id = (notificationId ?? 0) > 0 ? notificationId : null;
    InboxRefreshBus.instance.triggerDebounced();
    if (id != null) _sendOpenChatFeedbackIfNeeded(id);
    _navigateToChat(notificationId: id);
  }

  static Future<void> _navigateToChat({int? notificationId}) async {
    final context = navigatorKey.currentContext;
    if (context == null) return;

    final hasSession = await SessionGateResolver.hasValidSession();
    if (!context.mounted) return;

    if (!hasSession) {
      AppGateRouter.goToLogin(context);
      return;
    }

    AppGateRouter.goToHeart(
      context,
      fromNotification: true,
      notificationId: notificationId,
    );
  }

  static String _maskToken(String t) {
    if (t.length <= 10) return '***';
    return '${t.substring(0, 6)}...${t.substring(t.length - 4)}';
  }

  static Future<void> _registerTokenOnStart() async {
    try {
      debugPrint('[FCM] getToken() called');
      final token = await FirebaseMessaging.instance.getToken();
      if (token == null || token.isEmpty) return;

      debugPrint('[FCM] token acquired (masked): ${_maskToken(token)}');
      debugPrint('[FCM] saving token to prefs');
      await saveTokenToPreferences(token);
      debugPrint('[FCM] saved token to prefs');
      debugPrint('[FCM] registerFcmTokenToBackend() called');
      final res = await registerFcmTokenToBackend(token);
      debugPrint(
          '[FCM] register result: status=${res.statusCode ?? '?'} ok=${res.ok}');
    } catch (e) {
      debugPrint('[FCM] Token register error: $e');
    }
  }
}
