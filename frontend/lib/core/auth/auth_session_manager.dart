import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../features/auth_otp/presentation/pages/otp_login_page.dart';
import '../navigation/app_navigator.dart';
import '../utils/user_profile_manager.dart';
import 'auth_service.dart';

/// Clears session and navigates to OTP login (used after refresh failure).
class AuthSessionManager {
  static bool _handling = false;

  static Future<void> forceLogoutAndNavigate() async {
    if (_handling) return;
    _handling = true;
    try {
      await AuthService.clearUserData();
      await UserProfileManager.clearProfile();
      final ctx = navigatorKey.currentContext;
      if (ctx != null && ctx.mounted) {
        Navigator.of(ctx).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const OtpLoginPage()),
          (_) => false,
        );
      }
    } finally {
      _handling = false;
    }
  }

  /// Best-effort revoke refresh token on backend.
  static Future<void> revokeRefreshOnServer() async {
    final refreshToken = await AuthService.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) return;
    try {
      final uri = Uri.parse('${AppConfig.baseUrl}/auth/logout');
      await http
          .post(
            uri,
            headers: {
              'Authorization': 'Bearer $refreshToken',
              'Content-Type': 'application/json',
            },
          )
          .timeout(const Duration(seconds: 10));
    } catch (_) {
      // Best-effort only.
    }
  }
}
