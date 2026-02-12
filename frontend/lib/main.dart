import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/navigation/app_navigator.dart';
import 'core/notifications/fcm_setup.dart';
import 'core/notifications/local_notifications_service.dart';
import 'data/repositories/notification_repository.dart';
import 'features/chat/presentation/pages/chat_page.dart';
import 'services/push/push_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Firebase & FCM (graceful if google-services.json missing)
  try {
    await Firebase.initializeApp();
    await _setupFcm();
  } catch (e) {
    print('[main] Firebase/FCM setup skipped: $e');
  }

  runApp(const SediApp());
}

/// Dedupe: avoid sending open_chat feedback twice for same notification.
final _feedbackSentIds = <int>{};
const int _maxFeedbackDedupSize = 50;

Future<void> _setupFcm() async {
  // Request notification permission (Android 13+)
  await FirebaseMessaging.instance.requestPermission(
    alert: true,
    badge: true,
    sound: true,
    provisional: false,
  );

  // Initialize local notifications with action handler
  await LocalNotificationsService.init(
    onResponse: _handleNotificationResponse,
  );

  // Background handler
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

  // Foreground: show via local notifications
  FirebaseMessaging.onMessage.listen((RemoteMessage message) {
    LocalNotificationsService.showRemoteNotification(message);
  });

  // Opened from background/terminated
  FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
    _navigateToChatFromMessage(message);
  });

  // Check if app was opened from terminated state via notification
  final initialMessage = await FirebaseMessaging.instance.getInitialMessage();
  if (initialMessage != null) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _navigateToChatFromMessage(initialMessage);
    });
  }

  // Register token with backend (when user is logged in)
  _registerTokenOnStart();
  FirebaseMessaging.instance.onTokenRefresh.listen((_) => _registerTokenOnStart());
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
  if (id != null) _sendOpenChatFeedbackIfNeeded(id);
  _navigateToChat(notificationId: id);
}

void _navigateToChat({int? notificationId}) {
  final context = navigatorKey.currentContext;
  if (context == null) return;
  Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => ChatPage(
        fromNotification: true,
        notificationId: notificationId,
      ),
    ),
  );
}

Future<void> _registerTokenOnStart() async {
  try {
    final token = await FirebaseMessaging.instance.getToken();
    if (token == null || token.isEmpty) return;

    // Single-line log for debugging (masked: first 8 + last 4)
    final masked = token.length > 12
        ? '${token.substring(0, 8)}...${token.substring(token.length - 4)}'
        : '***';
    print('[FCM] token: $masked (len=${token.length})');

    await saveTokenToPreferences(token);
    await registerFcmTokenToBackend(token);
  } catch (e) {
    print('[FCM] Token register error: $e');
  }
}
