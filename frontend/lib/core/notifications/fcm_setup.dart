/// FCM setup: background handler and initialization helpers.
/// Stage 16.6 / Section 14-A2 push notifications.
library;

import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'local_notifications_service.dart';

void _fcmBackgroundLog(String message) {
  if (kDebugMode) {
    debugPrint(message);
  }
}

/// Top-level background handler. Must be top-level for Firebase isolate.
///
/// Integration limitation: when the FCM message includes a `notification`
/// payload, the OS displays it. Action buttons on that OS-owned notification
/// depend on platform/APNs category wiring and backend data-only delivery —
/// this handler only mirrors data-only messages into a local notification
/// with canonical actions. Do not claim background native action buttons work
/// for notification+data dual payloads without delivery-mode work.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp();
    await LocalNotificationsService.init();
    // Skip local duplicate when OS already displays notification payload.
    if (LocalNotificationsService.osWillDisplayRemoteNotification(message)) {
      return;
    }
    await LocalNotificationsService.showRemoteNotification(message);
  } catch (_) {
    _fcmBackgroundLog('[FCM] background handler failed');
  }
}

/// Parse payload JSON from notification response.
Map<String, dynamic>? parseNotificationPayload(String? payloadJson) {
  if (payloadJson == null || payloadJson.isEmpty) return null;
  try {
    final decoded = jsonDecode(payloadJson);
    return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
  } catch (_) {
    return null;
  }
}
