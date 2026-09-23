import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'auth_service.dart';

/// Result of one refresh attempt. Transient failures must not force logout.
enum AuthRefreshOutcome {
  success,
  invalidSession,
  transientFailure,
}

/// Exchanges refresh token for new access + refresh pair (rotation).
///
/// Concurrent callers share one in-flight Future (single-flight).
/// Multi-session backend policy is unchanged: this only serializes the
/// same local refresh token so a second caller cannot treat "in progress"
/// as failure.
class AuthRefreshService {
  static Future<AuthRefreshOutcome>? _inFlight;

  /// Test-only override of the network perform path.
  @visibleForTesting
  static Future<AuthRefreshOutcome> Function()? debugPerformOverride;

  @visibleForTesting
  static void debugReset() {
    _inFlight = null;
    debugPerformOverride = null;
  }

  /// Returns true when new tokens were stored.
  static Future<bool> tryRefresh() async {
    final outcome = await refreshOnce();
    return outcome == AuthRefreshOutcome.success;
  }

  /// Single-flight refresh. Concurrent 401 callers await this same Future.
  static Future<AuthRefreshOutcome> refreshOnce() {
    final existing = _inFlight;
    if (existing != null) return existing;

    late final Future<AuthRefreshOutcome> started;
    started = _perform().whenComplete(() {
      if (identical(_inFlight, started)) {
        _inFlight = null;
      }
    });
    _inFlight = started;
    return started;
  }

  static Future<AuthRefreshOutcome> _perform() {
    final override = debugPerformOverride;
    if (override != null) return override();
    return _performNetwork();
  }

  static Future<AuthRefreshOutcome> _performNetwork() async {
    final refreshToken = await AuthService.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) {
      return AuthRefreshOutcome.invalidSession;
    }

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

      if (response.statusCode == 401 || response.statusCode == 403) {
        return AuthRefreshOutcome.invalidSession;
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return AuthRefreshOutcome.transientFailure;
      }

      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return AuthRefreshOutcome.transientFailure;
      final root = Map<String, dynamic>.from(decoded);
      final data = root['data'];
      final payload = data is Map ? Map<String, dynamic>.from(data) : root;

      final access = payload['access_token']?.toString();
      final newRefresh = payload['refresh_token']?.toString();
      if (access == null || access.isEmpty) {
        return AuthRefreshOutcome.transientFailure;
      }

      await AuthService.setTokens(
        accessToken: access,
        refreshToken: newRefresh,
      );
      return AuthRefreshOutcome.success;
    } catch (_) {
      // Timeout / network / parse ambiguity — keep the session.
      return AuthRefreshOutcome.transientFailure;
    }
  }
}
