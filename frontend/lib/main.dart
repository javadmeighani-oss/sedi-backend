import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/navigation/app_gate_router.dart';
import 'core/navigation/session_gate_resolver.dart';
import 'core/navigation/app_navigator.dart';
import 'core/notifications/fcm_setup.dart';
import 'core/notifications/local_notifications_service.dart';
import 'data/repositories/notification_repository.dart';
import 'services/notifications/inbox_refresh_bus.dart';
import 'services/push/push_service.dart';

void _fcmLog(String message) {
  if (kDebugMode) {
    debugPrint(message);
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    await Firebase.initializeApp();
    _fcmLog('[FCM] Firebase initialized');
    await _setupFcm();
  } catch (_) {
    _fcmLog('[FCM] setup skipped');
  }

  runApp(const SediApp());
}

/// Dedupe: avoid sending open_chat feedback twice for same notification.
final _feedbackSentIds = <int>{};
const int _maxFeedbackDedupSize = 50;

Future<void> _setupFcm() async {
  _fcmLog('[FCM] setup start');
  await FirebaseMessaging.instance.requestPermission(
    alert: true,
    badge: true,
    sound: true,
    provisional: false,
  );
  _fcmLog('[FCM] permission requested');

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
  FirebaseMessaging.instance.onTokenRefresh.listen((_) {
    _fcmLog('[FCM] push registration refresh event');
    _registerTokenOnStart();
  });
}

void _handleNotificationResponse(String? actionId, String? payloadJson) {
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

void _sendOpenChatFeedbackIfNeeded(int? notificationId) {
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

void _navigateToChatFromMessage(RemoteMessage message) {
  final data = message.data;
  final notificationIdStr = data['notification_id']?.toString();
  final notificationId = int.tryParse(notificationIdStr ?? '');
  final id = (notificationId ?? 0) > 0 ? notificationId : null;
  InboxRefreshBus.instance.triggerDebounced();
  if (id != null) _sendOpenChatFeedbackIfNeeded(id);
  _navigateToChat(notificationId: id);
}

Future<void> _navigateToChat({int? notificationId}) async {
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

Future<void> _registerTokenOnStart() async {
  try {
    _fcmLog('[FCM] push registration started');
    final token = await FirebaseMessaging.instance.getToken();
    if (token == null || token.isEmpty) return;

    await saveTokenToPreferences(token);
    final res = await registerFcmTokenToBackend(token);
    _fcmLog(
      '[FCM] push registration finished: ok=${res.ok} status=${res.statusCode ?? '?'}',
    );
  } catch (_) {
    _fcmLog('[FCM] push registration failed');
  }
}
