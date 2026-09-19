import 'package:http/http.dart' as http;

import '../config/app_config.dart';

/// Bounded backend availability signal (not auth authority).
///
/// Uses GET `/healthz` only to inform UX. Session validity remains `/auth/me`.
class BackendAvailability {
  BackendAvailability._();

  static const Duration defaultTimeout = Duration(milliseconds: 1800);

  /// Returns true when `/healthz` responds with HTTP 2xx within [timeout].
  /// Failure / timeout ⇒ unavailable (never treated as authenticated).
  static Future<bool> probeHealthz({
    Duration timeout = defaultTimeout,
    String? baseUrl,
  }) async {
    final root = baseUrl ?? AppConfig.baseUrl;
    try {
      final uri = Uri.parse('$root/healthz');
      final response = await http.get(uri).timeout(timeout);
      return response.statusCode >= 200 && response.statusCode < 300;
    } catch (_) {
      return false;
    }
  }
}
