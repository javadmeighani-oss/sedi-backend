/// Push (FCM) token registration with backend.
/// Single entry point: registerFcmTokenToBackend(token).
/// Uses existing ApiClient via NotificationRepository; optionally stores token in preferences.
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/utils/user_profile_manager.dart';
import '../../data/repositories/notification_repository.dart';

const String _prefKeyFcmToken = 'fcm_token';

/// Register the given FCM token with the backend (POST /notifications/push/register).
/// Requires a logged-in user (userId from UserProfileManager). Uses existing API client.
/// Returns true if registration succeeded, false if no user or request failed.
Future<bool> registerFcmTokenToBackend(String token) async {
  if (token.isEmpty) return false;
  try {
    final profile = await UserProfileManager.loadProfile();
    final userId = profile.userId;
    if (userId == null) return false;

    final repo = NotificationRepository();
    final response = await repo.registerToken(
      userId: userId,
      fcmToken: token,
      appVersion: '1.0.0',
    );
    return response.ok;
  } catch (e) {
    print('[PushService] registerFcmTokenToBackend error: $e');
    return false;
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
