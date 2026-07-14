import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/navigation/app_gate_router.dart';
import 'core/navigation/session_gate_resolver.dart';
import 'core/navigation/app_navigator.dart';
import 'core/notifications/fcm_setup.dart';
import 'core/notifications/gate4_notification_contract.dart';
import 'core/notifications/local_notifications_service.dart';
import 'core/notifications/notification_launch_context.dart';
import 'core/notifications/notification_launch_parser.dart';
import 'core/notifications/pending_notification_launch_store.dart';
import 'data/repositories/notification_repository.dart';
import 'services/notifications/inbox_refresh_bus.dart';
import 'services/push/push_service.dart';

void _fcmLog(String message) {
  if (kDebugMode) {
    debugPrint(message);
  }
}

final PendingNotificationLaunchStore _pendingLaunchStore =
    PendingNotificationLaunchStore();

/// Dedupe feedback by notification_id + action_id (bounded).
final _feedbackSentKeys = <String>{};
final _feedbackSentOrder = <String>[];
const int _maxFeedbackDedupSize = 50;

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

  // Foreground: OS may not display the notification — always show local copy.
  FirebaseMessaging.onMessage.listen((RemoteMessage message) {
    LocalNotificationsService.showRemoteNotification(
      message,
      forceLocalDisplay: true,
    );
    InboxRefreshBus.instance.triggerDebounced();
  });

  FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
    InboxRefreshBus.instance.triggerDebounced();
    _openFromRemoteMessage(message);
  });

  final initialMessage = await FirebaseMessaging.instance.getInitialMessage();
  if (initialMessage != null) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      InboxRefreshBus.instance.triggerDebounced();
      _openFromRemoteMessage(initialMessage);
    });
  }

  _registerTokenOnStart();
  FirebaseMessaging.instance.onTokenRefresh.listen((_) {
    _fcmLog('[FCM] push registration refresh event');
    _registerTokenOnStart();
  });
}

void _markFeedbackDeduped(int notificationId, String actionId) {
  final key = '$notificationId::$actionId';
  if (_feedbackSentKeys.contains(key)) return;
  _feedbackSentKeys.add(key);
  _feedbackSentOrder.add(key);
  while (_feedbackSentOrder.length > _maxFeedbackDedupSize) {
    final oldest = _feedbackSentOrder.removeAt(0);
    _feedbackSentKeys.remove(oldest);
  }
}

bool _wasFeedbackSent(int notificationId, String actionId) =>
    _feedbackSentKeys.contains('$notificationId::$actionId');

Future<void> _sendCanonicalFeedbackIfNeeded({
  required int notificationId,
  required String actionId,
}) async {
  if (notificationId <= 0) return;
  final canonical = normalizeCanonicalActionId(actionId);
  if (canonical == null) return;
  if (_wasFeedbackSent(notificationId, canonical)) return;
  _markFeedbackDeduped(notificationId, canonical);
  await NotificationRepository().sendCanonicalFeedback(
    notificationId: notificationId,
    actionId: canonical,
  );
}

void _handleNotificationResponse(String? actionId, String? payloadJson) {
  final payload = parseNotificationPayload(payloadJson);
  if (payload == null) return;

  final launch = parseNotificationLaunchContext(payloadJson: payloadJson);
  final notificationId =
      parsePositiveNotificationId(payload['notification_id']) ??
          launch?.sourceNotificationId;
  if (notificationId == null) return;

  final canonical = normalizeCanonicalActionId(actionId) ?? 'OPEN_CHAT';
  InboxRefreshBus.instance.triggerDebounced();

  _sendCanonicalFeedbackIfNeeded(
    notificationId: notificationId,
    actionId: canonical,
  );

  if (canonical == 'OPEN_CHAT') {
    final ctx = launch ??
        NotificationLaunchContext(
          sourceNotificationId: notificationId,
          receivedAt: DateTime.now().toUtc(),
        );
    _persistAndNavigate(ctx);
  }
}

Future<void> _openFromRemoteMessage(RemoteMessage message) async {
  // Do not log raw FCM payloads.
  final data = Map<String, dynamic>.from(message.data);
  final launch = parseNotificationLaunchContext(data: data);
  InboxRefreshBus.instance.triggerDebounced();
  if (launch == null) return;

  await _sendCanonicalFeedbackIfNeeded(
    notificationId: launch.sourceNotificationId,
    actionId: 'OPEN_CHAT',
  );
  await _persistAndNavigate(launch);
}

Future<void> _persistAndNavigate(NotificationLaunchContext launch) async {
  if (!launch.isValid) return;
  await _pendingLaunchStore.save(launch);

  final context = navigatorKey.currentContext;
  if (context == null) {
    // Preserve pending context until navigator is ready / Gate 1 resolves session.
    _fcmLog('[FCM] navigator not ready; pending launch retained');
    return;
  }

  final hasSession = await SessionGateResolver.hasValidSession();
  if (!context.mounted) return;

  if (!hasSession) {
    AppGateRouter.goToLogin(context);
    return;
  }

  AppGateRouter.goToHeart(
    context,
    fromNotification: true,
    notificationLaunch: launch,
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
