import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'auth_service.dart';

/// Exchanges refresh token for new access + refresh pair (rotation).
class AuthRefreshService {
  static bool _refreshInProgress = false;

  /// Returns true when new tokens were stored.
  static Future<bool> tryRefresh() async {
    if (_refreshInProgress) return false;
    final refreshToken = await AuthService.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) return false;

    _refreshInProgress = true;
    try {
      final uri = Uri.parse('${AppConfig.baseUrl}/auth/refresh');
      final response = await http
          .post(
            uri,
            headers: {
              'Authorization': 'Bearer $refreshToken',
              'Content-Type': 'application/json',
            },
          )
          .timeout(const Duration(seconds: 15));

      if (response.statusCode < 200 || response.statusCode >= 300) {
        return false;
      }

      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return false;
      final root = Map<String, dynamic>.from(decoded);
      final data = root['data'];
      final payload = data is Map ? Map<String, dynamic>.from(data) : root;

      final access = payload['access_token']?.toString();
      final newRefresh = payload['refresh_token']?.toString();
      if (access == null || access.isEmpty) return false;

      await AuthService.setTokens(
        accessToken: access,
        refreshToken: newRefresh,
      );
      return true;
    } catch (_) {
      return false;
    } finally {
      _refreshInProgress = false;
    }
  }
}
