import 'api_error.dart';

/// Backend-standard response: { ok, data, error }
/// See: frontend/docs/FRONTEND_BACKEND_ALIGNMENT.md
class ApiResponse<T> {
  final bool ok;
  final T? data;
  final ApiError? error;
  /// HTTP status code when available (e.g. from ApiClient); for logging/trace (Stage 19).
  final int? statusCode;

  const ApiResponse({
    required this.ok,
    this.data,
    this.error,
    this.statusCode,
  });

  /// Parse from JSON. [parser] converts the raw "data" object to T (or null).
  /// Use for responses where "data" is an object or list.
  static bool _readOk(dynamic value) {
    if (value is bool) return value;
    if (value is num) return value != 0;
    if (value is String) {
      final normalized = value.trim().toLowerCase();
      if (normalized == 'true' || normalized == '1') return true;
      if (normalized == 'false' || normalized == '0') return false;
    }
    return false;
  }

  static ApiResponse<T> fromJson<T>(
    Map<String, dynamic> json,
    T? Function(Object? dataJson) parser,
  ) {
    final ok = json.containsKey('ok') ? _readOk(json['ok']) : false;
    final errorJson = json['error'];
    final ApiError? error = errorJson == null
        ? null
        : ApiError.fromJson(
            errorJson is Map ? Map<String, dynamic>.from(errorJson) : null,
          );
    T? data;
    final rawData = json['data'];
    if (rawData != null) {
      try {
        data = parser(rawData);
      } catch (_) {
        data = null;
      }
    }
    return ApiResponse<T>(ok: ok, data: data, error: error, statusCode: null);
  }

  bool get isSuccess => ok && error == null;
  String get errorMessage => error?.message ?? 'Unknown error';

  @override
  String toString() => 'ApiResponse(ok: $ok, data: $data, error: $error)';
}
