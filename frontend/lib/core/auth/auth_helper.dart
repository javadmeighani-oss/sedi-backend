import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';

import '../../data/repositories/notification_repository.dart';
import '../navigation/app_gate_router.dart';
import '../navigation/app_navigator.dart';
import '../utils/user_profile_manager.dart';
import 'auth_service.dart';
import 'auth_session_manager.dart';
import 'user_identity_service.dart';

/// راهنمای استفاده از سرویس احراز هویت
///
/// برای تنظیم توکن احراز هویت:
/// ```dart
/// await AuthService.setToken('your-token-here');
/// ```
///
/// برای دریافت توکن:
/// ```dart
/// final token = await AuthService.getToken();
/// ```
///
/// برای بررسی وجود توکن:
/// ```dart
/// final hasToken = await AuthService.hasToken();
/// ```
///
/// برای خروج کامل (شامل unregister FCM و پاک کردن session):
/// ```dart
/// await AuthHelper.performLogout();
/// ```

class AuthHelper {
  /// Performs full logout: revoke refresh, unregister FCM, clear session, navigate to login.
  static Future<bool> performLogout({BuildContext? context}) async {
    await AuthSessionManager.revokeRefreshOnServer();

    final profile = await UserProfileManager.loadProfile();
    final userId = profile.userId;

    if (userId != null) {
      try {
        final token = await FirebaseMessaging.instance.getToken();
        if (token != null && token.isNotEmpty) {
          final repo = NotificationRepository();
          await repo.unregisterToken(userId: userId, fcmToken: token);
        }
      } catch (_) {
        // Best-effort: proceed with logout regardless
      }
    }

    await AuthService.clearUserData();
    await UserProfileManager.clearProfile();
    UserIdentityService.clearCache();

    final navContext = context ?? navigatorKey.currentContext;
    if (navContext != null && navContext.mounted) {
      AppGateRouter.goToLogin(navContext);
    }
    return true;
  }
  /// تنظیم توکن از یک endpoint لاگین (در صورت نیاز)
  /// این متد را می‌توانید برای لاگین استفاده کنید
  static Future<bool> login(String username, String password) async {
    // در حال حاضر باید توکن را به صورت دستی تنظیم کنید
    // await AuthService.setToken('your-token-from-backend');
    return false;
  }

  /// تنظیم توکن به صورت دستی (برای تست)
  static Future<bool> setTokenManually(String token) async {
    return await AuthService.setToken(token);
  }
}
