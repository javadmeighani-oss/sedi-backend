/// Push (FCM) token registration with backend.
/// Single entry point: registerFcmTokenToBackend(token).
/// Uses existing ApiClient via NotificationRepository; optionally stores token in preferences.
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/config/app_config.dart';
import '../../core/network/api_response.dart';
import '../../core/utils/user_profile_manager.dart';
import '../../data/repositories/notification_repository.dart';

const String _prefKeyFcmToken = 'fcm_token';

/// Register the given FCM token with the backend (POST /notifications/push/register).
/// Requires a logged-in user (userId from UserProfileManager). Uses existing API client.
/// Returns ApiResponse for caller to log statusCode (Stage 19); ok indicates success.
Future<ApiResponse<Map<String, dynamic>?>> registerFcmTokenToBackend(String token) async {
  debugPrint('[FCM] registerFcmTokenToBackend enter');
  debugPrint('[FCM] baseUrl=${AppConfig.baseUrl}');
  if (token.isEmpty) {
    return ApiResponse(ok: false, statusCode: null);
  }
  try {
    final profile = await UserProfileManager.loadProfile();
    final userId = profile.userId;
    debugPrint('[FCM] userId(current)=$userId');
    if (userId == null) {
      debugPrint('[FCM] userId is null -> SKIP backend register (will retry after login)');
      return ApiResponse(ok: false, statusCode: null);
    }

    debugPrint('[FCM] calling NotificationRepository.registerToken(userId=$userId, platform=android, app_version=1.0.0)');
    final repo = NotificationRepository();
    final response = await repo.registerToken(
      userId: userId,
      fcmToken: token,
      appVersion: '1.0.0',
    );
    debugPrint('[FCM] repo.registerToken result: status=${response.statusCode ?? '?'} ok=${response.ok} error=${response.error?.message}');
    return response;
  } catch (e) {
    print('[PushService] registerFcmTokenToBackend error: $e');
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
  } catch (e) {
    print('[PushService] saveTokenToPreferences error: $e');
  }
}

/// Read stored FCM token from preferences (optional; may be stale after refresh).
Future<String?> getTokenFromPreferences() async {
  try {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_prefKeyFcmToken);
  } catch (e) {
    print('[PushService] getTokenFromPreferences error: $e');
    return null;
  }
}

/// Call after login/onboarding when profile (userId) has just been saved.
/// If a token was stored in preferences (e.g. before userId was available), registers it now.
Future<void> tryRegisterStoredTokenAfterLogin() async {
  final token = await getTokenFromPreferences();
  if (token == null || token.isEmpty) return;
  await registerFcmTokenToBackend(token);
}
