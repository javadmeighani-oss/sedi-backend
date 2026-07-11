/// Push (FCM) token registration with backend.
/// Single entry point: registerFcmTokenToBackend(token).
/// Uses existing ApiClient via NotificationRepository; optionally stores token in preferences.
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/network/api_response.dart';
import '../../core/utils/user_profile_manager.dart';
import '../../data/repositories/notification_repository.dart';

const String _prefKeyFcmToken = 'fcm_token';

/// Stage 19.2: Ensure we only run ensureFcmRegisteredAfterLogin once per app session.
bool _didEnsureFcmAfterLogin = false;

void _pushLog(String message) {
  if (kDebugMode) {
    debugPrint(message);
  }
}

/// Register the given FCM token with the backend (POST /notifications/push/register).
/// Requires a logged-in user (userId from UserProfileManager). Uses existing API client.
Future<ApiResponse<Map<String, dynamic>?>> registerFcmTokenToBackend(
  String token,
) async {
  _pushLog('[FCM] registerFcmTokenToBackend enter');
  if (token.isEmpty) {
    return ApiResponse(ok: false, statusCode: null);
  }
  try {
    final profile = await UserProfileManager.loadProfile();
    if (profile.userId == null) {
      _pushLog('[FCM] backend register skipped: no session');
      return ApiResponse(ok: false, statusCode: null);
    }

    final repo = NotificationRepository();
    final response = await repo.registerToken(
      userId: profile.userId!,
      fcmToken: token,
      appVersion: '1.0.0',
    );
    _pushLog(
      '[FCM] backend register finished: ok=${response.ok} status=${response.statusCode ?? '?'}',
    );
    return response;
  } catch (_) {
    _pushLog('[FCM] backend register failed');
    return ApiResponse(ok: false, statusCode: null);
  }
}

/// Optionally store FCM token in app preferences.
Future<void> saveTokenToPreferences(String? token) async {
  try {
    final prefs = await SharedPreferences.getInstance();
    if (token == null || token.isEmpty) {
      await prefs.remove(_prefKeyFcmToken);
    } else {
      await prefs.setString(_prefKeyFcmToken, token);
    }
  } catch (_) {
    _pushLog('[FCM] preference save failed');
  }
}

/// Read stored FCM token from preferences (optional; may be stale after refresh).
Future<String?> getTokenFromPreferences() async {
  try {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_prefKeyFcmToken);
  } catch (_) {
    _pushLog('[FCM] preference read failed');
    return null;
  }
}

/// Guarantee: after login (userId persisted), always attempt to register FCM token (Stage 19.1).
/// Uses stored token from prefs, or fetches fresh via getToken() if none stored.
Future<void> ensureFcmRegisteredAfterLogin() async {
  try {
    if (_didEnsureFcmAfterLogin) {
      _pushLog('[FCM] post-login register skipped: already done');
      return;
    }
    _pushLog('[FCM] ensureFcmRegisteredAfterLogin enter');
    final profile = await UserProfileManager.loadProfile();
    if (profile.userId == null) {
      _pushLog('[FCM] post-login register skipped: no session');
      return;
    }

    String? token = await getTokenFromPreferences();
    if (token == null || token.trim().isEmpty) {
      _pushLog('[FCM] post-login register: fetching device credential');
      final fresh = await FirebaseMessaging.instance.getToken();
      if (fresh == null || fresh.trim().isEmpty) {
        _pushLog('[FCM] post-login register skipped: no device credential');
        return;
      }
      await saveTokenToPreferences(fresh);
      token = fresh;
    }

    await registerFcmTokenToBackend(token);
    _didEnsureFcmAfterLogin = true;
  } catch (_) {
    _pushLog('[FCM] post-login register failed');
  }
}

/// Call after login/onboarding when profile (userId) has just been saved.
Future<void> tryRegisterStoredTokenAfterLogin() async {
  await ensureFcmRegisteredAfterLogin();
}
